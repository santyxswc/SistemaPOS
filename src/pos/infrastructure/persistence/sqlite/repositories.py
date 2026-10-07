"""Repositorios SQLite: traducen agregados del dominio a filas y viceversa.

El dinero y las cantidades se guardan como TEXT para conservar la exactitud de
Decimal; las fechas en UTC con formato ISO 8601 (ordenables como texto).
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import unicodedata
from collections.abc import Callable, Collection, Iterable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ....domain.branding import Logo
from ....domain.cash import CashMovement, CashMovementType, CashSession, CashSessionStatus
from ....domain.catalog import Category, Product, Unit
from ....domain.customers import Customer, LedgerEntry, LedgerEntryType
from ....domain.inventory import MovementType, StockMovement
from ....domain.payments import PaymentKind, PaymentMethodConfig
from ....domain.printing import PrinterConfig
from ....domain.sales import Sale, SaleLine, SalePayment, SaleStatus, allocate_change
from ....domain.settings import BusinessSettings
from ....domain.shared.entity import AggregateRoot
from ....domain.shared.values import Money, TaxRate
from ....domain.users import Permission, Role, RolePermissions, User

Track = Callable[[AggregateRoot], None]
_CHUNK = 500  # límite seguro de parámetros por consulta en SQLite


# --- conversiones ------------------------------------------------------------------


def _ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _dt(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _money(text: str | None) -> Money | None:
    return Money(Decimal(text)) if text is not None else None


def _uuid(text: str | None) -> UUID | None:
    return UUID(text) if text else None


def _str(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def normalize_search(*parts: str | None) -> str:
    """'Café Águila' → 'cafe aguila': búsquedas sin importar tildes ni mayúsculas."""
    text = " ".join(part for part in parts if part)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def _like_terms(text: str | None) -> list[str]:
    terms = normalize_search(text).split()
    return ["%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for term in terms]


def _chunks(values: Sequence[Any]) -> Iterable[Sequence[Any]]:
    for start in range(0, len(values), _CHUNK):
        yield values[start : start + _CHUNK]


def _placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))


# --- configuración y consecutivos ----------------------------------------------------------


class SqliteSettingsRepository:
    _KEY = "business"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self) -> BusinessSettings | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (self._KEY,)).fetchone()
        if row is None:
            return None
        stored = json.loads(row["value"])
        # Ignora claves de versiones anteriores (p. ej. max_users, que ahora viene de la licencia).
        known = {f.name for f in dataclasses.fields(BusinessSettings)}
        data = {key: value for key, value in stored.items() if key in known}
        data["default_tax_rate"] = TaxRate(Decimal(data["default_tax_rate"]))
        data["payment_methods"] = tuple(
            PaymentMethodConfig(code=m["code"], name=m["name"], kind=PaymentKind(m["kind"]), active=m["active"])
            for m in data["payment_methods"]
        )
        if "printer" in data:
            printer = data["printer"]
            printer_fields = {f.name for f in dataclasses.fields(PrinterConfig)}
            data["printer"] = PrinterConfig(**{k: v for k, v in printer.items() if k in printer_fields})
        return BusinessSettings(**data)

    def save(self, settings: BusinessSettings) -> None:
        data = {
            "business_name": settings.business_name,
            "tax_id": settings.tax_id,
            "address": settings.address,
            "phone": settings.phone,
            "currency": settings.currency,
            "timezone": settings.timezone,
            "prices_include_tax": settings.prices_include_tax,
            "default_tax_rate": str(settings.default_tax_rate.percent),
            "allow_negative_stock": settings.allow_negative_stock,
            "credit_sales_enabled": settings.credit_sales_enabled,
            "receipt_footer": settings.receipt_footer,
            "backup_folder": settings.backup_folder,
            "payment_methods": [
                {"code": m.code, "name": m.name, "kind": m.kind.value, "active": m.active}
                for m in settings.payment_methods
            ],
            "printer": {
                "kind": settings.printer.kind.value,
                "target": settings.printer.target,
                "width": settings.printer.width,
                "auto_print": settings.printer.auto_print,
                "open_drawer": settings.printer.open_drawer,
            },
        }
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self._KEY, json.dumps(data, ensure_ascii=False)),
        )


class SqliteLogoRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self) -> Logo | None:
        row = self._conn.execute("SELECT content_type, data, updated_at FROM business_logo WHERE id = 1").fetchone()
        if row is None:
            return None
        return Logo(content_type=row["content_type"], data=bytes(row["data"]), updated_at=_dt(row["updated_at"]))

    def save(self, logo: Logo) -> None:
        self._conn.execute(
            """
            INSERT INTO business_logo (id, content_type, data, updated_at) VALUES (1, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                content_type = excluded.content_type, data = excluded.data, updated_at = excluded.updated_at
            """,
            (logo.content_type, logo.data, _ts(logo.updated_at)),
        )

    def delete(self) -> None:
        self._conn.execute("DELETE FROM business_logo")


class SqliteLicenseRepository:
    """Usa la misma tabla clave-valor de la configuración, con claves propias."""

    _CODE = "license_code"
    _INSTALLED_AT = "installed_at"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_code(self) -> str | None:
        return self._get(self._CODE)

    def save_code(self, code: str) -> None:
        self._set(self._CODE, code)

    def get_installed_at(self) -> datetime | None:
        return _dt(self._get(self._INSTALLED_AT))

    def save_installed_at(self, at: datetime) -> None:
        self._set(self._INSTALLED_AT, _ts(at))

    def _get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set(self, key: str, value: str | None) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


class SqliteRolePermissionsRepository:
    """Guarda en la tabla clave-valor solo los roles que el negocio personalizó."""

    _KEY = "role_permissions"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self) -> RolePermissions:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (self._KEY,)).fetchone()
        if row is None:
            return RolePermissions()
        known_roles = {role.value for role in Role}
        known_permissions = {permission.value for permission in Permission}
        stored = json.loads(row["value"])
        # Ignora permisos o roles que una versión futura haya retirado.
        return RolePermissions({
            Role(role): frozenset(Permission(p) for p in permissions if p in known_permissions)
            for role, permissions in stored.items()
            if role in known_roles
        })

    def save(self, policy: RolePermissions) -> None:
        data = {role.value: sorted(p.value for p in permissions) for role, permissions in policy.granted.items()}
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self._KEY, json.dumps(data)),
        )


class SqliteSequenceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def next_value(self, name: str) -> int:
        self._conn.execute("INSERT OR IGNORE INTO sequences (name, value) VALUES (?, 0)", (name,))
        self._conn.execute("UPDATE sequences SET value = value + 1 WHERE name = ?", (name,))
        return int(self._conn.execute("SELECT value FROM sequences WHERE name = ?", (name,)).fetchone()[0])


# --- usuarios -------------------------------------------------------------------------------


class SqliteUserRepository:
    def __init__(self, conn: sqlite3.Connection, track: Track) -> None:
        self._conn = conn
        self._track = track

    def add(self, user: User) -> None:
        self._conn.execute(
            "INSERT INTO users (id, username, full_name, password_hash, role, active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(user.id), user.username, user.full_name, user.password_hash, user.role.value,
             int(user.active), _ts(user.created_at)),
        )
        self._track(user)

    def save(self, user: User) -> None:
        self._conn.execute(
            "UPDATE users SET full_name = ?, password_hash = ?, role = ?, active = ? WHERE id = ?",
            (user.full_name, user.password_hash, user.role.value, int(user.active), str(user.id)),
        )
        self._track(user)

    def get(self, user_id: UUID) -> User | None:
        return self._one("SELECT * FROM users WHERE id = ?", (str(user_id),))

    def get_by_username(self, username: str) -> User | None:
        return self._one("SELECT * FROM users WHERE username = ?", (username,))

    def list_all(self) -> list[User]:
        rows = self._conn.execute("SELECT * FROM users ORDER BY active DESC, username").fetchall()
        return [self._to_user(row) for row in rows]

    def count(self, *, active_only: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM users" + (" WHERE active = 1" if active_only else "")
        return int(self._conn.execute(sql).fetchone()[0])

    def _one(self, sql: str, params: tuple[Any, ...]) -> User | None:
        row = self._conn.execute(sql, params).fetchone()
        return self._to_user(row) if row else None

    @staticmethod
    def _to_user(row: sqlite3.Row) -> User:
        return User(
            id=UUID(row["id"]),
            username=row["username"],
            full_name=row["full_name"],
            password_hash=row["password_hash"],
            role=Role(row["role"]),
            active=bool(row["active"]),
            created_at=_dt(row["created_at"]),
        )


# --- catálogo e inventario ----------------------------------------------------------------------


class SqliteCategoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, category: Category) -> None:
        self._conn.execute(
            "INSERT INTO categories (id, name, active) VALUES (?, ?, ?)",
            (str(category.id), category.name, int(category.active)),
        )

    def get(self, category_id: UUID) -> Category | None:
        row = self._conn.execute("SELECT * FROM categories WHERE id = ?", (str(category_id),)).fetchone()
        return self._to_category(row) if row else None

    def get_by_name(self, name: str) -> Category | None:
        row = self._conn.execute("SELECT * FROM categories WHERE name = ?", (name.strip(),)).fetchone()
        return self._to_category(row) if row else None

    def list_all(self, *, include_inactive: bool = False) -> list[Category]:
        sql = "SELECT * FROM categories" + ("" if include_inactive else " WHERE active = 1") + " ORDER BY name"
        return [self._to_category(row) for row in self._conn.execute(sql).fetchall()]

    @staticmethod
    def _to_category(row: sqlite3.Row) -> Category:
        return Category(id=UUID(row["id"]), name=row["name"], active=bool(row["active"]))


class SqliteProductRepository:
    def __init__(self, conn: sqlite3.Connection, track: Track) -> None:
        self._conn = conn
        self._track = track

    def add(self, product: Product) -> None:
        self._conn.execute(
            "INSERT INTO products (id, sku, barcode, name, search_text, category_id, price, cost, tax_rate, "
            "unit, track_stock, stock, min_stock, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(product.id), *self._values(product), _ts(product.created_at), _ts(product.updated_at)),
        )
        self._track(product)

    def save(self, product: Product) -> None:
        self._conn.execute(
            "UPDATE products SET sku = ?, barcode = ?, name = ?, search_text = ?, category_id = ?, price = ?, "
            "cost = ?, tax_rate = ?, unit = ?, track_stock = ?, stock = ?, min_stock = ?, active = ?, "
            "updated_at = ? WHERE id = ?",
            (*self._values(product), _ts(product.updated_at), str(product.id)),
        )
        self._track(product)

    def get(self, product_id: UUID) -> Product | None:
        return self._one("SELECT * FROM products WHERE id = ?", (str(product_id),))

    def get_many(self, product_ids: Collection[UUID]) -> dict[UUID, Product]:
        ids = [str(product_id) for product_id in product_ids]
        found: dict[UUID, Product] = {}
        for chunk in _chunks(ids):
            rows = self._conn.execute(
                f"SELECT * FROM products WHERE id IN ({_placeholders(len(chunk))})", tuple(chunk)
            ).fetchall()
            for row in rows:
                product = self._to_product(row)
                found[product.id] = product
        return found

    def get_by_sku(self, sku: str) -> Product | None:
        return self._one("SELECT * FROM products WHERE sku = ?", (sku.strip().upper(),))

    def get_by_barcode(self, barcode: str) -> Product | None:
        return self._one("SELECT * FROM products WHERE barcode = ?", (barcode.strip(),))

    def search(
        self,
        *,
        text: str | None = None,
        category_id: UUID | None = None,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Product]:
        conditions: list[str] = []
        params: list[Any] = []
        for term in _like_terms(text):
            conditions.append("search_text LIKE ? ESCAPE '\\'")
            params.append(term)
        if category_id is not None:
            conditions.append("category_id = ?")
            params.append(str(category_id))
        if not include_inactive:
            conditions.append("active = 1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"SELECT * FROM products {where} ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._to_product(row) for row in rows]

    def list_low_stock(self) -> list[Product]:
        rows = self._conn.execute(
            "SELECT * FROM products WHERE active = 1 AND track_stock = 1 "
            "AND CAST(stock AS REAL) <= CAST(min_stock AS REAL) ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [product for product in map(self._to_product, rows) if product.is_low_stock]

    def list_all(self, *, include_inactive: bool = False) -> list[Product]:
        where = "" if include_inactive else "WHERE active = 1"
        rows = self._conn.execute(f"SELECT * FROM products {where} ORDER BY name COLLATE NOCASE").fetchall()
        return [self._to_product(row) for row in rows]

    def _one(self, sql: str, params: tuple[Any, ...]) -> Product | None:
        row = self._conn.execute(sql, params).fetchone()
        return self._to_product(row) if row else None

    @staticmethod
    def _values(product: Product) -> tuple[Any, ...]:
        return (
            product.sku,
            product.barcode,
            product.name,
            normalize_search(product.name, product.sku, product.barcode),
            _str(product.category_id),
            str(product.price.amount),
            str(product.cost.amount),
            str(product.tax_rate.percent),
            product.unit.value,
            int(product.track_stock),
            str(product.stock),
            str(product.min_stock),
            int(product.active),
        )

    @staticmethod
    def _to_product(row: sqlite3.Row) -> Product:
        return Product(
            id=UUID(row["id"]),
            sku=row["sku"],
            barcode=row["barcode"],
            name=row["name"],
            category_id=_uuid(row["category_id"]),
            price=Money(Decimal(row["price"])),
            cost=Money(Decimal(row["cost"])),
            tax_rate=TaxRate(Decimal(row["tax_rate"])),
            unit=Unit(row["unit"]),
            track_stock=bool(row["track_stock"]),
            stock=Decimal(row["stock"]),
            min_stock=Decimal(row["min_stock"]),
            active=bool(row["active"]),
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )


class SqliteStockMovementRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, movement: StockMovement) -> None:
        self._conn.execute(
            "INSERT INTO stock_movements (id, product_id, type, quantity, stock_after, unit_cost, reference, "
            "note, user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(movement.id),
                str(movement.product_id),
                movement.type.value,
                str(movement.quantity),
                str(movement.stock_after),
                str(movement.unit_cost.amount) if movement.unit_cost else None,
                movement.reference,
                movement.note,
                str(movement.user_id),
                _ts(movement.created_at),
            ),
        )

    def list_for_product(self, product_id: UUID, *, limit: int = 50) -> list[StockMovement]:
        rows = self._conn.execute(
            "SELECT * FROM stock_movements WHERE product_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (str(product_id), limit),
        ).fetchall()
        return [
            StockMovement(
                id=UUID(row["id"]),
                product_id=UUID(row["product_id"]),
                type=MovementType(row["type"]),
                quantity=Decimal(row["quantity"]),
                stock_after=Decimal(row["stock_after"]),
                unit_cost=_money(row["unit_cost"]),
                reference=row["reference"],
                note=row["note"],
                user_id=UUID(row["user_id"]),
                created_at=_dt(row["created_at"]),
            )
            for row in rows
        ]


# --- clientes ---------------------------------------------------------------------------------


class SqliteCustomerRepository:
    def __init__(self, conn: sqlite3.Connection, track: Track) -> None:
        self._conn = conn
        self._track = track

    def add(self, customer: Customer) -> None:
        self._conn.execute(
            "INSERT INTO customers (id, name, document, phone, email, address, search_text, credit_limit, "
            "balance, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(customer.id), *self._values(customer), _ts(customer.created_at)),
        )
        self._track(customer)

    def save(self, customer: Customer) -> None:
        self._conn.execute(
            "UPDATE customers SET name = ?, document = ?, phone = ?, email = ?, address = ?, search_text = ?, "
            "credit_limit = ?, balance = ?, active = ? WHERE id = ?",
            (*self._values(customer), str(customer.id)),
        )
        self._track(customer)

    def get(self, customer_id: UUID) -> Customer | None:
        row = self._conn.execute("SELECT * FROM customers WHERE id = ?", (str(customer_id),)).fetchone()
        return self._to_customer(row) if row else None

    def get_by_document(self, document: str) -> Customer | None:
        row = self._conn.execute("SELECT * FROM customers WHERE document = ?", (document.strip(),)).fetchone()
        return self._to_customer(row) if row else None

    def search(
        self, *, text: str | None = None, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> list[Customer]:
        conditions = ["search_text LIKE ? ESCAPE '\\'" for _ in _like_terms(text)]
        params: list[Any] = list(_like_terms(text))
        if not include_inactive:
            conditions.append("active = 1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"SELECT * FROM customers {where} ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._to_customer(row) for row in rows]

    @staticmethod
    def _values(customer: Customer) -> tuple[Any, ...]:
        return (
            customer.name,
            customer.document,
            customer.phone,
            customer.email,
            customer.address,
            normalize_search(customer.name, customer.document, customer.phone),
            str(customer.credit_limit.amount),
            str(customer.balance.amount),
            int(customer.active),
        )

    @staticmethod
    def _to_customer(row: sqlite3.Row) -> Customer:
        return Customer(
            id=UUID(row["id"]),
            name=row["name"],
            document=row["document"],
            phone=row["phone"],
            email=row["email"],
            address=row["address"],
            credit_limit=Money(Decimal(row["credit_limit"])),
            balance=Money(Decimal(row["balance"])),
            active=bool(row["active"]),
            created_at=_dt(row["created_at"]),
        )


class SqliteLedgerRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, entry: LedgerEntry) -> None:
        self._conn.execute(
            "INSERT INTO customer_ledger (id, customer_id, type, amount, balance_after, sale_id, note, user_id, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(entry.id),
                str(entry.customer_id),
                entry.type.value,
                str(entry.amount.amount),
                str(entry.balance_after.amount),
                _str(entry.sale_id),
                entry.note,
                str(entry.user_id),
                _ts(entry.created_at),
            ),
        )

    def list_for_customer(self, customer_id: UUID, *, limit: int = 50) -> list[LedgerEntry]:
        rows = self._conn.execute(
            "SELECT * FROM customer_ledger WHERE customer_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (str(customer_id), limit),
        ).fetchall()
        return [
            LedgerEntry(
                id=UUID(row["id"]),
                customer_id=UUID(row["customer_id"]),
                type=LedgerEntryType(row["type"]),
                amount=Money(Decimal(row["amount"])),
                balance_after=Money(Decimal(row["balance_after"])),
                sale_id=_uuid(row["sale_id"]),
                note=row["note"],
                user_id=UUID(row["user_id"]),
                created_at=_dt(row["created_at"]),
            )
            for row in rows
        ]


# --- caja -----------------------------------------------------------------------------------------


class SqliteCashSessionRepository:
    def __init__(self, conn: sqlite3.Connection, track: Track) -> None:
        self._conn = conn
        self._track = track

    def add(self, session: CashSession) -> None:
        self._conn.execute(
            "INSERT INTO cash_sessions (id, cashier_id, status, opening_amount, opened_at, closed_at, "
            "counted_amount, closing_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(session.id),
                str(session.cashier_id),
                session.status.value,
                str(session.opening_amount.amount),
                _ts(session.opened_at),
                _ts(session.closed_at),
                str(session.counted_amount.amount) if session.counted_amount else None,
                session.closing_note,
            ),
        )
        self._insert_movements(session)
        self._track(session)

    def save(self, session: CashSession) -> None:
        self._conn.execute(
            "UPDATE cash_sessions SET status = ?, closed_at = ?, counted_amount = ?, closing_note = ? WHERE id = ?",
            (
                session.status.value,
                _ts(session.closed_at),
                str(session.counted_amount.amount) if session.counted_amount else None,
                session.closing_note,
                str(session.id),
            ),
        )
        self._insert_movements(session)
        self._track(session)

    def get(self, session_id: UUID) -> CashSession | None:
        rows = self._conn.execute("SELECT * FROM cash_sessions WHERE id = ?", (str(session_id),)).fetchall()
        return next(iter(self._hydrate(rows)), None)

    def get_open_for_cashier(self, cashier_id: UUID) -> CashSession | None:
        rows = self._conn.execute(
            "SELECT * FROM cash_sessions WHERE cashier_id = ? AND status = 'open'", (str(cashier_id),)
        ).fetchall()
        return next(iter(self._hydrate(rows)), None)

    def list_recent(self, *, limit: int = 50, offset: int = 0) -> list[CashSession]:
        rows = self._conn.execute(
            "SELECT * FROM cash_sessions ORDER BY opened_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return self._hydrate(rows)

    def _insert_movements(self, session: CashSession) -> None:
        # Los movimientos son inmutables: solo se insertan los que todavía no existen.
        self._conn.executemany(
            "INSERT OR IGNORE INTO cash_movements (id, session_id, type, amount, reference, note, user_id, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (str(m.id), str(session.id), m.type.value, str(m.amount.amount), m.reference, m.note,
                 str(m.user_id), _ts(m.created_at))
                for m in session.movements
            ],
        )

    def _hydrate(self, rows: Sequence[sqlite3.Row]) -> list[CashSession]:
        sessions = [
            CashSession(
                id=UUID(row["id"]),
                cashier_id=UUID(row["cashier_id"]),
                status=CashSessionStatus(row["status"]),
                opening_amount=Money(Decimal(row["opening_amount"])),
                opened_at=_dt(row["opened_at"]),
                closed_at=_dt(row["closed_at"]),
                counted_amount=_money(row["counted_amount"]),
                closing_note=row["closing_note"],
            )
            for row in rows
        ]
        by_id = {str(session.id): session for session in sessions}
        for chunk in _chunks(list(by_id)):
            movement_rows = self._conn.execute(
                f"SELECT * FROM cash_movements WHERE session_id IN ({_placeholders(len(chunk))}) "
                "ORDER BY created_at, rowid",
                tuple(chunk),
            ).fetchall()
            for row in movement_rows:
                by_id[row["session_id"]].movements.append(
                    CashMovement(
                        id=UUID(row["id"]),
                        type=CashMovementType(row["type"]),
                        amount=Money(Decimal(row["amount"])),
                        reference=row["reference"],
                        note=row["note"],
                        user_id=UUID(row["user_id"]),
                        created_at=_dt(row["created_at"]),
                    )
                )
        return sessions


# --- ventas ---------------------------------------------------------------------------------------


class SqliteSaleRepository:
    def __init__(self, conn: sqlite3.Connection, track: Track) -> None:
        self._conn = conn
        self._track = track

    def add(self, sale: Sale) -> None:
        self._conn.execute(
            "INSERT INTO sales (id, number, status, cashier_id, cash_session_id, customer_id, subtotal, tax_total, "
            "discount_total, total, change_amount, note, created_at, voided_at, voided_by, void_reason, "
            "request_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(sale.id),
                sale.number,
                sale.status.value,
                str(sale.cashier_id),
                str(sale.cash_session_id),
                _str(sale.customer_id),
                str(sale.subtotal.amount),
                str(sale.tax_total.amount),
                str(sale.discount_total.amount),
                str(sale.total.amount),
                str(sale.change.amount),
                sale.note,
                _ts(sale.created_at),
                _ts(sale.voided_at),
                _str(sale.voided_by),
                sale.void_reason,
                sale.request_id,
            ),
        )
        self._conn.executemany(
            "INSERT INTO sale_lines (sale_id, position, product_id, sku, description, quantity, unit_price, "
            "discount, tax_rate, base, tax, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (str(sale.id), position, str(line.product_id), line.sku, line.description, str(line.quantity),
                 str(line.unit_price.amount), str(line.discount.amount), str(line.tax_rate.percent),
                 str(line.base.amount), str(line.tax.amount), str(line.total.amount))
                for position, line in enumerate(sale.lines)
            ],
        )
        self._conn.executemany(
            "INSERT INTO sale_payments (sale_id, position, method_code, method_name, kind, amount, applied_amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (str(sale.id), position, p.method_code, p.method_name, p.kind.value, str(p.amount.amount),
                 str(applied.amount))
                for position, (p, applied) in enumerate(
                    zip(sale.payments, allocate_change(sale.payments, sale.change), strict=True)
                )
            ],
        )
        self._track(sale)

    def save(self, sale: Sale) -> None:
        # Líneas y pagos son inmutables; después de creada solo cambia el estado (anulación).
        self._conn.execute(
            "UPDATE sales SET status = ?, voided_at = ?, voided_by = ?, void_reason = ? WHERE id = ?",
            (sale.status.value, _ts(sale.voided_at), _str(sale.voided_by), sale.void_reason, str(sale.id)),
        )
        self._track(sale)

    def get(self, sale_id: UUID) -> Sale | None:
        rows = self._conn.execute("SELECT * FROM sales WHERE id = ?", (str(sale_id),)).fetchall()
        return next(iter(self._hydrate(rows)), None)

    def get_by_request_id(self, request_id: str) -> Sale | None:
        rows = self._conn.execute("SELECT * FROM sales WHERE request_id = ?", (request_id,)).fetchall()
        return next(iter(self._hydrate(rows)), None)

    def find(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        cashier_id: UUID | None = None,
        cash_session_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Sale]:
        conditions: list[str] = []
        params: list[Any] = []
        if start is not None:
            conditions.append("created_at >= ?")
            params.append(_ts(start))
        if end is not None:
            conditions.append("created_at < ?")
            params.append(_ts(end))
        if cashier_id is not None:
            conditions.append("cashier_id = ?")
            params.append(str(cashier_id))
        if cash_session_id is not None:
            conditions.append("cash_session_id = ?")
            params.append(str(cash_session_id))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM sales {where} ORDER BY number DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        return self._hydrate(self._conn.execute(sql, tuple(params)).fetchall())

    def _hydrate(self, rows: Sequence[sqlite3.Row]) -> list[Sale]:
        ids = [row["id"] for row in rows]
        lines: dict[str, list[SaleLine]] = {sale_id: [] for sale_id in ids}
        payments: dict[str, list[SalePayment]] = {sale_id: [] for sale_id in ids}
        for chunk in _chunks(ids):
            marks = _placeholders(len(chunk))
            for row in self._conn.execute(
                f"SELECT * FROM sale_lines WHERE sale_id IN ({marks}) ORDER BY sale_id, position", tuple(chunk)
            ):
                lines[row["sale_id"]].append(
                    SaleLine(
                        product_id=UUID(row["product_id"]),
                        sku=row["sku"],
                        description=row["description"],
                        quantity=Decimal(row["quantity"]),
                        unit_price=Money(Decimal(row["unit_price"])),
                        discount=Money(Decimal(row["discount"])),
                        tax_rate=TaxRate(Decimal(row["tax_rate"])),
                        base=Money(Decimal(row["base"])),
                        tax=Money(Decimal(row["tax"])),
                        total=Money(Decimal(row["total"])),
                    )
                )
            for row in self._conn.execute(
                f"SELECT * FROM sale_payments WHERE sale_id IN ({marks}) ORDER BY sale_id, position", tuple(chunk)
            ):
                payments[row["sale_id"]].append(
                    SalePayment(
                        method_code=row["method_code"],
                        method_name=row["method_name"],
                        kind=PaymentKind(row["kind"]),
                        amount=Money(Decimal(row["amount"])),
                    )
                )
        return [
            Sale(
                id=UUID(row["id"]),
                number=row["number"],
                status=SaleStatus(row["status"]),
                cashier_id=UUID(row["cashier_id"]),
                cash_session_id=UUID(row["cash_session_id"]),
                customer_id=_uuid(row["customer_id"]),
                lines=tuple(lines[row["id"]]),
                payments=tuple(payments[row["id"]]),
                subtotal=Money(Decimal(row["subtotal"])),
                tax_total=Money(Decimal(row["tax_total"])),
                discount_total=Money(Decimal(row["discount_total"])),
                total=Money(Decimal(row["total"])),
                change=Money(Decimal(row["change_amount"])),
                note=row["note"],
                created_at=_dt(row["created_at"]),
                voided_at=_dt(row["voided_at"]),
                voided_by=_uuid(row["voided_by"]),
                void_reason=row["void_reason"],
                request_id=row["request_id"],
            )
            for row in rows
        ]
