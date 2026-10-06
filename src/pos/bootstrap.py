"""Raíz de composición: el único lugar que conoce las piezas concretas y las conecta.

Para un cliente con necesidades distintas se cambia aquí el adaptador (otra base de
datos, un proveedor de facturación electrónica, notificaciones) y nada más.
"""

from __future__ import annotations

from dataclasses import dataclass

from .application.event_handlers import ElectronicInvoicingHandler, log_low_stock
from .application.ports import Clock, InvoiceProvider, UnitOfWorkFactory
from .application.use_cases import cash, catalog, customers, inventory, reports, sales, settings, users
from .config import AppConfig
from .domain.catalog import StockLow
from .domain.sales import SaleCompleted
from .infrastructure.clock import SystemClock
from .infrastructure.events import SyncEventBus
from .infrastructure.invoicing import NoInvoiceProvider
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
    create_user: users.CreateUser
    update_user: users.UpdateUser
    change_own_password: users.ChangeOwnPassword
    list_users: users.ListUsers
    # configuración
    get_settings: settings.GetSettings
    update_settings: settings.UpdateSettings
    # catálogo
    create_category: catalog.CreateCategory
    list_categories: catalog.ListCategories
    create_product: catalog.CreateProduct
    update_product: catalog.UpdateProduct
    get_product: catalog.GetProduct
    find_product_by_code: catalog.FindProductByCode
    search_products: catalog.SearchProducts
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
    # reportes
    get_sales_summary: reports.GetSalesSummary
    get_top_products: reports.GetTopProducts


def build_container(
    config: AppConfig,
    *,
    clock: Clock | None = None,
    invoice_provider: InvoiceProvider | None = None,
) -> Container:
    clock = clock or SystemClock()

    bus = SyncEventBus()
    bus.subscribe(StockLow, log_low_stock)
    bus.subscribe(SaleCompleted, ElectronicInvoicingHandler(invoice_provider or NoInvoiceProvider()))

    migrate(config.database_path)

    def uow(*, read_only: bool = False) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(config.database_path, bus, read_only=read_only)

    hasher = Pbkdf2PasswordHasher(config.password_iterations)
    tokens = JwtTokenService(config.secret_key, config.token_ttl_minutes, clock)
    settings.EnsureSettings(uow).execute(config.business_name)

    return Container(
        config=config,
        uow_factory=uow,
        login=users.Login(uow, hasher, tokens, InMemoryLoginThrottle(clock)),
        resolve_actor=users.ResolveActor(uow, tokens),
        bootstrap_admin=users.BootstrapAdmin(uow, hasher, clock),
        create_user=users.CreateUser(uow, hasher, clock),
        update_user=users.UpdateUser(uow, hasher),
        change_own_password=users.ChangeOwnPassword(uow, hasher),
        list_users=users.ListUsers(uow),
        get_settings=settings.GetSettings(uow),
        update_settings=settings.UpdateSettings(uow),
        create_category=catalog.CreateCategory(uow),
        list_categories=catalog.ListCategories(uow),
        create_product=catalog.CreateProduct(uow, clock),
        update_product=catalog.UpdateProduct(uow, clock),
        get_product=catalog.GetProduct(uow),
        find_product_by_code=catalog.FindProductByCode(uow),
        search_products=catalog.SearchProducts(uow),
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
        get_sales_summary=reports.GetSalesSummary(uow),
        get_top_products=reports.GetTopProducts(uow),
    )
