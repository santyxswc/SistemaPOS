"""Proveedores, compras de mercancía y cuentas por pagar.

Una compra a crédito queda como una factura pendiente del proveedor. Los pagos se
aplican a las facturas más antiguas primero (por fecha de vencimiento), así el dueño
sabe en todo momento qué facturas debe, cuáles vencieron y cuánto le falta a cada una.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from .shared.entity import AggregateRoot, Entity
from .shared.errors import BusinessRuleViolation, ValidationError
from .shared.events import DomainEvent
from .shared.values import Money, required_text

MAX_PURCHASE_LINES = 300


def _ensure_positive(amount: Money) -> None:
    if not amount.is_positive:
        raise ValidationError("El monto debe ser mayor que cero")


@dataclass(kw_only=True, eq=False)
class Supplier(AggregateRoot):
    EDITABLE_FIELDS = frozenset({"name", "document", "contact_name", "phone", "email", "address", "notes", "active"})

    name: str
    created_at: datetime
    document: str | None = None  # NIT o cédula
    contact_name: str = ""  # el vendedor o preventista que visita la tienda
    phone: str = ""
    email: str = ""
    address: str = ""
    notes: str = ""  # p. ej. "Visita los martes; pedido mínimo $200.000"
    balance: Money = field(default_factory=Money.zero)  # lo que el negocio le debe
    active: bool = True

    def __post_init__(self) -> None:
        self.name = required_text(self.name, "nombre del proveedor")
        self.document = (self.document or "").strip() or None
        self.contact_name = (self.contact_name or "").strip()
        self.phone = (self.phone or "").strip()
        self.email = (self.email or "").strip().lower()
        self.address = (self.address or "").strip()
        self.notes = (self.notes or "").strip()

    def update(self, **changes: object) -> None:
        unknown = set(changes) - self.EDITABLE_FIELDS
        if unknown:
            raise ValidationError(f"No se pueden editar estos campos: {', '.join(sorted(unknown))}")
        candidate = dataclasses.replace(self, **changes)  # type: ignore[arg-type]
        for name in changes:
            setattr(self, name, getattr(candidate, name))

    def add_debt(self, amount: Money) -> None:
        _ensure_positive(amount)
        if not self.active:
            raise BusinessRuleViolation(f"El proveedor «{self.name}» está inactivo")
        self.balance += amount

    def pay(self, amount: Money) -> None:
        _ensure_positive(amount)
        if amount > self.balance:
            raise BusinessRuleViolation(
                f"El pago ({amount.display()}) supera lo que se le debe a «{self.name}» ({self.balance.display()})"
            )
        self.balance -= amount


class PurchasePaymentMode(StrEnum):
    CASH_DRAWER = "cash_drawer"  # se paga con el efectivo de la caja abierta
    EXTERNAL = "external"  # transferencia, consignación o dinero que no sale de la caja
    CREDIT = "credit"  # queda debiendo: cuenta por pagar


PAYMENT_MODE_LABELS: dict[PurchasePaymentMode, str] = {
    PurchasePaymentMode.CASH_DRAWER: "Efectivo de la caja",
    PurchasePaymentMode.EXTERNAL: "Pagada por fuera de la caja",
    PurchasePaymentMode.CREDIT: "A crédito",
}


class PurchaseStatus(StrEnum):
    PAID = "paid"
    PENDING = "pending"  # a crédito, con saldo


@dataclass(frozen=True, kw_only=True)
class PurchaseLine:
    product_id: UUID
    sku: str
    description: str
    quantity: Decimal
    unit_cost: Money

    @property
    def total(self) -> Money:
        return self.unit_cost * self.quantity


@dataclass(frozen=True, kw_only=True)
class PurchaseRegistered(DomainEvent):
    purchase_id: UUID
    supplier_id: UUID | None
    total: Money


@dataclass(kw_only=True, eq=False)
class Purchase(AggregateRoot):
    """Entrada de mercancía con su factura de compra."""

    number: int
    user_id: UUID
    created_at: datetime
    payment_mode: PurchasePaymentMode
    lines: list[PurchaseLine]
    supplier_id: UUID | None = None
    invoice_number: str = ""  # número de la factura del proveedor
    due_date: date | None = None  # vencimiento, solo a crédito
    outstanding: Money = field(default_factory=Money.zero)
    note: str = ""

    def __post_init__(self) -> None:
        self.invoice_number = (self.invoice_number or "").strip()
        self.note = (self.note or "").strip()
        if not self.lines:
            raise ValidationError("La compra debe tener al menos un producto")
        if len(self.lines) > MAX_PURCHASE_LINES:
            raise ValidationError(f"Una compra admite máximo {MAX_PURCHASE_LINES} productos")
        if self.payment_mode is PurchasePaymentMode.CREDIT:
            if self.supplier_id is None:
                raise ValidationError("Una compra a crédito necesita el proveedor")
        elif self.due_date is not None:
            raise ValidationError("La fecha de vencimiento solo aplica a compras a crédito")

    @classmethod
    def register(
        cls,
        *,
        number: int,
        user_id: UUID,
        at: datetime,
        payment_mode: PurchasePaymentMode,
        lines: Sequence[PurchaseLine],
        supplier_id: UUID | None = None,
        invoice_number: str = "",
        due_date: date | None = None,
        note: str = "",
    ) -> Purchase:
        purchase = cls(
            number=number,
            user_id=user_id,
            created_at=at,
            payment_mode=payment_mode,
            lines=list(lines),
            supplier_id=supplier_id,
            invoice_number=invoice_number,
            due_date=due_date,
            note=note,
        )
        if payment_mode is PurchasePaymentMode.CREDIT:
            purchase.outstanding = purchase.total
        purchase.record(
            PurchaseRegistered(occurred_at=at, purchase_id=purchase.id, supplier_id=supplier_id, total=purchase.total)
        )
        return purchase

    @property
    def total(self) -> Money:
        return Money.sum(line.total for line in self.lines)

    @property
    def status(self) -> PurchaseStatus:
        return PurchaseStatus.PENDING if self.outstanding.is_positive else PurchaseStatus.PAID

    def is_overdue(self, today: date) -> bool:
        return self.status is PurchaseStatus.PENDING and self.due_date is not None and self.due_date < today

    def apply_payment(self, amount: Money) -> Money:
        """Abona hasta `amount` a esta factura. Devuelve lo que se aplicó."""
        applied = min(amount, self.outstanding)
        self.outstanding -= applied
        return applied


def allocate_payment(pending: Sequence[Purchase], amount: Money) -> list[tuple[Purchase, Money]]:
    """Reparte un pago entre las facturas pendientes: primero las que vencen antes.

    Las facturas sin vencimiento van después de las que tienen fecha, por antigüedad.
    """
    _ensure_positive(amount)
    ordered = sorted(
        (purchase for purchase in pending if purchase.outstanding.is_positive),
        key=lambda p: (p.due_date is None, p.due_date or date.max, p.created_at, p.number),
    )
    remaining = amount
    applied: list[tuple[Purchase, Money]] = []
    for purchase in ordered:
        if not remaining.is_positive:
            break
        part = purchase.apply_payment(remaining)
        remaining -= part
        applied.append((purchase, part))
    return applied


class SupplierEntryType(StrEnum):
    PURCHASE = "purchase"
    PAYMENT = "payment"


@dataclass(kw_only=True, eq=False)
class SupplierLedgerEntry(Entity):
    """Movimiento de la cuenta con el proveedor (solo se agregan, nunca se editan)."""

    supplier_id: UUID
    type: SupplierEntryType
    amount: Money
    balance_after: Money
    user_id: UUID
    created_at: datetime
    purchase_id: UUID | None = None
    method: str = ""  # cómo se pagó (efectivo de la caja, transferencia...)
    note: str = ""
