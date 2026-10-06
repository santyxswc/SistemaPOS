"""Unidad de trabajo SQLite.

Cada operación abre su conexión con BEGIN IMMEDIATE: las escrituras quedan en fila
y dos cajeros nunca venden la misma última unidad de un producto.
"""

from __future__ import annotations

import sqlite3

from ....application.ports import EventPublisher, UnitOfWork
from .connection import connect
from .repositories import (
    SqliteCashSessionRepository,
    SqliteCategoryRepository,
    SqliteCustomerRepository,
    SqliteLedgerRepository,
    SqliteProductRepository,
    SqliteSaleRepository,
    SqliteSequenceRepository,
    SqliteSettingsRepository,
    SqliteStockMovementRepository,
    SqliteUserRepository,
)


class SqliteUnitOfWork(UnitOfWork):
    def __init__(self, database: str, publisher: EventPublisher | None = None) -> None:
        super().__init__(publisher)
        self._database = database
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> SqliteUnitOfWork:
        conn = connect(self._database)
        conn.execute("BEGIN IMMEDIATE")
        self._conn = conn
        self.settings = SqliteSettingsRepository(conn)
        self.sequences = SqliteSequenceRepository(conn)
        self.users = SqliteUserRepository(conn, self.track)
        self.categories = SqliteCategoryRepository(conn)
        self.products = SqliteProductRepository(conn, self.track)
        self.stock_movements = SqliteStockMovementRepository(conn)
        self.customers = SqliteCustomerRepository(conn, self.track)
        self.ledger = SqliteLedgerRepository(conn)
        self.cash_sessions = SqliteCashSessionRepository(conn, self.track)
        self.sales = SqliteSaleRepository(conn, self.track)
        return self

    def __exit__(self, *exc_info: object) -> None:
        try:
            super().__exit__(*exc_info)
        finally:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _commit(self) -> None:
        assert self._conn is not None, "La unidad de trabajo no está abierta"
        self._conn.execute("COMMIT")

    def rollback(self) -> None:
        if self._conn is not None and self._conn.in_transaction:
            self._conn.execute("ROLLBACK")
