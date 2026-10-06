"""Migraciones versionadas con PRAGMA user_version.

Para cambiar el esquema se agrega una entrada nueva al final de MIGRATIONS; nunca
se edita una que ya se aplicó en un negocio.
"""

from __future__ import annotations

from .connection import connect

FK = "DEFERRABLE INITIALLY DEFERRED"

MIGRATIONS: list[str] = [
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
            conn.executescript(f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;")
            current = version
        return current
    finally:
        conn.close()
