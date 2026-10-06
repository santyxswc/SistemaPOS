"""Carga masiva de productos: vista previa, errores por fila y actualización de precios."""

from decimal import Decimal

from pos.application.use_cases.catalog_import import ProductImportRow
from pos.domain.shared.errors import PermissionDenied, ValidationError
from pos.domain.shared.values import Money

from ..support import PosTestCase


def row(line, **values):
    return ProductImportRow(line=line, values=values)


class ImportProductsTests(PosTestCase):
    def test_preview_reports_everything_and_saves_nothing(self):
        rows = [
            row(2, sku="arroz-500", name="Arroz Diana", price="$2.500", stock="40", category="Granos"),
            row(3, sku="QUESO", name="Queso campesino", price="18.000", unit="Kilos", stock="5,5"),
            row(4, sku="MALO", name="Sin precio"),
        ]
        report = self.c.import_products.execute(self.admin, rows, dry_run=True)

        self.assertEqual((report.created, len(report.errors)), (2, 1))
        self.assertEqual((report.errors[0].line, report.errors[0].message), (4, "Falta el precio de venta"))
        self.assertEqual(report.new_categories, ["Granos"])
        self.assertEqual(self.c.search_products.execute(), [])
        self.assertEqual(self.c.list_categories.execute(), [])

    def test_import_saves_valid_rows_with_initial_stock_and_kardex(self):
        rows = [
            row(2, sku="ARROZ-500", name="Arroz Diana", price="2.500", cost="1.900", tax_rate="0", stock="40",
                barcode=Decimal("7702511000014"), category="Granos"),
            row(3, sku="LECHE", name="Leche", price="4900", tax_rate="exento", category="granos"),  # misma categoría
            row(4, sku="ARROZ-500", name="Repetido", price="1"),
        ]
        report = self.c.import_products.execute(self.admin, rows, dry_run=False)

        self.assertEqual((report.created, [e.line for e in report.errors]), (2, [4]))
        self.assertIn("fila 2", report.errors[0].message)
        rice = self.c.find_product_by_code.execute("7702511000014")
        self.assertEqual((rice.price, rice.cost, rice.stock), (Money.of(2500), Money.of(1900), Decimal(40)))
        self.assertEqual(len(self.c.list_categories.execute()), 1)
        movements = self.c.list_stock_movements.execute(self.admin, rice.id)
        self.assertEqual([(m.type.value, m.quantity) for m in movements], [("initial", Decimal(40))])

    def test_existing_products_are_skipped_unless_updating_and_stock_is_never_overwritten(self):
        self.make_product(sku="ARROZ-500", price="2500", stock="10")
        changed = [row(2, sku="ARROZ-500", name="Arroz Diana 500 g", price="2.700", stock="999")]

        skipped = self.c.import_products.execute(self.admin, changed, dry_run=False)
        self.assertEqual(skipped.skipped_existing, 1)

        updated = self.c.import_products.execute(self.admin, changed, update_existing=True, dry_run=False)
        self.assertEqual(updated.updated, 1)
        product = self.c.find_product_by_code.execute("ARROZ-500")
        self.assertEqual((product.price, product.stock), (Money.of(2700), Decimal(10)))

        again = self.c.import_products.execute(self.admin, changed, update_existing=True, dry_run=False)
        self.assertEqual((again.updated, again.unchanged), (0, 1))

    def test_barcode_alone_works_as_the_code(self):
        report = self.c.import_products.execute(
            self.admin, [row(2, barcode="7702004001234", name="Gaseosa", price="2800")], dry_run=False
        )
        self.assertEqual(report.created, 1)
        self.assertEqual(self.c.find_product_by_code.execute("7702004001234").sku, "7702004001234")

    def test_explains_bad_values(self):
        report = self.c.import_products.execute(self.admin, [
            row(2, sku="A", name="A", price="mucho"),
            row(3, sku="B", name="B", price="100", unit="caja"),
            row(4, sku="C", name="C", price="100", stock="2.5"),  # unidades enteras
        ])
        messages = [error.message for error in report.errors]
        self.assertIn("no es un número válido", messages[0])
        self.assertIn("Unidad «caja» no reconocida", messages[1])
        self.assertIn("unidades enteras", messages[2])

    def test_requires_catalog_permission_and_rows(self):
        with self.assertRaises(PermissionDenied):
            self.c.import_products.execute(self.make_cashier(), [row(2, sku="A", name="A", price="1")])
        with self.assertRaises(ValidationError):
            self.c.import_products.execute(self.admin, [])
