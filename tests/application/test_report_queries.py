"""El modelo de lectura de reportes da exactamente las mismas cifras que el dominio."""

from collections import defaultdict
from decimal import Decimal

from pos.application.ports import SalesFilter
from pos.application.use_cases.customers import CreateCustomerCommand
from pos.domain.catalog import Unit
from pos.domain.shared.values import Money
from pos.infrastructure.persistence.sqlite.connection import connect
from pos.infrastructure.persistence.sqlite.migrations import migrate

from ..support import PosTestCase


class SalesReportQueriesTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.open_cash(self.admin, "100000")
        rice = self.make_product(sku="ARROZ", name="Arroz", price="2500", stock="500")
        cheese = self.make_product(sku="QUESO", name="Queso", price="18990", stock="50", unit=Unit.KILOGRAM)
        soda = self.make_product(sku="GASEOSA", name="Gaseosa", price="3333.33", stock="500")
        customer = self.c.create_customer.execute(
            self.admin, CreateCustomerCommand(name="Doña Rosa", credit_limit=Money.of("500000"))
        )
        self.sell(self.admin, [(rice, "3"), (cheese, "0.375")], [("efectivo", "20000")])
        self.sell(self.admin, [(soda, "7", "1000")], [("nequi", "10000"), ("efectivo", "20000")])
        self.sell(self.admin, [(cheese, "1.255"), (rice, "1")], [("fiado", "26332.45")], customer_id=customer.id)
        self.sell(self.admin, [(soda, "1")], [("efectivo", "2000"), ("efectivo", "5000")])
        voided = self.sell(self.admin, [(rice, "10")], [("tarjeta", "25000")])
        self.c.void_sale.execute(self.admin, voided.id, "Prueba")
        for _ in range(3):
            self.clock.advance(minutes=7)
            self.sell(self.admin, [(rice, "2"), (soda, "3")], [("efectivo", "50000")])

    def expected(self):
        with self.c.uow_factory(read_only=True) as uow:
            sales = uow.sales.find()
        completed = [sale for sale in sales if not sale.is_voided]
        by_method = defaultdict(Money.zero)
        products = defaultdict(lambda: [Decimal(0), Money.zero()])
        for sale in completed:
            for payment in sale.applied_payments():
                by_method[payment.method_code] += payment.amount
            for line in sale.lines:
                products[line.sku][0] += line.quantity
                products[line.sku][1] += line.total
        return sales, completed, dict(by_method), {sku: tuple(v) for sku, v in products.items()}

    def test_matches_the_domain_calculation(self):
        sales, completed, by_method, products = self.expected()
        with self.c.uow_factory(read_only=True) as uow:
            totals = uow.sales_reports.totals(SalesFilter())
            methods = uow.sales_reports.totals_by_payment_method(SalesFilter())
            top = uow.sales_reports.top_products(SalesFilter(), limit=10)
            amounts = uow.sales_reports.sale_amounts(SalesFilter())

        self.assertEqual((totals.sales_count, totals.voided_count), (len(completed), len(sales) - len(completed)))
        self.assertEqual(totals.total, Money.sum(s.total for s in completed))
        self.assertEqual(totals.subtotal, Money.sum(s.subtotal for s in completed))
        self.assertEqual(totals.tax_total, Money.sum(s.tax_total for s in completed))
        self.assertEqual(totals.discount_total, Money.sum(s.discount_total for s in completed))
        self.assertEqual({m.code: m.amount for m in methods}, by_method)
        self.assertEqual([m.amount for m in methods], sorted(by_method.values(), reverse=True))
        self.assertEqual({p.sku: (p.quantity, p.total) for p in top}, products)
        self.assertEqual(sorted(a for _, a in amounts), sorted(s.total for s in completed))

    def test_filters_by_cash_session_and_dates(self):
        session = self.c.get_current_cash_session.execute(self.admin).session
        last_hour = SalesFilter(start=self.clock.now().replace(minute=0), end=self.clock.now().replace(minute=59))
        with self.c.uow_factory(read_only=True) as uow:
            by_session = uow.sales_reports.totals(SalesFilter(cash_session_id=session.id))
            in_range = uow.sales_reports.totals(last_hour)
            nothing = uow.sales_reports.totals(SalesFilter(start=self.clock.now().replace(year=2030)))
        self.assertEqual(by_session.sales_count, 7)
        self.assertEqual(in_range.sales_count, 7)
        self.assertEqual((nothing.sales_count, nothing.total), (0, Money.zero()))

    def test_migration_backfills_existing_sales(self):
        _, _, by_method, _ = self.expected()
        conn = connect(self.c.config.database_path)
        conn.executescript(
            # Deja la base como estaba en la versión 2 (deshace también las migraciones posteriores).
            "DROP TABLE business_logo; DROP TABLE electronic_documents; "
            "DROP TABLE supplier_ledger; DROP TABLE purchase_lines; DROP TABLE purchases; DROP TABLE suppliers; "
            "DROP INDEX ix_sale_lines_product; ALTER TABLE sale_payments DROP COLUMN applied_amount; "
            "PRAGMA user_version = 2;"
        )
        conn.close()

        migrate(self.c.config.database_path)

        with self.c.uow_factory(read_only=True) as uow:
            methods = uow.sales_reports.totals_by_payment_method(SalesFilter())
        self.assertEqual({m.code: m.amount for m in methods}, by_method)
