"""Migraciones versionadas con PRAGMA user_version.

Para cambiar el esquema se agrega una entrada nueva al final de MIGRATIONS; nunca
se edita una que ya se aplicó en un negocio. Una migración es un script SQL o una
función que recibe la conexión (para transformar datos con las reglas del dominio).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from decimal import Decimal

from ....domain.payments import PaymentKind
from ....domain.sales import SalePayment, allocate_change
from ....domain.shared.values import Money
from .connection import connect

FK = "DEFERRABLE INITIALLY DEFERRED"

Migration = str | Callable[[sqlite3.Connection], None]


def _store_applied_payment_amounts(conn: sqlite3.Connection) -> None:
    """Guarda el monto neto (sin vueltas) de cada pago para que los reportes sumen en SQL."""
    conn.execute("ALTER TABLE sale_payments ADD COLUMN applied_amount TEXT")
    rows = conn.execute(
        "SELECT p.sale_id, p.position, p.method_code, p.method_name, p.kind, p.amount, s.change_amount "
        "FROM sale_payments p JOIN sales s ON s.id = p.sale_id ORDER BY p.sale_id, p.position"
    ).fetchall()
    by_sale: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_sale.setdefault(row["sale_id"], []).append(row)
    updates = []
    for sale_id, payment_rows in by_sale.items():
        payments = [
            SalePayment(
                method_code=row["method_code"],
                method_name=row["method_name"],
                kind=PaymentKind(row["kind"]),
                amount=Money(Decimal(row["amount"])),
            )
            for row in payment_rows
        ]
        change = Money(Decimal(payment_rows[0]["change_amount"]))
        for row, applied in zip(payment_rows, allocate_change(payments, change), strict=True):
            updates.append((str(applied.amount), sale_id, row["position"]))
    conn.executemany("UPDATE sale_payments SET applied_amount = ? WHERE sale_id = ? AND position = ?", updates)
    conn.execute("CREATE INDEX ix_sale_lines_product ON sale_lines(product_id)")


MIGRATIONS: list[Migration] = [
    f"""
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE sequences (
        name  TEXT PRIMARY KEY,
        value INTEGER NOT NULL
    );

    CREATE TABLE users (
        id            TEXT PRIMARY KEY,
        username      TEXT NOT NULL UNIQUE,
        full_name     TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role          TEXT NOT NULL,
        active        INTEGER NOT NULL,
        created_at    TEXT NOT NULL
    );

    CREATE TABLE categories (
        id         TEXT PRIMARY KEY,
        name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
        active     INTEGER NOT NULL
    );

    CREATE TABLE products (
        id          TEXT PRIMARY KEY,
        sku         TEXT NOT NULL UNIQUE,
        barcode     TEXT UNIQUE,
        name        TEXT NOT NULL,
        search_text TEXT NOT NULL,
        category_id TEXT REFERENCES categories(id) {FK},
        price       TEXT NOT NULL,
        cost        TEXT NOT NULL,
        tax_rate    TEXT NOT NULL,
        unit        TEXT NOT NULL,
        track_stock INTEGER NOT NULL,
        stock       TEXT NOT NULL,
        min_stock   TEXT NOT NULL,
        active      INTEGER NOT NULL,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    CREATE INDEX ix_products_name ON products(name);

    CREATE TABLE stock_movements (
        id          TEXT PRIMARY KEY,
        product_id  TEXT NOT NULL REFERENCES products(id) {FK},
        type        TEXT NOT NULL,
        quantity    TEXT NOT NULL,
        stock_after TEXT NOT NULL,
        unit_cost   TEXT,
        reference   TEXT,
        note        TEXT NOT NULL,
        user_id     TEXT NOT NULL REFERENCES users(id) {FK},
        created_at  TEXT NOT NULL
    );
    CREATE INDEX ix_stock_movements_product ON stock_movements(product_id, created_at);

    CREATE TABLE customers (
        id           TEXT PRIMARY KEY,
        name         TEXT NOT NULL,
        document     TEXT UNIQUE,
        phone        TEXT NOT NULL,
        email        TEXT NOT NULL,
        address      TEXT NOT NULL,
        search_text  TEXT NOT NULL,
        credit_limit TEXT NOT NULL,
        balance      TEXT NOT NULL,
        active       INTEGER NOT NULL,
        created_at   TEXT NOT NULL
    );

    CREATE TABLE cash_sessions (
        id             TEXT PRIMARY KEY,
        cashier_id     TEXT NOT NULL REFERENCES users(id) {FK},
        status         TEXT NOT NULL,
        opening_amount TEXT NOT NULL,
        opened_at      TEXT NOT NULL,
        closed_at      TEXT,
        counted_amount TEXT,
        closing_note   TEXT NOT NULL
    );
    -- Garantía en la base de datos: un cajero no puede tener dos cajas abiertas.
    CREATE UNIQUE INDEX ux_cash_sessions_one_open ON cash_sessions(cashier_id) WHERE status = 'open';

    CREATE TABLE cash_movements (
        id         TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES cash_sessions(id) {FK},
        type       TEXT NOT NULL,
        amount     TEXT NOT NULL,
        reference  TEXT,
        note       TEXT NOT NULL,
        user_id    TEXT NOT NULL REFERENCES users(id) {FK},
        created_at TEXT NOT NULL
    );
    CREATE INDEX ix_cash_movements_session ON cash_movements(session_id, created_at);

    CREATE TABLE sales (
        id              TEXT PRIMARY KEY,
        number          INTEGER NOT NULL UNIQUE,
        status          TEXT NOT NULL,
        cashier_id      TEXT NOT NULL REFERENCES users(id) {FK},
        cash_session_id TEXT NOT NULL REFERENCES cash_sessions(id) {FK},
        customer_id     TEXT REFERENCES customers(id) {FK},
        subtotal        TEXT NOT NULL,
        tax_total       TEXT NOT NULL,
        discount_total  TEXT NOT NULL,
        total           TEXT NOT NULL,
        change_amount   TEXT NOT NULL,
        note            TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        voided_at       TEXT,
        voided_by       TEXT REFERENCES users(id) {FK},
        void_reason     TEXT NOT NULL
    );
    CREATE INDEX ix_sales_created_at ON sales(created_at);
    CREATE INDEX ix_sales_session ON sales(cash_session_id);

    CREATE TABLE sale_lines (
        sale_id     TEXT NOT NULL REFERENCES sales(id) {FK},
        position    INTEGER NOT NULL,
        product_id  TEXT NOT NULL REFERENCES products(id) {FK},
        sku         TEXT NOT NULL,
        description TEXT NOT NULL,
        quantity    TEXT NOT NULL,
        unit_price  TEXT NOT NULL,
        discount    TEXT NOT NULL,
        tax_rate    TEXT NOT NULL,
        base        TEXT NOT NULL,
        tax         TEXT NOT NULL,
        total       TEXT NOT NULL,
        PRIMARY KEY (sale_id, position)
    );

    CREATE TABLE sale_payments (
        sale_id     TEXT NOT NULL REFERENCES sales(id) {FK},
        position    INTEGER NOT NULL,
        method_code TEXT NOT NULL,
        method_name TEXT NOT NULL,
        kind        TEXT NOT NULL,
        amount      TEXT NOT NULL,
        PRIMARY KEY (sale_id, position)
    );

    CREATE TABLE customer_ledger (
        id            TEXT PRIMARY KEY,
        customer_id   TEXT NOT NULL REFERENCES customers(id) {FK},
        type          TEXT NOT NULL,
        amount        TEXT NOT NULL,
        balance_after TEXT NOT NULL,
        sale_id       TEXT REFERENCES sales(id) {FK},
        note          TEXT NOT NULL,
        user_id       TEXT NOT NULL REFERENCES users(id) {FK},
        created_at    TEXT NOT NULL
    );
    CREATE INDEX ix_customer_ledger_customer ON customer_ledger(customer_id, created_at);
    """,
    # 2: clave de idempotencia para que un reintento del cajero no duplique la venta
    """
    ALTER TABLE sales ADD COLUMN request_id TEXT;
    CREATE UNIQUE INDEX ux_sales_request_id ON sales(request_id) WHERE request_id IS NOT NULL;
    """,
    # 3: montos netos por pago para reportes agregados en SQL
    _store_applied_payment_amounts,
    # 4: proveedores, compras de mercancía y cuentas por pagar
    f"""
    CREATE TABLE suppliers (
        id           TEXT PRIMARY KEY,
        name         TEXT NOT NULL,
        document     TEXT UNIQUE,
        contact_name TEXT NOT NULL,
        phone        TEXT NOT NULL,
        email        TEXT NOT NULL,
        address      TEXT NOT NULL,
        notes        TEXT NOT NULL,
        search_text  TEXT NOT NULL,
        balance      TEXT NOT NULL,
        active       INTEGER NOT NULL,
        created_at   TEXT NOT NULL
    );

    CREATE TABLE purchases (
        id             TEXT PRIMARY KEY,
        number         INTEGER NOT NULL UNIQUE,
        supplier_id    TEXT REFERENCES suppliers(id) {FK},
        invoice_number TEXT NOT NULL,
        payment_mode   TEXT NOT NULL,
        total          TEXT NOT NULL,
        outstanding    TEXT NOT NULL,
        due_date       TEXT,
        note           TEXT NOT NULL,
        user_id        TEXT NOT NULL REFERENCES users(id) {FK},
        created_at     TEXT NOT NULL
    );
    CREATE INDEX ix_purchases_created_at ON purchases(created_at);
    CREATE INDEX ix_purchases_supplier ON purchases(supplier_id, created_at);
    CREATE INDEX ix_purchases_pending ON purchases(due_date) WHERE outstanding <> '0.00';

    CREATE TABLE purchase_lines (
        purchase_id TEXT NOT NULL REFERENCES purchases(id) {FK},
        position    INTEGER NOT NULL,
        product_id  TEXT NOT NULL REFERENCES products(id) {FK},
        sku         TEXT NOT NULL,
        description TEXT NOT NULL,
        quantity    TEXT NOT NULL,
        unit_cost   TEXT NOT NULL,
        PRIMARY KEY (purchase_id, position)
    );

    CREATE TABLE supplier_ledger (
        id            TEXT PRIMARY KEY,
        supplier_id   TEXT NOT NULL REFERENCES suppliers(id) {FK},
        type          TEXT NOT NULL,
        amount        TEXT NOT NULL,
        balance_after TEXT NOT NULL,
        purchase_id   TEXT REFERENCES purchases(id) {FK},
        method        TEXT NOT NULL,
        note          TEXT NOT NULL,
        user_id       TEXT NOT NULL REFERENCES users(id) {FK},
        created_at    TEXT NOT NULL
    );
    CREATE INDEX ix_supplier_ledger_supplier ON supplier_ledger(supplier_id, created_at);
    """,
    # 5: bandeja de salida de documentos electrónicos (facturación DIAN)
    f"""
    CREATE TABLE electronic_documents (
        id                 TEXT PRIMARY KEY,
        sale_id            TEXT NOT NULL REFERENCES sales(id) {FK},
        sale_number        INTEGER NOT NULL,
        kind               TEXT NOT NULL,
        status             TEXT NOT NULL,
        attempts           INTEGER NOT NULL,
        next_attempt_at    TEXT,
        last_error         TEXT NOT NULL,
        cufe               TEXT,
        qr_data            TEXT NOT NULL,
        provider_reference TEXT NOT NULL,
        accepted_at        TEXT,
        created_at         TEXT NOT NULL
    );
    -- Un documento de cada tipo por venta: la venta y, si se anula, su nota crédito.
    CREATE UNIQUE INDEX ux_electronic_documents_sale_kind ON electronic_documents(sale_id, kind);
    CREATE INDEX ix_electronic_documents_due ON electronic_documents(next_attempt_at) WHERE status = 'pending';
    CREATE INDEX ix_electronic_documents_status ON electronic_documents(status, created_at);
    """,
    # 6: logo del negocio (una sola fila), dentro de la base de datos para que viaje con los respaldos
    """
    CREATE TABLE business_logo (
        id           INTEGER PRIMARY KEY CHECK (id = 1),
        content_type TEXT NOT NULL,
        data         BLOB NOT NULL,
        updated_at   TEXT NOT NULL
    );
    """,
]


def migrate(database: str) -> int:
    """Aplica las migraciones pendientes. Devuelve la versión final del esquema."""
    conn = connect(database)
    try:
        if database != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")  # lecturas sin bloquear a quien escribe
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            if isinstance(script, str):
                conn.executescript(f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;")
            else:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    script(conn)
                    conn.execute(f"PRAGMA user_version = {version}")
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            current = version
        return current
    finally:
        conn.close()
