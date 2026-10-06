"""Tiquete en ESC/POS, transportes a la impresora y casos de uso de impresión directa."""

import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from pos.application.receipts import Columns, ReceiptBuilder, Text
from pos.domain.printing import PrinterConfig, PrinterKind
from pos.domain.shared.errors import BusinessRuleViolation, PermissionDenied, ValidationError
from pos.infrastructure.printing.escpos import CODEPAGE_PC850, FEED_AND_CUT, INIT, OPEN_DRAWER, EscPosEncoder
from pos.infrastructure.printing.transports import (
    FileTransport,
    NetworkTransport,
    PrinterUnavailable,
    WindowsSpoolerTransport,
)

from ..support import ApiTestCase, PosTestCase

NETWORK = PrinterConfig(kind=PrinterKind.NETWORK, target="192.168.1.50")


class FakePrinter:
    def __init__(self):
        self.printed = []
        self.drawer_opened = 0
        self.fail_with: Exception | None = None

    def print(self, config, document, *, open_drawer=False):
        if self.fail_with:
            raise self.fail_with
        self.printed.append((config, document, open_drawer))

    def open_drawer(self, config):
        self.drawer_opened += 1

    def available_printers(self):
        return ["EPSON TM-T20III", "Microsoft Print to PDF"]


class PrinterConfigTests(unittest.TestCase):
    def test_validations(self):
        self.assertFalse(PrinterConfig().is_direct)
        self.assertEqual(PrinterConfig(kind="network", target="10.0.0.9:9101").network_address(), ("10.0.0.9", 9101))
        self.assertEqual(NETWORK.network_address(), ("192.168.1.50", 9100))
        for bad in ({"kind": "windows"}, {"kind": "network", "target": "999.1.1.1"},
                    {"kind": "network", "target": "10.0.0.9:puerto"}, {"width": 80}, {"kind": "fax"}):
            with self.subTest(bad), self.assertRaises(ValidationError):
                PrinterConfig(**bad)


class EscPosEncoderTests(unittest.TestCase):
    def test_columns_text_wrapping_and_spanish_characters(self):
        document = (
            ReceiptBuilder()
            .text("Panadería La Espiga", large=True)
            .columns("TOTAL", "$12.500")
            .columns("Un producto con un nombre larguísimo de verdad", "$1.000.000")
            .separator()
            .build()
        )
        data = EscPosEncoder(32).encode(document)

        self.assertTrue(data.startswith(INIT + CODEPAGE_PC850))
        self.assertTrue(data.endswith(FEED_AND_CUT))
        lines = data.decode("cp850", errors="replace").splitlines()
        self.assertIn("Panadería La", "".join(lines))  # grande: la mitad del ancho, se parte en dos líneas
        total = next(line for line in lines if "TOTAL" in line)
        total = total[total.index("TOTAL"):]  # sin los comandos de alineación que van antes
        self.assertEqual(len(total), 32)
        self.assertTrue(total.endswith("$12.500"))
        self.assertIn("ñ".encode("cp850"), EscPosEncoder(32).encode(ReceiptBuilder().text("ñ").build()))
        long_line = [line for line in lines if "$1.000.000" in line][0]
        self.assertTrue(long_line.endswith("$1.000.000"))

    def test_drawer_goes_first_and_qr_is_encoded(self):
        document = ReceiptBuilder().text("Hola").qr("CUFE: abc").build()
        data = EscPosEncoder().encode(document, open_drawer=True)
        self.assertEqual(data[len(INIT + CODEPAGE_PC850):][: len(OPEN_DRAWER)], OPEN_DRAWER)
        self.assertIn(b"\x1d(k\x0c\x001P0CUFE: abc", data)  # 9 bytes de datos + 3
        self.assertNotIn(OPEN_DRAWER, EscPosEncoder().encode(document))


class TransportTests(unittest.TestCase):
    def test_network_printer_receives_the_bytes(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        received = bytearray()

        def accept():
            connection, _ = server.accept()
            with connection:
                while chunk := connection.recv(4096):
                    received.extend(chunk)

        thread = threading.Thread(target=accept)
        thread.start()
        NetworkTransport("127.0.0.1", server.getsockname()[1]).send(b"\x1b@hola", job_name="prueba")
        thread.join(5)
        server.close()
        self.assertEqual(bytes(received), b"\x1b@hola")

    def test_unreachable_printers_give_a_clear_message(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        with self.assertRaisesRegex(PrinterUnavailable, "encendida"):
            NetworkTransport("127.0.0.1", free_port).send(b"x", job_name="prueba")

    def test_file_transport(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lp0"
            FileTransport(path).send(b"abc", job_name="prueba")
            self.assertEqual(path.read_bytes(), b"abc")

    @unittest.skipUnless(sys.platform == "win32", "solo en Windows")
    def test_windows_spooler_reports_missing_printer(self):
        with self.assertRaisesRegex(PrinterUnavailable, "No se encontró la impresora"):
            WindowsSpoolerTransport("Impresora que no existe 123").send(b"x", job_name="prueba")


class PrintingUseCaseTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.printer = FakePrinter()
        # El contenedor ya existe: se reemplaza la impresora de los casos de uso para las pruebas.
        from pos.application.use_cases import printing

        self.print_sale = printing.PrintSaleReceipt(self.c.uow_factory, self.printer)
        self.open_drawer = printing.OpenCashDrawer(self.c.uow_factory, self.printer)
        self.print_test = printing.PrintTestReceipt(self.c.uow_factory, self.printer, self.clock)
        self.rice = self.make_product()
        self.open_cash(self.admin)

    def use_printer(self, config: PrinterConfig = NETWORK) -> None:
        self.c.update_settings.execute(self.admin, {"printer": config})

    def test_cash_sale_prints_and_opens_the_drawer_but_a_copy_does_not(self):
        self.use_printer()
        sale = self.sell(self.admin, [(self.rice, "2")], [("efectivo", "10000")])

        self.print_sale.execute(self.admin, sale.id)
        self.print_sale.execute(self.admin, sale.id, copy=True)

        (_, receipt, drawer), (_, copy, copy_drawer) = self.printer.printed
        self.assertEqual((drawer, copy_drawer), (True, False))
        text = receipt.plain_text()
        self.assertIn("Tienda de prueba", text)
        self.assertIn("Venta #1", text)
        self.assertIn("Atendió: Dueña", text)
        self.assertIn(Columns("Vueltas", "$5.000", bold=True), receipt.items)
        self.assertIn(Text("*** COPIA ***", bold=True, align="center"), copy.items)

    def test_electronic_payment_does_not_open_the_drawer(self):
        self.use_printer()
        sale = self.sell(self.admin, [(self.rice, "1")], [("nequi", "2500")])
        self.print_sale.execute(self.admin, sale.id)
        self.assertFalse(self.printer.printed[0][2])

    def test_without_direct_printer_it_says_how_to_configure_it(self):
        sale = self.sell(self.admin, [(self.rice, "1")], [("efectivo", "2500")])
        with self.assertRaisesRegex(BusinessRuleViolation, "Impresora de tiquetes"):
            self.print_sale.execute(self.admin, sale.id)

    def test_drawer_and_test_page_permissions(self):
        self.use_printer()
        cashier = self.make_cashier()
        self.open_drawer.execute(cashier)
        self.assertEqual(self.printer.drawer_opened, 1)
        with self.assertRaises(PermissionDenied):
            self.print_test.execute(cashier)
        self.print_test.execute(self.admin, PrinterConfig(kind=PrinterKind.WINDOWS, target="EPSON"))
        self.assertEqual(self.printer.printed[-1][0].target, "EPSON")  # prueba antes de guardar

    def test_cashier_can_only_print_own_sales(self):
        self.use_printer()
        sale = self.sell(self.admin, [(self.rice, "1")], [("efectivo", "2500")])
        with self.assertRaises(PermissionDenied):
            self.print_sale.execute(self.make_cashier(), sale.id)


class PrintingApiTests(ApiTestCase):
    def test_printer_settings_round_trip_and_validation(self):
        saved = self.api("PATCH", "/api/v1/settings", json={"printer": {
            "kind": "network", "target": "192.168.1.50", "width": 32, "auto_print": True, "open_drawer": False,
        }})
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(self.api("GET", "/api/v1/settings").get_json()["printer"], {
            "kind": "network", "target": "192.168.1.50", "width": 32, "auto_print": True, "open_drawer": False,
        })
        bad = self.api("PATCH", "/api/v1/settings", json={"printer": {"kind": "windows", "target": ""}})
        self.assertEqual(bad.status_code, 400)
        unknown = self.api("POST", "/api/v1/printing/test", json={"printer": {"kind": "network", "color": "rojo"}})
        self.assertEqual(unknown.status_code, 400)

    def test_print_without_printer_is_a_business_rule(self):
        response = self.api("POST", "/api/v1/cash-drawer/open")
        self.assertEqual(response.status_code, 422)
        self.assertIn("Impresora de tiquetes", response.get_json()["error"]["message"])
