"""Excel y CSV de punta a punta: plantilla, importación, exportación y reporte para el contador."""

import io
import unittest
import zipfile
from decimal import Decimal

from pos.presentation.spreadsheets import Sheet, read_rows, write_xlsx

from ..support import ApiTestCase


class SpreadsheetFormatTests(unittest.TestCase):
    def test_xlsx_round_trip_keeps_numbers_exact_and_row_numbers(self):
        data = write_xlsx([Sheet("Hoja", ["Código", "Precio"], [["A", Decimal("2500.5")], ["B", Decimal("0.1")]])])
        self.assertEqual(read_rows(data, "x.xlsx"), [(1, ["Código", "Precio"]), (2, ["A", Decimal("2500.5")]),
                                                     (3, ["B", Decimal("0.1")])])

    def test_numbers_are_written_without_scientific_notation(self):
        data = write_xlsx([Sheet("Hoja", ["Existencias"], [[Decimal("40.000").normalize()]])])
        sheet = zipfile.ZipFile(io.BytesIO(data)).read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("<v>40</v>", sheet)

    def test_csv_from_excel_in_spanish(self):
        data = "Código;Nombre;Precio\r\n\r\nA1;Café Águila;$2.500\r\n".encode("cp1252")
        self.assertEqual(read_rows(data, "productos.csv"), [(1, ["Código", "Nombre", "Precio"]),
                                                            (3, ["A1", "Café Águila", "$2.500"])])


class SpreadsheetApiTests(ApiTestCase):
    def upload(self, data, filename, **query):
        url = "/api/v1/products/import?" + "&".join(f"{key}={value}" for key, value in query.items())
        return self.api("POST", url, data={"file": (io.BytesIO(data), filename)},
                        content_type="multipart/form-data")

    def test_the_template_imports_cleanly(self):
        template = self.api("GET", "/api/v1/products/import-template")
        self.assertEqual(template.status_code, 200)
        self.assertIn("plantilla-productos.xlsx", template.headers["Content-Disposition"])

        preview = self.upload(template.data, "plantilla.xlsx").get_json()
        self.assertEqual((preview["dry_run"], preview["created"], preview["errors"]), (True, 3, []))
        self.assertEqual(self.api("GET", "/api/v1/products").get_json()["items"], [])

        done = self.upload(template.data, "plantilla.xlsx", dry_run="false").get_json()
        self.assertEqual(done["created"], 3)
        cheese = self.api("GET", "/api/v1/products/lookup?code=QUESO-CAMPESINO").get_json()
        self.assertEqual((cheese["unit"], cheese["stock"], cheese["price"]), ("kg", "5.5", "18000.00"))

    def test_csv_with_a_title_row_and_spanish_headers(self):
        csv_data = ("Inventario Tienda Rosa;;\nProducto;Precio de venta;Código de barras\n"
                    "Pan tajado;4.500;7701234\n").encode("utf-8-sig")
        report = self.upload(csv_data, "inventario.csv", dry_run="false").get_json()
        self.assertEqual((report["created"], report["errors"]), (1, []))

    def test_explains_files_it_cannot_use(self):
        no_headers = self.upload(b"hola;mundo\n1;2\n", "x.csv")
        self.assertEqual(no_headers.status_code, 400)
        self.assertIn("encabezados", no_headers.get_json()["error"]["message"])
        old_excel = self.upload(b"\xd0\xcf\x11\xe0", "viejo.xls")
        self.assertIn(".xls", old_excel.get_json()["error"]["message"])

    def test_export_edit_and_reimport_updates_prices(self):
        self.api("POST", "/api/v1/products", json={"sku": "PAN", "name": "Pan", "price": "500", "initial_stock": "10"})
        exported = self.api("GET", "/api/v1/products/export")
        rows = read_rows(exported.data, "productos.xlsx")
        self.assertEqual(rows[1][1][:3], ["PAN", "Pan", Decimal(500)])

        header, product = rows[0][1], list(rows[1][1])
        product[2] = Decimal(600)
        edited = write_xlsx([Sheet("Productos", header, [product])])
        report = self.upload(edited, "productos.xlsx", dry_run="false", update_existing="true").get_json()
        self.assertEqual((report["updated"], report["errors"]), (1, []))
        self.assertEqual(self.api("GET", "/api/v1/products/lookup?code=PAN").get_json()["price"], "600.00")

    def test_sales_report_for_the_accountant(self):
        product_id = self.api("POST", "/api/v1/products", json={
            "sku": "PAN", "name": "Pan", "price": "1190", "initial_stock": "10"}).get_json()["id"]
        self.api("POST", "/api/v1/cash-sessions", json={"opening_amount": "0"})
        self.api("POST", "/api/v1/sales", json={"items": [{"product_id": product_id, "quantity": 2}],
                                                "payments": [{"method": "efectivo", "amount": "5000"}]})

        response = self.api("GET", "/api/v1/reports/export")
        self.assertEqual(response.status_code, 200)
        names = zipfile.ZipFile(io.BytesIO(response.data)).namelist()
        self.assertEqual(len([name for name in names if name.startswith("xl/worksheets/")]), 4)
        summary = dict(cells[:2] for _, cells in read_rows(response.data, "r.xlsx")[1:])
        self.assertEqual((summary["Total vendido"], summary["Recibido en Efectivo"]), (Decimal(2380), Decimal(2380)))

    def test_cashiers_cannot_export_costs(self):
        self.api("POST", "/api/v1/users", json={"username": "caja", "full_name": "Caja", "password": "clave-segura-2"})
        token = self.login("caja", "clave-segura-2")
        self.assertEqual(self.api("GET", "/api/v1/products/export", token=token).status_code, 403)
