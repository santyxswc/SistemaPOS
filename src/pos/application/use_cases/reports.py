"""Reportes: resumen de ventas por día o mes, métodos de pago y productos más vendidos.

Las cifras salen del modelo de lectura (`uow.sales_reports`): la base de datos suma
y agrupa, así un reporte de un año no carga cada venta en memoria.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, tzinfo

from ...domain.shared.errors import ValidationError
from ...domain.shared.values import Money
from ...domain.users import Permission
from ..actor import Actor
from ..common import local_day_range, require_settings
from ..ports import PaymentTotal, ProductSales, SaleRow, SalesFilter, UnitOfWorkFactory

__all__ = [
    "ExportSalesReport",
    "GetSalesSummary",
    "GetTopProducts",
    "PaymentTotal",
    "PeriodTotal",
    "ProductSales",
    "SaleRow",
    "SalesReportExport",
    "SalesSummary",
]

MAX_EXPORTED_SALES = 100_000


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
            where = SalesFilter(start=start, end=end)
            totals = uow.sales_reports.totals(where)
            by_method = uow.sales_reports.totals_by_payment_method(where)
            amounts = uow.sales_reports.sale_amounts(where)

        # El día o mes se calcula en la zona horaria del negocio, no en UTC.
        periods: dict[str, tuple[int, Money]] = {}
        for created_at, amount in amounts:
            key = created_at.astimezone(settings.tzinfo).strftime(_PERIOD_FORMATS[group_by])
            count, subtotal = periods.get(key, (0, Money.zero()))
            periods[key] = (count + 1, subtotal + amount)

        count = totals.sales_count
        return SalesSummary(
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            sales_count=count,
            voided_count=totals.voided_count,
            subtotal=totals.subtotal,
            tax_total=totals.tax_total,
            discount_total=totals.discount_total,
            total=totals.total,
            average_ticket=Money(totals.total.amount / count) if count else Money.zero(),
            by_payment_method=by_method,
            by_period=[PeriodTotal(period=k, sales_count=c, total=a) for k, (c, a) in periods.items()],
        )


class GetTopProducts:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, date_from: date, date_to: date, limit: int = 10) -> list[ProductSales]:
        actor.require(Permission.VIEW_REPORTS)
        with self._uow(read_only=True) as uow:
            settings = require_settings(uow)
            start, end = local_day_range(date_from, date_to, settings.tzinfo)
            return uow.sales_reports.top_products(SalesFilter(start=start, end=end), max(1, min(limit, 100)))


@dataclass(frozen=True)
class SalesReportExport:
    summary: SalesSummary
    sales: list[SaleRow]
    products: list[ProductSales]
    timezone: tzinfo


class ExportSalesReport:
    """Lo que pide el contador: resumen, cada venta con sus impuestos y lo vendido por producto."""

    def __init__(self, uow: UnitOfWorkFactory, summary: GetSalesSummary) -> None:
        self._uow = uow
        self._summary = summary

    def execute(self, actor: Actor, date_from: date, date_to: date) -> SalesReportExport:
        actor.require(Permission.VIEW_REPORTS)
        summary = self._summary.execute(actor, date_from, date_to, group_by="day")
        with self._uow(read_only=True) as uow:
            settings = require_settings(uow)
            start, end = local_day_range(date_from, date_to, settings.tzinfo)
            where = SalesFilter(start=start, end=end)
            sales = uow.sales_reports.sale_rows(where, MAX_EXPORTED_SALES)
            products = uow.sales_reports.top_products(where, 100_000)
        return SalesReportExport(summary=summary, sales=sales, products=products, timezone=settings.tzinfo)
