"""Clientes y cuentas por cobrar (fiados)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID

from .catalog import required_text
from .shared.entity import AggregateRoot, Entity
from .shared.errors import BusinessRuleViolation, CreditLimitExceeded, ValidationError
from .shared.values import Money


def _ensure_positive(amount: Money) -> None:
    if not amount.is_positive:
        raise ValidationError("El monto debe ser mayor que cero")


@dataclass(kw_only=True, eq=False)
class Customer(AggregateRoot):
    EDITABLE_FIELDS = frozenset({"name", "document", "phone", "email", "address", "credit_limit", "active"})

    name: str
    created_at: datetime
    document: str | None = None  # cédula o NIT
    phone: str = ""
    email: str = ""
    address: str = ""
    credit_limit: Money = field(default_factory=Money.zero)
    balance: Money = field(default_factory=Money.zero)  # lo que debe; negativo = saldo a favor
    active: bool = True

    def __post_init__(self) -> None:
        self.name = required_text(self.name, "nombre del cliente")
        self.document = (self.document or "").strip() or None
        self.phone = (self.phone or "").strip()
        self.email = (self.email or "").strip().lower()
        self.address = (self.address or "").strip()
        if self.credit_limit.is_negative:
            raise ValidationError("El cupo de crédito no puede ser negativo")

    @property
    def available_credit(self) -> Money:
        return self.credit_limit - self.balance

    def update(self, **changes: object) -> None:
        unknown = set(changes) - self.EDITABLE_FIELDS
        if unknown:
            raise ValidationError(f"No se pueden editar estos campos: {', '.join(sorted(unknown))}")
        candidate = dataclasses.replace(self, **changes)  # type: ignore[arg-type]
        for name in changes:
            setattr(self, name, getattr(candidate, name))

    def charge(self, amount: Money) -> None:
        """Registra una compra fiada respetando el cupo."""
        _ensure_positive(amount)
        if not self.active:
            raise BusinessRuleViolation(f"El cliente «{self.name}» está inactivo")
        if amount > self.available_credit:
            raise CreditLimitExceeded(
                f"«{self.name}» no tiene cupo suficiente: disponible "
                f"{self.available_credit.display()}, se piden {amount.display()}"
            )
        self.balance += amount

    def receive_payment(self, amount: Money) -> None:
        _ensure_positive(amount)
        if amount > self.balance:
            raise BusinessRuleViolation(
                f"El abono ({amount.display()}) supera la deuda de «{self.name}» "
                f"({self.balance.display()})"
            )
        self.balance -= amount

    def reverse_charge(self, amount: Money) -> None:
        """Deshace un cargo (venta anulada). Si ya había pagado, queda saldo a favor."""
        _ensure_positive(amount)
        self.balance -= amount


class LedgerEntryType(str, Enum):
    CHARGE = "charge"
    PAYMENT = "payment"
    REVERSAL = "reversal"


@dataclass(kw_only=True, eq=False)
class LedgerEntry(Entity):
    """Movimiento del estado de cuenta del cliente."""

    customer_id: UUID
    type: LedgerEntryType
    amount: Money
    balance_after: Money
    user_id: UUID
    created_at: datetime
    sale_id: UUID | None = None
    note: str = ""
