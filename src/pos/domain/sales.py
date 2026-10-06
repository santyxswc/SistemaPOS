"""Ventas: líneas con impuestos calculados, pagos mixtos, vueltas y anulación."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from .payments import PaymentKind, behavior_for
from .shared.entity import AggregateRoot
from .shared.errors import BusinessRuleViolation, ValidationError
from .shared.events import DomainEvent
from .shared.values import Money, TaxRate
from .taxes import TaxPolicy


class SaleStatus(StrEnum):
    COMPLETED = "completed"
    VOIDED = "voided"


@dataclass(frozen=True, kw_only=True)
class SaleCompleted(DomainEvent):
    sale_id: UUID
    number: int
    total: Money
    customer_id: UUID | None


@dataclass(frozen=True, kw_only=True)
class SaleVoided(DomainEvent):
    sale_id: UUID
    number: int
    reason: str


@dataclass(frozen=True, kw_only=True)
class SaleLine:
    """Línea de venta. Guarda una foto del producto (nombre y precio) al momento de vender."""

    product_id: UUID
    sku: str
    description: str
    quantity: Decimal
    unit_price: Money
    discount: Money
    tax_rate: TaxRate
    base: Money
    tax: Money
    total: Money

    @classmethod
    def build(
        cls,
        *,
        product_id: UUID,
        sku: str,
        description: str,
        quantity: Decimal,
        unit_price: Money,
        discount: Money,
        tax_rate: TaxRate,
        tax_policy: TaxPolicy,
    ) -> SaleLine:
        gross = unit_price * quantity
        if discount.is_negative:
            raise ValidationError("El descuento no puede ser negativo")
        if discount > gross:
            raise ValidationError(f"El descuento de «{description}» supera el valor de la línea")
        breakdown = tax_policy.breakdown(gross - discount, tax_rate)
        return cls(
            product_id=product_id,
            sku=sku,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            discount=discount,
            tax_rate=tax_rate,
            base=breakdown.base,
            tax=breakdown.tax,
            total=breakdown.total,
        )


@dataclass(frozen=True, kw_only=True)
class SalePayment:
    """Lo que entregó el cliente con un método de pago (el efectivo puede incluir vueltas)."""

    method_code: str
    method_name: str
    kind: PaymentKind
    amount: Money


@dataclass(kw_only=True, eq=False)
class Sale(AggregateRoot):
    number: int
    cashier_id: UUID
    cash_session_id: UUID
    lines: tuple[SaleLine, ...]
    payments: tuple[SalePayment, ...]
    subtotal: Money
    tax_total: Money
    discount_total: Money
    total: Money
    change: Money
    created_at: datetime
    customer_id: UUID | None = None
    request_id: str | None = None  # clave de idempotencia enviada por la caja
    status: SaleStatus = SaleStatus.COMPLETED
    note: str = ""
    voided_at: datetime | None = None
    voided_by: UUID | None = None
    void_reason: str = ""

    @classmethod
    def create(
        cls,
        *,
        number: int,
        cashier_id: UUID,
        cash_session_id: UUID,
        lines: Sequence[SaleLine],
        payments: Sequence[SalePayment],
        at: datetime,
        customer_id: UUID | None = None,
        note: str = "",
        request_id: str | None = None,
    ) -> Sale:
        if not lines:
            raise ValidationError("La venta debe tener al menos un producto")
        if not payments:
            raise ValidationError("Registre al menos un pago")
        if any(not payment.amount.is_positive for payment in payments):
            raise ValidationError("Cada pago debe ser mayor que cero")

        total = Money.sum(line.total for line in lines)
        paid = Money.sum(payment.amount for payment in payments)
        if paid < total:
            raise BusinessRuleViolation(f"Pago incompleto: faltan {(total - paid).display()}")

        change = paid - total
        change_capacity = Money.sum(p.amount for p in payments if behavior_for(p.kind).can_give_change)
        if change > change_capacity:
            raise BusinessRuleViolation(
                "Solo los pagos en efectivo pueden dar vueltas: revise los montos de los otros métodos"
            )
        if customer_id is None and any(behavior_for(p.kind).requires_customer for p in payments):
            raise BusinessRuleViolation("Para vender fiado debe seleccionar un cliente")

        sale = cls(
            number=number,
            cashier_id=cashier_id,
            cash_session_id=cash_session_id,
            customer_id=customer_id,
            lines=tuple(lines),
            payments=tuple(payments),
            subtotal=Money.sum(line.base for line in lines),
            tax_total=Money.sum(line.tax for line in lines),
            discount_total=Money.sum(line.discount for line in lines),
            total=total,
            change=change,
            created_at=at,
            note=(note or "").strip(),
            request_id=request_id,
        )
        sale.record(
            SaleCompleted(occurred_at=at, sale_id=sale.id, number=number, total=total, customer_id=customer_id)
        )
        return sale

    @property
    def is_voided(self) -> bool:
        return self.status is SaleStatus.VOIDED

    def applied_payments(self) -> list[SalePayment]:
        """Pagos netos: a los pagos que dan vueltas se les descuenta el cambio entregado."""
        remaining_change = self.change
        applied: list[SalePayment] = []
        for payment in self.payments:
            amount = payment.amount
            if remaining_change.is_positive and behavior_for(payment.kind).can_give_change:
                deducted = min(amount, remaining_change)
                amount -= deducted
                remaining_change -= deducted
            if amount.is_positive:
                applied.append(dataclasses.replace(payment, amount=amount))
        return applied

    @property
    def cash_in_drawer(self) -> Money:
        """Efectivo que la venta deja en el cajón (recibido menos vueltas)."""
        return Money.sum(p.amount for p in self.applied_payments() if behavior_for(p.kind).goes_to_cash_drawer)

    @property
    def credit_amount(self) -> Money:
        """Parte de la venta que queda como deuda del cliente."""
        return Money.sum(p.amount for p in self.applied_payments() if behavior_for(p.kind).requires_customer)

    def void(self, *, by: UUID, reason: str, at: datetime) -> None:
        if self.is_voided:
            raise BusinessRuleViolation(f"La venta #{self.number} ya está anulada")
        cleaned = (reason or "").strip()
        if not cleaned:
            raise ValidationError("Indique el motivo de la anulación")
        self.status = SaleStatus.VOIDED
        self.voided_at = at
        self.voided_by = by
        self.void_reason = cleaned
        self.record(SaleVoided(occurred_at=at, sale_id=self.id, number=self.number, reason=cleaned))
