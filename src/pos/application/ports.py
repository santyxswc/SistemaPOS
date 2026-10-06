"""Puertos: contratos que la aplicación necesita del mundo exterior (inversión de dependencias).

Los casos de uso dependen de estas abstracciones; la infraestructura (SQLite, JWT,
PBKDF2...) las implementa. Cambiar de base de datos o conectar un proveedor de
facturación electrónica es escribir un adaptador nuevo, sin tocar las reglas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from ..domain.cash import CashSession
from ..domain.catalog import Category, Product
from ..domain.customers import Customer, LedgerEntry
from ..domain.inventory import StockMovement
from ..domain.sales import Sale
from ..domain.settings import BusinessSettings
from ..domain.shared.entity import AggregateRoot
from ..domain.shared.events import DomainEvent
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


class EventPublisher(Protocol):
    def publish(self, events: Sequence[DomainEvent]) -> None: ...


class InvoiceProvider(Protocol):
    """Punto de extensión para facturación electrónica (proveedor autorizado por la DIAN)."""

    def issue_for_sale(self, sale_id: UUID) -> None: ...


# --- Repositorios ---------------------------------------------------------------


class SettingsRepository(Protocol):
    def get(self) -> BusinessSettings | None: ...

    def save(self, settings: BusinessSettings) -> None: ...


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


# --- Unidad de trabajo -------------------------------------------------------------


class UnitOfWork(ABC):
    """Transacción de negocio: todo se confirma junto o nada.

    Después de confirmar publica los eventos de los agregados guardados, para que
    las reacciones (alertas, facturación) solo ocurran si los datos quedaron firmes.
    """

    settings: SettingsRepository
    sequences: SequenceRepository
    users: UserRepository
    categories: CategoryRepository
    products: ProductRepository
    stock_movements: StockMovementRepository
    customers: CustomerRepository
    ledger: LedgerRepository
    cash_sessions: CashSessionRepository
    sales: SaleRepository

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
