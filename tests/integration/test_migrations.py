"""Las migraciones actualizan bases de datos de negocios que ya están en uso."""

import os
import sqlite3
import tempfile
import unittest

from pos.infrastructure.persistence.sqlite.connection import connect
from pos.infrastructure.persistence.sqlite.migrations import MIGRATIONS, migrate


class MigrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "pos.sqlite3")

    def test_upgrades_a_version_1_database_keeping_its_data(self):
        conn = connect(self.path)
        conn.executescript(f"BEGIN;\n{MIGRATIONS[0]}\nPRAGMA user_version = 1;\nCOMMIT;")
        conn.execute("INSERT INTO settings (key, value) VALUES ('business', '{}')")
        conn.close()

        self.assertEqual(migrate(self.path), len(MIGRATIONS))

        conn = connect(self.path)
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0], 1)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sales)")}
        self.assertIn("request_id", columns)

    def test_running_twice_changes_nothing(self):
        self.assertEqual(migrate(self.path), migrate(self.path))

    def test_request_id_is_unique(self):
        migrate(self.path)
        conn = connect(self.path)
        self.addCleanup(conn.close)
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(sales)")}
        self.assertIn("ux_sales_request_id", indexes)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("PRAGMA foreign_keys = OFF")
            for _ in range(2):
                conn.execute(
                    "INSERT INTO sales (id, number, status, cashier_id, cash_session_id, subtotal, tax_total, "
                    "discount_total, total, change_amount, note, created_at, void_reason, request_id) "
                    "VALUES (lower(hex(randomblob(16))), abs(random()), 'completed', 'u', 's', '0', '0', '0', "
                    "'0', '0', '', '2026-01-01', '', 'misma')"
                )
