"""Ícono junto al reloj: menú, avisos e ícono, sin necesitar una pantalla."""

import contextlib
import importlib.util
import io
import tempfile
import threading
import unittest
from pathlib import Path

from pos.cli import build_parser
from pos.presentation.desktop.tray import TrayActions, announce_update, menu_entries

HAS_PILLOW = importlib.util.find_spec("PIL") is not None


def actions(**overrides) -> TrayActions:
    defaults = {
        "open_app": lambda: None,
        "backup_now": lambda: "Respaldo creado: pos-2026.sqlite3",
        "open_data_folder": lambda: None,
        "quit": lambda: None,
    }
    return TrayActions(**{**defaults, **overrides})


class TrayMenuTests(unittest.TestCase):
    def test_menu_opens_the_app_by_default_and_ends_with_shutdown(self):
        entries = menu_entries(actions(), notify=lambda _: None)
        self.assertEqual([e.label for e in entries], [
            "Abrir el punto de venta", "Respaldar ahora", "Abrir la carpeta de datos", "-", "Apagar el punto de venta",
        ])
        self.assertEqual([e.default for e in entries].count(True), 1)
        self.assertIsNone(entries[3].action)

    def test_backup_runs_in_background_and_reports_success_or_failure(self):
        messages, done = [], threading.Event()

        def notify(message):
            messages.append(message)
            done.set()

        def fail():
            raise OSError("disco lleno")

        menu_entries(actions(), notify)[1].action()
        self.assertTrue(done.wait(5))
        done.clear()
        menu_entries(actions(backup_now=fail), notify)[1].action()
        self.assertTrue(done.wait(5))
        self.assertEqual(messages, ["Respaldo creado: pos-2026.sqlite3", "No se pudo hacer el respaldo: disco lleno"])

    def test_update_notice_only_when_there_is_one_and_never_crashes(self):
        messages = []

        def offline():
            raise OSError("sin internet")

        announce_update(actions(update_message=lambda: "Hay una versión nueva: 0.4.0"), messages.append)
        announce_update(actions(), messages.append)
        announce_update(actions(update_message=offline), messages.append)
        self.assertEqual(messages, ["Hay una versión nueva: 0.4.0"])


@unittest.skipUnless(HAS_PILLOW, "Pillow solo se instala en Windows")
class IconTests(unittest.TestCase):
    def test_icon_is_drawn_and_saved_with_all_sizes(self):
        from PIL import Image

        from pos.presentation.desktop.icon import draw_icon, write_ico

        self.assertEqual(draw_icon(64).size, (64, 64))
        with tempfile.TemporaryDirectory() as folder:
            path = write_ico(Path(folder) / "icono.ico")
            with Image.open(path) as ico:
                self.assertIn((16, 16), ico.info["sizes"])
                self.assertIn((256, 256), ico.info["sizes"])


class CommandLineTests(unittest.TestCase):
    def test_start_chooses_tray_or_console(self):
        parser = build_parser()
        self.assertIsNone(parser.parse_args(["start"]).tray)  # decide según haya consola o no
        self.assertTrue(parser.parse_args(["start", "--tray"]).tray)
        self.assertFalse(parser.parse_args(["start", "--console"]).tray)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["start", "--tray", "--console"])

    def test_backup_can_show_the_result_in_a_window(self):
        self.assertTrue(build_parser().parse_args(["backup", "--avisar"]).notify)
        self.assertFalse(build_parser().parse_args(["backup"]).notify)
