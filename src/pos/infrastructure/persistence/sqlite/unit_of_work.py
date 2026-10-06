"""Unidad de trabajo SQLite.

Cada operación de escritura abre su conexión con BEGIN IMMEDIATE: las escrituras
quedan en fila y dos cajeros nunca venden la misma última unidad de un producto.
Las consultas usan una transacción de solo lectura que, en modo WAL, ve una foto
consistente de los datos sin bloquear ni esperar a quien escribe.
"""

from __future__ import annotations

import sqlite3

from ....application.ports import EventPublisher, UnitOfWork
from .connection import connect
from .report_queries import SqliteSalesReportQueries
from .repositories import (
    SqliteCashSessionRepository,
    SqliteCategoryRepository,
    SqliteCustomerRepository,
    SqliteLedgerRepository,
    SqliteLicenseRepository,
    SqliteProductRepository,
    SqliteSaleRepository,
    SqliteSequenceRepository,
    SqliteSettingsRepository,
    SqliteStockMovementRepository,
    SqliteUserRepository,
)
from .supplier_repositories import SqlitePurchaseRepository, SqliteSupplierLedgerRepository, SqliteSupplierRepository


class SqliteUnitOfWork(UnitOfWork):
    def __init__(self, database: str, publisher: EventPublisher | None = None, *, read_only: bool = False) -> None:
        super().__init__(publisher, read_only=read_only)
        self._database = database
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> SqliteUnitOfWork:
        conn = connect(self._database)
        if self.read_only:
            conn.execute("PRAGMA query_only = ON")  # la base de datos rechaza cualquier escritura
            conn.execute("BEGIN")
        else:
            conn.execute("BEGIN IMMEDIATE")
        self._conn = conn
        self.settings = SqliteSettingsRepository(conn)
        self.licensing = SqliteLicenseRepository(conn)
        self.sequences = SqliteSequenceRepository(conn)
        self.users = SqliteUserRepository(conn, self.track)
        self.categories = SqliteCategoryRepository(conn)
        self.products = SqliteProductRepository(conn, self.track)
        self.stock_movements = SqliteStockMovementRepository(conn)
        self.customers = SqliteCustomerRepository(conn, self.track)
        self.ledger = SqliteLedgerRepository(conn)
        self.suppliers = SqliteSupplierRepository(conn, self.track)
        self.supplier_ledger = SqliteSupplierLedgerRepository(conn)
        self.purchases = SqlitePurchaseRepository(conn, self.track)
        self.cash_sessions = SqliteCashSessionRepository(conn, self.track)
        self.sales = SqliteSaleRepository(conn, self.track)
        self.sales_reports = SqliteSalesReportQueries(conn)
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
