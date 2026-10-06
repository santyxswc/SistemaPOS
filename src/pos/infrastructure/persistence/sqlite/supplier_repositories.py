"""Repositorios SQLite de proveedores, compras y cuentas por pagar."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from ....application.ports import PurchaseFilter
from ....domain.shared.values import Money
from ....domain.suppliers import (
    Purchase,
    PurchaseLine,
    PurchasePaymentMode,
    Supplier,
    SupplierEntryType,
    SupplierLedgerEntry,
)
from .repositories import Track, _chunks, _dt, _like_terms, _placeholders, _str, _ts, _uuid, normalize_search

_ZERO = str(Money.zero().amount)  # "0.00": así se guarda una factura ya pagada


class SqliteSupplierRepository:
    def __init__(self, conn: sqlite3.Connection, track: Track) -> None:
        self._conn = conn
        self._track = track

    def add(self, supplier: Supplier) -> None:
        self._conn.execute(
            "INSERT INTO suppliers (id, name, document, contact_name, phone, email, address, notes, search_text, "
            "balance, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(supplier.id), *self._values(supplier), _ts(supplier.created_at)),
        )
        self._track(supplier)

    def save(self, supplier: Supplier) -> None:
        self._conn.execute(
            "UPDATE suppliers SET name = ?, document = ?, contact_name = ?, phone = ?, email = ?, address = ?, "
            "notes = ?, search_text = ?, balance = ?, active = ? WHERE id = ?",
            (*self._values(supplier), str(supplier.id)),
        )
        self._track(supplier)

    def get(self, supplier_id: UUID) -> Supplier | None:
        row = self._conn.execute("SELECT * FROM suppliers WHERE id = ?", (str(supplier_id),)).fetchone()
        return self._to_supplier(row) if row else None

    def get_by_document(self, document: str) -> Supplier | None:
        row = self._conn.execute("SELECT * FROM suppliers WHERE document = ?", (document.strip(),)).fetchone()
        return self._to_supplier(row) if row else None

    def search(
        self,
        *,
        text: str | None = None,
        include_inactive: bool = False,
        with_balance_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Supplier]:
        terms = _like_terms(text)
        conditions = ["search_text LIKE ? ESCAPE '\\'" for _ in terms]
        params: list[Any] = list(terms)
        if not include_inactive:
            conditions.append("active = 1")
        if with_balance_only:
            conditions.append("balance <> ?")
            params.append(_ZERO)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"SELECT * FROM suppliers {where} ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._to_supplier(row) for row in rows]

    @staticmethod
    def _values(supplier: Supplier) -> tuple[Any, ...]:
        return (
            supplier.name,
            supplier.document,
            supplier.contact_name,
            supplier.phone,
            supplier.email,
            supplier.address,
            supplier.notes,
            normalize_search(supplier.name, supplier.document, supplier.contact_name, supplier.phone),
            str(supplier.balance.amount),
            int(supplier.active),
        )

    @staticmethod
    def _to_supplier(row: sqlite3.Row) -> Supplier:
        return Supplier(
            id=UUID(row["id"]),
            name=row["name"],
            document=row["document"],
            contact_name=row["contact_name"],
            phone=row["phone"],
            email=row["email"],
            address=row["address"],
            notes=row["notes"],
            balance=Money(Decimal(row["balance"])),
            active=bool(row["active"]),
            created_at=_dt(row["created_at"]),
        )


class SqliteSupplierLedgerRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, entry: SupplierLedgerEntry) -> None:
        self._conn.execute(
            "INSERT INTO supplier_ledger (id, supplier_id, type, amount, balance_after, purchase_id, method, note, "
            "user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(entry.id),
                str(entry.supplier_id),
                entry.type.value,
                str(entry.amount.amount),
                str(entry.balance_after.amount),
                _str(entry.purchase_id),
                entry.method,
                entry.note,
                str(entry.user_id),
                _ts(entry.created_at),
            ),
        )

    def list_for_supplier(self, supplier_id: UUID, *, limit: int = 50) -> list[SupplierLedgerEntry]:
        rows = self._conn.execute(
            "SELECT * FROM supplier_ledger WHERE supplier_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (str(supplier_id), limit),
        ).fetchall()
        return [
            SupplierLedgerEntry(
                id=UUID(row["id"]),
                supplier_id=UUID(row["supplier_id"]),
                type=SupplierEntryType(row["type"]),
                amount=Money(Decimal(row["amount"])),
                balance_after=Money(Decimal(row["balance_after"])),
                purchase_id=_uuid(row["purchase_id"]),
                method=row["method"],
                note=row["note"],
                user_id=UUID(row["user_id"]),
                created_at=_dt(row["created_at"]),
            )
            for row in rows
        ]


class SqlitePurchaseRepository:
    def __init__(self, conn: sqlite3.Connection, track: Track) -> None:
        self._conn = conn
        self._track = track

    def add(self, purchase: Purchase) -> None:
        self._conn.execute(
            "INSERT INTO purchases (id, number, supplier_id, invoice_number, payment_mode, total, outstanding, "
            "due_date, note, user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(purchase.id),
                purchase.number,
                _str(purchase.supplier_id),
                purchase.invoice_number,
                purchase.payment_mode.value,
                str(purchase.total.amount),
                str(purchase.outstanding.amount),
                purchase.due_date.isoformat() if purchase.due_date else None,
                purchase.note,
                str(purchase.user_id),
                _ts(purchase.created_at),
            ),
        )
        self._conn.executemany(
            "INSERT INTO purchase_lines (purchase_id, position, product_id, sku, description, quantity, unit_cost) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (str(purchase.id), position, str(line.product_id), line.sku, line.description, str(line.quantity),
                 str(line.unit_cost.amount))
                for position, line in enumerate(purchase.lines)
            ],
        )
        self._track(purchase)

    def save(self, purchase: Purchase) -> None:
        self._conn.execute(
            "UPDATE purchases SET outstanding = ? WHERE id = ?", (str(purchase.outstanding.amount), str(purchase.id))
        )
        self._track(purchase)

    def get(self, purchase_id: UUID) -> Purchase | None:
        rows = self._conn.execute("SELECT * FROM purchases WHERE id = ?", (str(purchase_id),)).fetchall()
        found = self._hydrate(rows)
        return found[0] if found else None

    def find(self, where: PurchaseFilter, *, limit: int = 50, offset: int = 0) -> list[Purchase]:
        conditions: list[str] = []
        params: list[Any] = []
        if where.supplier_id is not None:
            conditions.append("supplier_id = ?")
            params.append(str(where.supplier_id))
        if where.pending_only or where.due_before is not None:
            conditions.append("outstanding <> ?")
            params.append(_ZERO)
        if where.due_before is not None:
            conditions.append("due_date IS NOT NULL AND due_date < ?")
            params.append(where.due_before.isoformat())
        if where.start is not None:
            conditions.append("created_at >= ?")
            params.append(_ts(where.start))
        if where.end is not None:
            conditions.append("created_at < ?")
            params.append(_ts(where.end))
        clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"SELECT * FROM purchases {clause} ORDER BY created_at DESC, number DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return self._hydrate(rows)

    def list_pending_for_supplier(self, supplier_id: UUID) -> list[Purchase]:
        rows = self._conn.execute(
            "SELECT * FROM purchases WHERE supplier_id = ? AND outstanding <> ? ORDER BY created_at",
            (str(supplier_id), _ZERO),
        ).fetchall()
        return self._hydrate(rows)

    def _hydrate(self, rows: Sequence[sqlite3.Row]) -> list[Purchase]:
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        lines: dict[str, list[PurchaseLine]] = {purchase_id: [] for purchase_id in ids}
        for chunk in _chunks(ids):
            line_rows = self._conn.execute(
                f"SELECT * FROM purchase_lines WHERE purchase_id IN ({_placeholders(len(chunk))}) "
                "ORDER BY purchase_id, position",
                tuple(chunk),
            ).fetchall()
            for line in line_rows:
                lines[line["purchase_id"]].append(
                    PurchaseLine(
                        product_id=UUID(line["product_id"]),
                        sku=line["sku"],
                        description=line["description"],
                        quantity=Decimal(line["quantity"]),
                        unit_cost=Money(Decimal(line["unit_cost"])),
                    )
                )
        return [
            Purchase(
                id=UUID(row["id"]),
                number=row["number"],
                supplier_id=_uuid(row["supplier_id"]),
                invoice_number=row["invoice_number"],
                payment_mode=PurchasePaymentMode(row["payment_mode"]),
                lines=lines[row["id"]],
                outstanding=Money(Decimal(row["outstanding"])),
                due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
                note=row["note"],
                user_id=UUID(row["user_id"]),
                created_at=_dt(row["created_at"]),
            )
            for row in rows
        ]
