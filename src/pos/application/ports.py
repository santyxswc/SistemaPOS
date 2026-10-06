"""Puertos: contratos que la aplicación necesita del mundo exterior (inversión de dependencias).

Los casos de uso dependen de estas abstracciones; la infraestructura (SQLite, JWT,
PBKDF2...) las implementa. Cambiar de base de datos o conectar un proveedor de
facturación electrónica es escribir un adaptador nuevo, sin tocar las reglas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from ..domain.cash import CashSession
from ..domain.catalog import Category, Product
from ..domain.customers import Customer, LedgerEntry
from ..domain.inventory import StockMovement
from ..domain.licensing import License
from ..domain.payments import PaymentKind
from ..domain.sales import Sale
from ..domain.settings import BusinessSettings
from ..domain.shared.entity import AggregateRoot
from ..domain.shared.events import DomainEvent
from ..domain.shared.values import Money
from ..domain.suppliers import Purchase, Supplier, SupplierLedgerEntry
from ..domain.users import User

# --- Servicios técnicos -------------------------------------------------------


class Clock(Protocol):
    def now(self) -> datetime: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, hashed: str) -> bool: ...


class TokenService(Protocol):
    @property
    def expires_in_seconds(self) -> int: ...

    def issue(self, user: User) -> str: ...

    def decode(self, token: str) -> UUID:
        """Devuelve el id del usuario o lanza AuthenticationError."""
        ...


class LoginThrottle(Protocol):
    """Frena los intentos repetidos de adivinar una contraseña."""

    def check(self, key: str) -> None:
        """Lanza TooManyAttempts si la clave está bloqueada."""
        ...

    def failed(self, key: str) -> None: ...

    def succeeded(self, key: str) -> None: ...


class EventPublisher(Protocol):
    def publish(self, events: Sequence[DomainEvent]) -> None: ...


class LicenseVerifier(Protocol):
    """Comprueba la firma de un código de licencia emitido por el proveedor del sistema."""

    def verify(self, code: str) -> License:
        """Devuelve la licencia o lanza ValidationError si el código es falso o está dañado."""
        ...


@dataclass(frozen=True)
class BackupFile:
    name: str
    created_at: datetime
    size_bytes: int


@dataclass(frozen=True)
class BackupResult:
    file: BackupFile
    extra_copy: str | None = None  # ruta de la copia adicional (USB, OneDrive...)
    extra_error: str | None = None  # por qué no se pudo copiar allí (USB desconectada...)


class BackupService(Protocol):
    """Copias de seguridad de la base de datos del negocio."""

    def create(self, *, at: datetime, extra_folder: str | None = None) -> BackupResult:
        """Copia verificada en la carpeta principal y, si se indica, otra en `extra_folder`.

        Que falle la copia adicional nunca hace fallar el respaldo principal.
        """
        ...

    def list_recent(self, limit: int = 10) -> list[BackupFile]: ...

    def check_folder(self, folder: str) -> None:
        """Lanza ValidationError si la carpeta no existe o no se puede escribir en ella."""
        ...


class InvoiceProvider(Protocol):
    """Punto de extensión para facturación electrónica (proveedor autorizado por la DIAN)."""

    def issue_for_sale(self, sale_id: UUID) -> None: ...


# --- Repositorios ---------------------------------------------------------------


class SettingsRepository(Protocol):
    def get(self) -> BusinessSettings | None: ...

    def save(self, settings: BusinessSettings) -> None: ...


class LicenseRepository(Protocol):
    """Guarda el código de licencia tal como se instaló y la fecha de instalación (inicio de la prueba)."""

    def get_code(self) -> str | None: ...

    def save_code(self, code: str) -> None: ...

    def get_installed_at(self) -> datetime | None: ...

    def save_installed_at(self, at: datetime) -> None: ...


class SequenceRepository(Protocol):
    def next_value(self, name: str) -> int: ...


class UserRepository(Protocol):
    def add(self, user: User) -> None: ...

    def save(self, user: User) -> None: ...

    def get(self, user_id: UUID) -> User | None: ...

    def get_by_username(self, username: str) -> User | None: ...

    def list_all(self) -> list[User]: ...

    def count(self, *, active_only: bool = False) -> int: ...


class CategoryRepository(Protocol):
    def add(self, category: Category) -> None: ...

    def get(self, category_id: UUID) -> Category | None: ...

    def get_by_name(self, name: str) -> Category | None: ...

    def list_all(self, *, include_inactive: bool = False) -> list[Category]: ...


class ProductRepository(Protocol):
    def add(self, product: Product) -> None: ...

    def save(self, product: Product) -> None: ...

    def get(self, product_id: UUID) -> Product | None: ...

    def get_many(self, product_ids: Collection[UUID]) -> dict[UUID, Product]: ...

    def get_by_sku(self, sku: str) -> Product | None: ...

    def get_by_barcode(self, barcode: str) -> Product | None: ...

    def search(
        self,
        *,
        text: str | None = None,
        category_id: UUID | None = None,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Product]: ...

    def list_low_stock(self) -> list[Product]: ...

    def list_all(self, *, include_inactive: bool = False) -> list[Product]:
        """Todo el catálogo ordenado por nombre (exportar a Excel)."""
        ...


class StockMovementRepository(Protocol):
    def add(self, movement: StockMovement) -> None: ...

    def list_for_product(self, product_id: UUID, *, limit: int = 50) -> list[StockMovement]: ...


class CustomerRepository(Protocol):
    def add(self, customer: Customer) -> None: ...

    def save(self, customer: Customer) -> None: ...

    def get(self, customer_id: UUID) -> Customer | None: ...

    def get_by_document(self, document: str) -> Customer | None: ...

    def search(
        self, *, text: str | None = None, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> list[Customer]: ...


class LedgerRepository(Protocol):
    def add(self, entry: LedgerEntry) -> None: ...

    def list_for_customer(self, customer_id: UUID, *, limit: int = 50) -> list[LedgerEntry]: ...


class SupplierRepository(Protocol):
    def add(self, supplier: Supplier) -> None: ...

    def save(self, supplier: Supplier) -> None: ...

    def get(self, supplier_id: UUID) -> Supplier | None: ...

    def get_by_document(self, document: str) -> Supplier | None: ...

    def search(
        self,
        *,
        text: str | None = None,
        include_inactive: bool = False,
        with_balance_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Supplier]: ...


class SupplierLedgerRepository(Protocol):
    def add(self, entry: SupplierLedgerEntry) -> None: ...

    def list_for_supplier(self, supplier_id: UUID, *, limit: int = 50) -> list[SupplierLedgerEntry]: ...


@dataclass(frozen=True)
class PurchaseFilter:
    supplier_id: UUID | None = None
    pending_only: bool = False
    start: datetime | None = None  # inclusive, UTC
    end: datetime | None = None  # exclusivo, UTC
    due_before: date | None = None  # pendientes que vencen antes de esta fecha (vencidas)


class PurchaseRepository(Protocol):
    def add(self, purchase: Purchase) -> None: ...

    def save(self, purchase: Purchase) -> None:
        """Solo cambia el saldo pendiente: las líneas de una compra nunca se editan."""
        ...

    def get(self, purchase_id: UUID) -> Purchase | None: ...

    def find(self, where: PurchaseFilter, *, limit: int = 50, offset: int = 0) -> list[Purchase]:
        """De la más reciente a la más antigua."""
        ...

    def list_pending_for_supplier(self, supplier_id: UUID) -> list[Purchase]: ...


class CashSessionRepository(Protocol):
    def add(self, session: CashSession) -> None: ...

    def save(self, session: CashSession) -> None: ...

    def get(self, session_id: UUID) -> CashSession | None: ...

    def get_open_for_cashier(self, cashier_id: UUID) -> CashSession | None: ...

    def list_recent(self, *, limit: int = 50, offset: int = 0) -> list[CashSession]: ...


class SaleRepository(Protocol):
    def add(self, sale: Sale) -> None: ...

    def save(self, sale: Sale) -> None: ...

    def get(self, sale_id: UUID) -> Sale | None: ...

    def get_by_request_id(self, request_id: str) -> Sale | None: ...

    def find(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        cashier_id: UUID | None = None,
        cash_session_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Sale]: ...


# --- Consultas de reportes (modelo de lectura) ----------------------------------------
#
# Los reportes no necesitan ventas completas: piden sumas. Separar la lectura de la
# escritura (CQRS ligero) deja que cada base de datos agregue a su manera y que un
# reporte de un año no cargue miles de ventas en memoria.


@dataclass(frozen=True)
class SalesFilter:
    start: datetime | None = None  # inclusive, UTC
    end: datetime | None = None  # exclusivo, UTC
    cash_session_id: UUID | None = None


@dataclass(frozen=True)
class SalesTotals:
    sales_count: int
    voided_count: int
    subtotal: Money
    tax_total: Money
    discount_total: Money
    total: Money


@dataclass(frozen=True)
class PaymentTotal:
    code: str
    name: str
    kind: PaymentKind
    amount: Money


@dataclass(frozen=True)
class ProductSales:
    product_id: UUID
    sku: str
    description: str
    quantity: Decimal
    total: Money


@dataclass(frozen=True)
class SaleRow:
    """Una venta en una fila, para exportar (sin cargar líneas ni pagos completos)."""

    number: int
    created_at: datetime
    status: str
    cashier: str
    customer: str | None
    subtotal: Money
    tax_total: Money
    discount_total: Money
    total: Money
    payments: tuple[tuple[str, Money], ...]  # (método, monto neto sin vueltas)


class SalesReportQueries(Protocol):
    """Todas las cifras cuentan solo ventas no anuladas, salvo `voided_count`."""

    def totals(self, where: SalesFilter) -> SalesTotals: ...

    def totals_by_payment_method(self, where: SalesFilter) -> list[PaymentTotal]:
        """Lo realmente recibido por método (sin vueltas), de mayor a menor."""
        ...

    def sale_amounts(self, where: SalesFilter) -> list[tuple[datetime, Money]]:
        """Fecha y total de cada venta, para agrupar por día o mes en la zona horaria del negocio."""
        ...

    def top_products(self, where: SalesFilter, limit: int) -> list[ProductSales]: ...

    def sale_rows(self, where: SalesFilter, limit: int) -> list[SaleRow]:
        """Todas las ventas del periodo, anuladas incluidas, de la más antigua a la más reciente."""
        ...


# --- Unidad de trabajo -------------------------------------------------------------


class UnitOfWork(ABC):
    """Transacción de negocio: todo se confirma junto o nada.

    Después de confirmar publica los eventos de los agregados guardados, para que
    las reacciones (alertas, facturación) solo ocurran si los datos quedaron firmes.
    """

    settings: SettingsRepository
    licensing: LicenseRepository
    sequences: SequenceRepository
    users: UserRepository
    categories: CategoryRepository
    products: ProductRepository
    stock_movements: StockMovementRepository
    customers: CustomerRepository
    ledger: LedgerRepository
    suppliers: SupplierRepository
    supplier_ledger: SupplierLedgerRepository
    purchases: PurchaseRepository
    cash_sessions: CashSessionRepository
    sales: SaleRepository
    sales_reports: SalesReportQueries

    def __init__(self, publisher: EventPublisher | None = None, *, read_only: bool = False) -> None:
        self._publisher = publisher
        self._tracked: list[AggregateRoot] = []
        self.read_only = read_only

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.rollback()

    def track(self, aggregate: AggregateRoot) -> None:
        if not any(seen is aggregate for seen in self._tracked):
            self._tracked.append(aggregate)

    def commit(self) -> None:
        if self.read_only:
            raise RuntimeError("Una unidad de trabajo de solo lectura no puede confirmar cambios")
        self._commit()
        events = [event for aggregate in self._tracked for event in aggregate.pull_events()]
        self._tracked.clear()
        if events and self._publisher is not None:
            self._publisher.publish(events)

    @abstractmethod
    def _commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    """Abre una unidad de trabajo.

    Las consultas piden `read_only=True`: no toman el candado de escritura, así que
    los reportes y las búsquedas nunca hacen esperar a quien está vendiendo.
    """

    def __call__(self, *, read_only: bool = False) -> UnitOfWork: ...
