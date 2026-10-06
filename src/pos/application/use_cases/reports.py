"""Reportes: resumen de ventas por día o mes, métodos de pago y productos más vendidos."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from ...domain.payments import PaymentKind
from ...domain.sales import Sale
from ...domain.shared.errors import ValidationError
from ...domain.shared.values import Money
from ...domain.users import Permission
from ..actor import Actor
from ..common import local_day_range, require_settings
from ..ports import UnitOfWorkFactory


@dataclass(frozen=True)
class PaymentTotal:
    code: str
    name: str
    kind: PaymentKind
    amount: Money


def summarize_payments(sales: Iterable[Sale]) -> list[PaymentTotal]:
    """Suma por método de pago lo realmente recibido (sin las vueltas), en orden de aparición."""
    totals: dict[str, PaymentTotal] = {}
    for sale in sales:
        if sale.is_voided:
            continue
        for payment in sale.applied_payments():
            current = totals.get(payment.method_code)
            amount = payment.amount if current is None else current.amount + payment.amount
            totals[payment.method_code] = PaymentTotal(
                code=payment.method_code, name=payment.method_name, kind=payment.kind, amount=amount
            )
    return list(totals.values())


@dataclass(frozen=True)
class PeriodTotal:
    period: str  # "2026-10-05" o "2026-10"
    sales_count: int
    total: Money


@dataclass(frozen=True)
class SalesSummary:
    date_from: date
    date_to: date
    group_by: str
    sales_count: int
    voided_count: int
    subtotal: Money
    tax_total: Money
    discount_total: Money
    total: Money
    average_ticket: Money
    by_payment_method: list[PaymentTotal]
    by_period: list[PeriodTotal]


_PERIOD_FORMATS = {"day": "%Y-%m-%d", "month": "%Y-%m"}


class GetSalesSummary:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, date_from: date, date_to: date, group_by: str = "day") -> SalesSummary:
        actor.require(Permission.VIEW_REPORTS)
        if group_by not in _PERIOD_FORMATS:
            raise ValidationError("Agrupe por 'day' (día) o 'month' (mes)")
        with self._uow(read_only=True) as uow:
            settings = require_settings(uow)
            start, end = local_day_range(date_from, date_to, settings.tzinfo)
            sales = uow.sales.find(start=start, end=end)

        completed = [sale for sale in sales if not sale.is_voided]
        total = Money.sum(sale.total for sale in completed)
        periods: dict[str, tuple[int, Money]] = {}
        for sale in sorted(completed, key=lambda s: s.created_at):
            key = sale.created_at.astimezone(settings.tzinfo).strftime(_PERIOD_FORMATS[group_by])
            count, amount = periods.get(key, (0, Money.zero()))
            periods[key] = (count + 1, amount + sale.total)

        return SalesSummary(
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            sales_count=len(completed),
            voided_count=len(sales) - len(completed),
            subtotal=Money.sum(sale.subtotal for sale in completed),
            tax_total=Money.sum(sale.tax_total for sale in completed),
            discount_total=Money.sum(sale.discount_total for sale in completed),
            total=total,
            average_ticket=Money(total.amount / len(completed)) if completed else Money.zero(),
            by_payment_method=summarize_payments(completed),
            by_period=[PeriodTotal(period=k, sales_count=c, total=a) for k, (c, a) in periods.items()],
        )


@dataclass(frozen=True)
class ProductSales:
    product_id: UUID
    sku: str
    description: str
    quantity: Decimal
    total: Money


class GetTopProducts:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, date_from: date, date_to: date, limit: int = 10) -> list[ProductSales]:
        actor.require(Permission.VIEW_REPORTS)
        with self._uow(read_only=True) as uow:
            settings = require_settings(uow)
            start, end = local_day_range(date_from, date_to, settings.tzinfo)
            sales = uow.sales.find(start=start, end=end)

        ranking: dict[UUID, ProductSales] = {}
        for sale in sales:
            if sale.is_voided:
                continue
            for line in sale.lines:
                current = ranking.get(line.product_id)
                ranking[line.product_id] = ProductSales(
                    product_id=line.product_id,
                    sku=line.sku,
                    description=line.description,
                    quantity=line.quantity + (current.quantity if current else Decimal(0)),
                    total=line.total + (current.total if current else Money.zero()),
                )
        ordered = sorted(ranking.values(), key=lambda item: (item.quantity, item.total), reverse=True)
        return ordered[: max(1, min(limit, 100))]
