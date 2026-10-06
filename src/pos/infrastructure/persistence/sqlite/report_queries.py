"""Reportes de ventas agregados por SQLite (modelo de lectura).

El dinero se guarda como texto decimal. Para sumarlo sin errores de redondeo se
convierte cada valor a centavos enteros (las cantidades a milésimas) y se suma en
enteros: es exacto mientras cada valor esté por debajo de 90 billones.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ....application.ports import PaymentTotal, ProductSales, SalesFilter, SalesTotals
from ....domain.payments import PaymentKind
from ....domain.sales import SaleStatus
from ....domain.shared.values import Money
from .repositories import _ts  # mismo formato con que se guardan las fechas

_COMPLETED = SaleStatus.COMPLETED.value
_VOIDED = SaleStatus.VOIDED.value


def _cents(column: str) -> str:
    return f"CAST(ROUND(CAST({column} AS REAL) * 100) AS INTEGER)"


def _thousandths(column: str) -> str:
    return f"CAST(ROUND(CAST({column} AS REAL) * 1000) AS INTEGER)"


def _money(cents: int | None) -> Money:
    return Money(Decimal(cents or 0) / 100)


def _conditions(where: SalesFilter) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if where.start is not None:
        conditions.append("s.created_at >= ?")
        params.append(_ts(where.start))
    if where.end is not None:
        conditions.append("s.created_at < ?")
        params.append(_ts(where.end))
    if where.cash_session_id is not None:
        conditions.append("s.cash_session_id = ?")
        params.append(str(where.cash_session_id))
    return conditions, params


def _completed(where: SalesFilter) -> tuple[str, list[Any]]:
    conditions, params = _conditions(where)
    return " AND ".join([f"s.status = '{_COMPLETED}'", *conditions]), params


class SqliteSalesReportQueries:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def totals(self, where: SalesFilter) -> SalesTotals:
        conditions, params = _conditions(where)
        clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        done = f"s.status = '{_COMPLETED}'"
        row = self._conn.execute(
            f"""
            SELECT
                COALESCE(SUM({done}), 0) AS sales_count,
                COALESCE(SUM(s.status = '{_VOIDED}'), 0) AS voided_count,
                SUM(CASE WHEN {done} THEN {_cents("s.subtotal")} END) AS subtotal,
                SUM(CASE WHEN {done} THEN {_cents("s.tax_total")} END) AS tax_total,
                SUM(CASE WHEN {done} THEN {_cents("s.discount_total")} END) AS discount_total,
                SUM(CASE WHEN {done} THEN {_cents("s.total")} END) AS total
            FROM sales s {clause}
            """,
            params,
        ).fetchone()
        return SalesTotals(
            sales_count=int(row["sales_count"]),
            voided_count=int(row["voided_count"]),
            subtotal=_money(row["subtotal"]),
            tax_total=_money(row["tax_total"]),
            discount_total=_money(row["discount_total"]),
            total=_money(row["total"]),
        )

    def totals_by_payment_method(self, where: SalesFilter) -> list[PaymentTotal]:
        clause, params = _completed(where)
        # Con MAX(), SQLite toma el nombre y el tipo de la venta más reciente:
        # si el método se renombró, el reporte muestra el nombre actual.
        rows = self._conn.execute(
            f"""
            SELECT p.method_code, p.method_name, p.kind, SUM({_cents("p.applied_amount")}) AS cents,
                   MAX(s.number) AS last_number
            FROM sale_payments p JOIN sales s ON s.id = p.sale_id
            WHERE {clause}
            GROUP BY p.method_code
            HAVING cents > 0
            ORDER BY cents DESC, p.method_code
            """,
            params,
        ).fetchall()
        return [
            PaymentTotal(
                code=row["method_code"],
                name=row["method_name"],
                kind=PaymentKind(row["kind"]),
                amount=_money(row["cents"]),
            )
            for row in rows
        ]

    def sale_amounts(self, where: SalesFilter) -> list[tuple[datetime, Money]]:
        clause, params = _completed(where)
        rows = self._conn.execute(
            f"SELECT s.created_at, s.total FROM sales s WHERE {clause} ORDER BY s.created_at", params
        ).fetchall()
        return [(datetime.fromisoformat(row["created_at"]), Money(Decimal(row["total"]))) for row in rows]

    def top_products(self, where: SalesFilter, limit: int) -> list[ProductSales]:
        clause, params = _completed(where)
        rows = self._conn.execute(
            f"""
            SELECT l.product_id, l.sku, l.description, SUM({_thousandths("l.quantity")}) AS quantity,
                   SUM({_cents("l.total")}) AS cents, MAX(s.number) AS last_number
            FROM sale_lines l JOIN sales s ON s.id = l.sale_id
            WHERE {clause}
            GROUP BY l.product_id
            ORDER BY quantity DESC, cents DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [
            ProductSales(
                product_id=UUID(row["product_id"]),
                sku=row["sku"],
                description=row["description"],
                quantity=Decimal(row["quantity"]) / 1000,
                total=_money(row["cents"]),
            )
            for row in rows
        ]
