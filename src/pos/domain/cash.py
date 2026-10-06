"""Caja: apertura con base, movimientos de efectivo y cierre con arqueo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from .shared.entity import AggregateRoot, Entity
from .shared.errors import BusinessRuleViolation, ValidationError
from .shared.events import DomainEvent
from .shared.values import Money, required_text


class CashSessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CashMovementType(StrEnum):
    SALE = "sale"
    SALE_VOID = "sale_void"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    CREDIT_COLLECTION = "credit_collection"
    SUPPLIER_PAYMENT = "supplier_payment"


@dataclass(frozen=True, kw_only=True)
class CashSessionClosed(DomainEvent):
    session_id: UUID
    cashier_id: UUID
    expected: Money
    counted: Money
    difference: Money


@dataclass(kw_only=True, eq=False)
class CashMovement(Entity):
    type: CashMovementType
    amount: Money  # con signo: positivo entra a la caja, negativo sale
    user_id: UUID
    created_at: datetime
    reference: str | None = None
    note: str = ""


@dataclass(kw_only=True, eq=False)
class CashSession(AggregateRoot):
    cashier_id: UUID
    opening_amount: Money
    opened_at: datetime
    status: CashSessionStatus = CashSessionStatus.OPEN
    closed_at: datetime | None = None
    counted_amount: Money | None = None
    closing_note: str = ""
    movements: list[CashMovement] = field(default_factory=list)

    @classmethod
    def open(cls, *, cashier_id: UUID, opening_amount: Money, at: datetime) -> CashSession:
        if opening_amount.is_negative:
            raise ValidationError("La base de caja no puede ser negativa")
        return cls(cashier_id=cashier_id, opening_amount=opening_amount, opened_at=at)

    @property
    def is_open(self) -> bool:
        return self.status is CashSessionStatus.OPEN

    @property
    def expected_cash(self) -> Money:
        """Efectivo que debería haber en el cajón según el sistema."""
        return self.opening_amount + Money.sum(movement.amount for movement in self.movements)

    @property
    def difference(self) -> Money | None:
        """Sobrante (positivo) o faltante (negativo) al cierre."""
        if self.counted_amount is None:
            return None
        return self.counted_amount - self.expected_cash

    def register_sale(self, *, sale_number: int, cash_amount: Money, user_id: UUID, at: datetime) -> None:
        if cash_amount.is_zero:
            return
        self._add(CashMovementType.SALE, cash_amount, user_id, at, reference=f"Venta #{sale_number}")

    def register_sale_void(self, *, sale_number: int, cash_amount: Money, user_id: UUID, at: datetime) -> None:
        if cash_amount.is_zero:
            return
        self._ensure_cash_available(cash_amount)
        self._add(CashMovementType.SALE_VOID, -cash_amount, user_id, at, reference=f"Anulación venta #{sale_number}")

    def register_credit_collection(self, *, amount: Money, customer_name: str, user_id: UUID, at: datetime) -> None:
        self._ensure_positive(amount)
        self._add(CashMovementType.CREDIT_COLLECTION, amount, user_id, at, reference=f"Abono de {customer_name}")

    def pay_supplier(self, *, amount: Money, reference: str, user_id: UUID, at: datetime) -> CashMovement:
        """Pago a un proveedor con el efectivo del cajón (compra de contado o abono a la deuda)."""
        self._ensure_positive(amount)
        self._ensure_cash_available(amount)
        return self._add(CashMovementType.SUPPLIER_PAYMENT, -amount, user_id, at, reference=reference)

    def deposit(self, *, amount: Money, note: str, user_id: UUID, at: datetime) -> CashMovement:
        self._ensure_positive(amount)
        return self._add(CashMovementType.DEPOSIT, amount, user_id, at, note=required_text(note, "motivo"))

    def withdraw(self, *, amount: Money, note: str, user_id: UUID, at: datetime) -> CashMovement:
        self._ensure_positive(amount)
        reason = required_text(note, "motivo")
        self._ensure_cash_available(amount)
        return self._add(CashMovementType.WITHDRAWAL, -amount, user_id, at, note=reason)

    def close(self, *, counted_amount: Money, at: datetime, note: str = "") -> None:
        self._ensure_open()
        if counted_amount.is_negative:
            raise ValidationError("El efectivo contado no puede ser negativo")
        self.status = CashSessionStatus.CLOSED
        self.closed_at = at
        self.counted_amount = counted_amount
        self.closing_note = (note or "").strip()
        self.record(
            CashSessionClosed(
                occurred_at=at,
                session_id=self.id,
                cashier_id=self.cashier_id,
                expected=self.expected_cash,
                counted=counted_amount,
                difference=counted_amount - self.expected_cash,
            )
        )

    def _add(
        self,
        movement_type: CashMovementType,
        amount: Money,
        user_id: UUID,
        at: datetime,
        *,
        reference: str | None = None,
        note: str = "",
    ) -> CashMovement:
        self._ensure_open()
        movement = CashMovement(
            type=movement_type, amount=amount, user_id=user_id, created_at=at, reference=reference, note=note
        )
        self.movements.append(movement)
        return movement

    def _ensure_open(self) -> None:
        if not self.is_open:
            raise BusinessRuleViolation("La caja ya está cerrada")

    def _ensure_cash_available(self, amount: Money) -> None:
        if amount > self.expected_cash:
            raise BusinessRuleViolation(
                f"No hay suficiente efectivo en caja: hay {self.expected_cash.display()}"
            )

    @staticmethod
    def _ensure_positive(amount: Money) -> None:
        if not amount.is_positive:
            raise ValidationError("El monto debe ser mayor que cero")
