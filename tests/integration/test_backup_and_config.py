"""Respaldos de la base de datos y generación del archivo de configuración."""

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from pos.config import render_env
from pos.infrastructure.persistence.sqlite.backup import backup_database

from ..support import PosTestCase


class BackupTests(PosTestCase):
    def test_backup_is_a_complete_copy_even_with_the_system_running(self):
        self.make_product(sku="ARROZ")
        with tempfile.TemporaryDirectory() as folder, self.c.uow_factory(read_only=True):
            target = backup_database(self.c.config.database_path, folder, now=datetime(2026, 10, 5, 22, 30))
            self.assertEqual(target.name, "pos-20261005-223000.sqlite3")
            conn = sqlite3.connect(target)
            try:
                self.assertEqual(conn.execute("SELECT sku FROM products").fetchall(), [("ARROZ",)])
            finally:
                conn.close()

    def test_keeps_only_the_most_recent_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            start = datetime(2026, 10, 1)
            for day in range(5):
                backup_database(self.c.config.database_path, folder, now=start + timedelta(days=day), keep=3)
            names = sorted(path.name for path in Path(folder).iterdir())
        self.assertEqual(names, ["pos-20261003-000000.sqlite3", "pos-20261004-000000.sqlite3",
                                 "pos-20261005-000000.sqlite3"])


class RenderEnvTests(PosTestCase):
    def test_fills_existing_keys_and_keeps_comments(self):
        template = "# comentario\nPOS_ENV=development\nPOS_SECRET_KEY=\nPOS_PORT=8000\n"
        rendered = render_env(template, {"POS_ENV": "production", "POS_SECRET_KEY": "x" * 40, "POS_NUEVA": "1"})
        self.assertEqual(
            rendered, f"# comentario\nPOS_ENV=production\nPOS_SECRET_KEY={'x' * 40}\nPOS_PORT=8000\nPOS_NUEVA=1\n"
        )
