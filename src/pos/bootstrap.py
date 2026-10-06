"""Raíz de composición: el único lugar que conoce las piezas concretas y las conecta.

Para un cliente con necesidades distintas se cambia aquí el adaptador (otra base de
datos, un proveedor de facturación electrónica, notificaciones) y nada más.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .application.event_handlers import ElectronicInvoicingHandler, log_low_stock
from .application.ports import Clock, InvoiceProvider, LicenseVerifier, UnitOfWorkFactory
from .application.use_cases import (
    backups,
    cash,
    catalog,
    catalog_import,
    customers,
    inventory,
    licensing,
    reports,
    sales,
    settings,
    suppliers,
    users,
)
from .config import AppConfig
from .domain.cash import CashSessionClosed
from .domain.catalog import StockLow
from .domain.sales import SaleCompleted
from .infrastructure.clock import SystemClock
from .infrastructure.events import SyncEventBus
from .infrastructure.invoicing import NoInvoiceProvider
from .infrastructure.license_key import PUBLIC_KEY
from .infrastructure.licensing import Ed25519LicenseVerifier
from .infrastructure.persistence.sqlite.backup import SqliteBackupService
from .infrastructure.persistence.sqlite.migrations import migrate
from .infrastructure.persistence.sqlite.unit_of_work import SqliteUnitOfWork
from .infrastructure.security import InMemoryLoginThrottle, JwtTokenService, Pbkdf2PasswordHasher


@dataclass(frozen=True)
class Container:
    config: AppConfig
    uow_factory: UnitOfWorkFactory
    # acceso y usuarios
    login: users.Login
    resolve_actor: users.ResolveActor
    bootstrap_admin: users.BootstrapAdmin
    get_setup_status: users.GetSetupStatus
    complete_initial_setup: users.CompleteInitialSetup
    create_user: users.CreateUser
    update_user: users.UpdateUser
    change_own_password: users.ChangeOwnPassword
    reset_password_from_console: users.ResetPasswordFromConsole
    list_users: users.ListUsers
    get_role_permissions: users.GetRolePermissions
    update_role_permissions: users.UpdateRolePermissions
    # licencia
    get_license_status: licensing.GetLicenseStatus
    install_license: licensing.InstallLicense
    # configuración
    get_settings: settings.GetSettings
    update_settings: settings.UpdateSettings
    # respaldos
    run_backup: backups.RunBackup
    list_backups: backups.ListBackups
    # catálogo
    create_category: catalog.CreateCategory
    list_categories: catalog.ListCategories
    create_product: catalog.CreateProduct
    update_product: catalog.UpdateProduct
    get_product: catalog.GetProduct
    find_product_by_code: catalog.FindProductByCode
    search_products: catalog.SearchProducts
    export_catalog: catalog.ExportCatalog
    import_products: catalog_import.ImportProducts
    # inventario
    register_purchase: inventory.RegisterPurchase
    adjust_stock: inventory.AdjustStock
    list_low_stock: inventory.ListLowStock
    list_stock_movements: inventory.ListStockMovements
    # caja
    open_cash_session: cash.OpenCashSession
    get_current_cash_session: cash.GetCurrentCashSession
    register_cash_movement: cash.RegisterCashMovement
    close_cash_session: cash.CloseCashSession
    get_cash_session_report: cash.GetCashSessionReport
    list_cash_sessions: cash.ListCashSessions
    # ventas
    create_sale: sales.CreateSale
    void_sale: sales.VoidSale
    get_sale: sales.GetSale
    list_sales: sales.ListSales
    # clientes y fiados
    create_customer: customers.CreateCustomer
    update_customer: customers.UpdateCustomer
    get_customer: customers.GetCustomer
    search_customers: customers.SearchCustomers
    get_customer_statement: customers.GetCustomerStatement
    register_customer_payment: customers.RegisterCustomerPayment
    # proveedores, compras y cuentas por pagar
    create_supplier: suppliers.CreateSupplier
    update_supplier: suppliers.UpdateSupplier
    get_supplier: suppliers.GetSupplier
    search_suppliers: suppliers.SearchSuppliers
    get_supplier_statement: suppliers.GetSupplierStatement
    receive_purchase: suppliers.ReceivePurchase
    list_purchases: suppliers.ListPurchases
    get_purchase: suppliers.GetPurchase
    pay_supplier: suppliers.PaySupplier
    get_payables_summary: suppliers.GetPayablesSummary
    # reportes
    get_sales_summary: reports.GetSalesSummary
    get_top_products: reports.GetTopProducts
    export_sales_report: reports.ExportSalesReport


def build_container(
    config: AppConfig,
    *,
    clock: Clock | None = None,
    invoice_provider: InvoiceProvider | None = None,
    license_verifier: LicenseVerifier | None = None,
) -> Container:
    clock = clock or SystemClock()
    # La clave pública va dentro del programa a propósito: no se lee de .env ni de la base de datos.
    verifier = license_verifier or Ed25519LicenseVerifier(PUBLIC_KEY)
    license_policy = licensing.LicensePolicy(verifier, clock)

    bus = SyncEventBus()
    bus.subscribe(StockLow, log_low_stock)
    bus.subscribe(SaleCompleted, ElectronicInvoicingHandler(invoice_provider or NoInvoiceProvider()))

    migrate(config.database_path)

    def uow(*, read_only: bool = False) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(config.database_path, bus, read_only=read_only)

    backup_service = SqliteBackupService(config.database_path, Path(config.database_path).parent / "backups")
    run_backup = backups.RunBackup(uow, backup_service, clock)
    bus.subscribe(CashSessionClosed, backups.BackupOnCashClose(run_backup))

    sales_summary = reports.GetSalesSummary(uow)
    hasher = Pbkdf2PasswordHasher(config.password_iterations)
    tokens = JwtTokenService(config.secret_key, config.token_ttl_minutes, clock)
    settings.EnsureSettings(uow, clock).execute(config.business_name)

    return Container(
        config=config,
        uow_factory=uow,
        login=users.Login(uow, hasher, tokens, InMemoryLoginThrottle(clock)),
        resolve_actor=users.ResolveActor(uow, tokens),
        bootstrap_admin=users.BootstrapAdmin(uow, hasher, clock),
        get_setup_status=users.GetSetupStatus(uow),
        complete_initial_setup=users.CompleteInitialSetup(uow, hasher, clock),
        create_user=users.CreateUser(uow, hasher, clock, license_policy),
        update_user=users.UpdateUser(uow, hasher, license_policy),
        change_own_password=users.ChangeOwnPassword(uow, hasher),
        reset_password_from_console=users.ResetPasswordFromConsole(uow, hasher, license_policy),
        list_users=users.ListUsers(uow),
        get_role_permissions=users.GetRolePermissions(uow),
        update_role_permissions=users.UpdateRolePermissions(uow),
        get_license_status=licensing.GetLicenseStatus(uow, license_policy),
        install_license=licensing.InstallLicense(uow, verifier, license_policy, clock),
        get_settings=settings.GetSettings(uow),
        update_settings=settings.UpdateSettings(uow, backup_service),
        run_backup=run_backup,
        list_backups=backups.ListBackups(backup_service),
        create_category=catalog.CreateCategory(uow),
        list_categories=catalog.ListCategories(uow),
        create_product=catalog.CreateProduct(uow, clock),
        update_product=catalog.UpdateProduct(uow, clock),
        get_product=catalog.GetProduct(uow),
        find_product_by_code=catalog.FindProductByCode(uow),
        search_products=catalog.SearchProducts(uow),
        export_catalog=catalog.ExportCatalog(uow),
        import_products=catalog_import.ImportProducts(uow, clock),
        register_purchase=inventory.RegisterPurchase(uow, clock),
        adjust_stock=inventory.AdjustStock(uow, clock),
        list_low_stock=inventory.ListLowStock(uow),
        list_stock_movements=inventory.ListStockMovements(uow),
        open_cash_session=cash.OpenCashSession(uow, clock),
        get_current_cash_session=cash.GetCurrentCashSession(uow),
        register_cash_movement=cash.RegisterCashMovement(uow, clock),
        close_cash_session=cash.CloseCashSession(uow, clock),
        get_cash_session_report=cash.GetCashSessionReport(uow),
        list_cash_sessions=cash.ListCashSessions(uow),
        create_sale=sales.CreateSale(uow, clock),
        void_sale=sales.VoidSale(uow, clock),
        get_sale=sales.GetSale(uow),
        list_sales=sales.ListSales(uow),
        create_customer=customers.CreateCustomer(uow, clock),
        update_customer=customers.UpdateCustomer(uow),
        get_customer=customers.GetCustomer(uow),
        search_customers=customers.SearchCustomers(uow),
        get_customer_statement=customers.GetCustomerStatement(uow),
        register_customer_payment=customers.RegisterCustomerPayment(uow, clock),
        create_supplier=suppliers.CreateSupplier(uow, clock),
        update_supplier=suppliers.UpdateSupplier(uow),
        get_supplier=suppliers.GetSupplier(uow),
        search_suppliers=suppliers.SearchSuppliers(uow),
        get_supplier_statement=suppliers.GetSupplierStatement(uow, clock),
        receive_purchase=suppliers.ReceivePurchase(uow, clock),
        list_purchases=suppliers.ListPurchases(uow),
        get_purchase=suppliers.GetPurchase(uow),
        pay_supplier=suppliers.PaySupplier(uow, clock),
        get_payables_summary=suppliers.GetPayablesSummary(uow, clock),
        get_sales_summary=sales_summary,
        get_top_products=reports.GetTopProducts(uow),
        export_sales_report=reports.ExportSalesReport(uow, sales_summary),
    )
