"""Respaldos de la base de datos y generación del archivo de configuración."""

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from pos.config import render_env
from pos.domain.shared.errors import PermissionDenied, ValidationError
from pos.domain.shared.values import Money
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


class BackupServiceTests(PosTestCase):
    def backups_dir(self):
        return Path(self.c.config.database_path).parent / "backups"

    def test_closing_the_cash_register_makes_a_backup(self):
        cashier = self.make_cashier()
        self.open_cash(cashier)
        self.assertEqual(list(self.backups_dir().glob("pos-*.sqlite3")), [])

        self.c.close_cash_session.execute(cashier, counted_amount=Money.of("50000"))

        files = self.c.list_backups.execute(self.admin)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "pos-20261005-100000.sqlite3")  # 15:00 UTC = 10:00 en Bogotá

    def test_copies_to_the_extra_folder_configured_in_settings(self):
        with tempfile.TemporaryDirectory() as usb:
            self.c.update_settings.execute(self.admin, {"backup_folder": usb})
            result = self.c.run_backup.execute(self.admin)
            copy = Path(result.extra_copy)
            self.assertTrue(copy.is_file())
            self.assertEqual(copy.parent.name, "Respaldos Punto de Venta")
            self.assertIsNone(result.extra_error)

    def test_a_disconnected_usb_never_breaks_the_main_backup(self):
        with tempfile.TemporaryDirectory() as usb:
            self.c.update_settings.execute(self.admin, {"backup_folder": usb})
        # la "USB" ya no existe: se desconectó
        result = self.c.run_backup.execute_unattended()
        self.assertTrue((self.backups_dir() / result.file.name).is_file())
        self.assertIsNone(result.extra_copy)
        self.assertIn("No se pudo copiar", result.extra_error)

    def test_rejects_a_folder_that_does_not_exist(self):
        with self.assertRaisesRegex(ValidationError, "no existe"):
            self.c.update_settings.execute(self.admin, {"backup_folder": str(Path(tempfile.gettempdir()) / "no-hay")})
        with self.assertRaisesRegex(ValidationError, "ruta completa"):
            self.c.update_settings.execute(self.admin, {"backup_folder": "respaldos"})
        self.c.update_settings.execute(self.admin, {"backup_folder": ""})  # vacío = desactivar

    def test_only_who_manages_settings_can_back_up_on_demand(self):
        with self.assertRaises(PermissionDenied):
            self.c.run_backup.execute(self.make_cashier())
