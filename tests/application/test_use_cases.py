"""Flujos completos de los casos de uso contra SQLite real."""

from datetime import UTC, date, datetime
from decimal import Decimal

from pos.application.use_cases.customers import CreateCustomerCommand, RegisterCustomerPayment  # noqa: F401
from pos.application.use_cases.sales import ListSalesQuery
from pos.application.use_cases.users import CreateUserCommand, UpdateUserCommand
from pos.domain.payments import DEFAULT_PAYMENT_METHODS, PaymentKind, PaymentMethodConfig
from pos.domain.shared.errors import (
    BusinessRuleViolation,
    ConflictError,
    CreditLimitExceeded,
    InsufficientStock,
    PermissionDenied,
)
from pos.domain.shared.values import Money
from pos.domain.users import Role

from ..support import PosTestCase


class SalesFlowTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.cashier = self.make_cashier()
        self.rice = self.make_product(stock="10")

    def test_sale_updates_stock_cash_and_numbering(self):
        self.open_cash(self.cashier, "50000")
        first = self.sell(self.cashier, [(self.rice, "3")], [("efectivo", "10000")])
        second = self.sell(self.cashier, [(self.rice, "1")], [("nequi", "2500")])

        self.assertEqual((first.number, second.number), (1, 2))
        self.assertEqual(first.total, Money.of("7500"))
        self.assertEqual(first.change, Money.of("2500"))
        self.assertEqual(self.stock_of(self.rice), Decimal("6"))
        report = self.c.get_current_cash_session.execute(self.cashier)
        self.assertEqual(report.session.expected_cash, Money.of("57500"))  # Nequi no entra al cajón

    def test_cannot_sell_without_open_cash(self):
        with self.assertRaisesRegex(BusinessRuleViolation, "abra la caja"):
            self.sell(self.cashier, [(self.rice, "1")], [("efectivo", "2500")])

    def test_failed_sale_leaves_nothing_half_done(self):
        self.open_cash(self.cashier)
        with self.assertRaises(InsufficientStock):
            self.sell(self.cashier, [(self.rice, "11")], [("efectivo", "50000")])
        self.assertEqual(self.stock_of(self.rice), Decimal("10"))
        sale = self.sell(self.cashier, [(self.rice, "1")], [("efectivo", "2500")])
        self.assertEqual(sale.number, 1)  # el consecutivo tampoco se consumió

    def test_same_product_in_two_lines_respects_total_stock(self):
        self.open_cash(self.cashier)
        with self.assertRaises(InsufficientStock):
            self.sell(self.cashier, [(self.rice, "6"), (self.rice, "5")], [("efectivo", "50000")])

    def test_price_always_comes_from_the_catalog(self):
        self.open_cash(self.cashier)
        sale = self.sell(self.cashier, [(self.rice, "2")], [("efectivo", "5000")])
        self.assertEqual(sale.lines[0].unit_price, Money.of("2500"))
        self.assertEqual(sale.lines[0].tax + sale.lines[0].base, Money.of("5000"))

    def test_cashier_cannot_discount_or_void(self):
        self.open_cash(self.cashier)
        with self.assertRaisesRegex(PermissionDenied, "descuentos"):
            self.sell(self.cashier, [(self.rice, "1", "500")], [("efectivo", "2000")])
        sale = self.sell(self.cashier, [(self.rice, "1")], [("efectivo", "2500")])
        with self.assertRaisesRegex(PermissionDenied, "anular"):
            self.c.void_sale.execute(self.cashier, sale.id, "Error")

    def test_void_restores_stock_and_cash(self):
        self.open_cash(self.cashier, "50000")
        sale = self.sell(self.cashier, [(self.rice, "4")], [("efectivo", "20000")])
        voided = self.c.void_sale.execute(self.admin, sale.id, "Cliente se arrepintió")

        self.assertTrue(voided.is_voided)
        self.assertEqual(self.stock_of(self.rice), Decimal("10"))
        report = self.c.get_current_cash_session.execute(self.cashier)
        self.assertEqual(report.session.expected_cash, Money.of("50000"))
        self.assertEqual((report.sales_count, report.voided_count), (0, 1))

    def test_close_cash_with_totals_by_payment_method(self):
        self.open_cash(self.cashier, "50000")
        self.sell(self.cashier, [(self.rice, "2")], [("efectivo", "10000")])
        self.sell(self.cashier, [(self.rice, "1")], [("nequi", "1000"), ("efectivo", "1500")])
        self.c.register_cash_movement.execute(
            self.cashier, kind="withdrawal", amount=Money.of("3000"), note="Pago de domicilio"
        )
        report = self.c.close_cash_session.execute(self.cashier, counted_amount=Money.of("53000"))

        self.assertEqual(report.session.expected_cash, Money.of("53500"))
        self.assertEqual(report.session.difference, Money.of("-500"))
        totals = {t.code: t.amount for t in report.totals_by_method}
        self.assertEqual(totals, {"efectivo": Money.of("6500"), "nequi": Money.of("1000")})
        with self.assertRaises(BusinessRuleViolation):
            self.sell(self.cashier, [(self.rice, "1")], [("efectivo", "2500")])

    def test_one_open_cash_per_cashier(self):
        self.open_cash(self.cashier)
        with self.assertRaises(ConflictError):
            self.open_cash(self.cashier)

    def test_low_stock_alert_is_published_after_commit(self):
        candle = self.make_product(sku="VELA", name="Vela", price="1000", stock="3", min_stock=Decimal("2"))
        self.open_cash(self.cashier)
        with self.assertLogs("pos.events", "WARNING") as logs:
            self.sell(self.cashier, [(candle, "1")], [("efectivo", "1000")])
        self.assertIn("Stock bajo: Vela", logs.output[0])
        self.assertEqual([p.id for p in self.c.list_low_stock.execute()], [candle.id])

    def test_search_ignores_accents_and_case(self):
        coffee = self.make_product(sku="CAFE-AG", name="Café Águila Roja 250 g", price="9000")
        found = self.c.search_products.execute(text="cafe aguila")
        self.assertEqual([p.id for p in found], [coffee.id])
        self.assertEqual(self.c.find_product_by_code.execute("cafe-ag").id, coffee.id)


class CreditTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.cashier = self.make_cashier()
        self.product = self.make_product(price="10000", stock="20")
        self.customer = self.c.create_customer.execute(
            self.admin,
            CreateCustomerCommand(name="Doña Rosa", document="1061700000", credit_limit=Money.of("50000")),
        )
        self.open_cash(self.cashier, "20000")

    def test_credit_sale_and_cash_payment(self):
        self.sell(self.cashier, [(self.product, "2")], [("fiado", "20000")], customer_id=self.customer.id)
        entry = self.c.register_customer_payment.execute(
            self.cashier, customer_id=self.customer.id, amount=Money.of("5000"), method="efectivo"
        )
        self.assertEqual(entry.balance_after, Money.of("15000"))

        statement = self.c.get_customer_statement.execute(self.cashier, self.customer.id)
        self.assertEqual([e.type.value for e in statement.entries], ["payment", "charge"])
        cash = self.c.get_current_cash_session.execute(self.cashier).session
        self.assertEqual(cash.expected_cash, Money.of("25000"))  # el abono en efectivo entra al cajón

    def test_credit_limit_blocks_the_whole_sale(self):
        with self.assertRaises(CreditLimitExceeded):
            self.sell(self.cashier, [(self.product, "6")], [("fiado", "60000")], customer_id=self.customer.id)
        self.assertEqual(self.c.get_customer.execute(self.customer.id).balance, Money.zero())
        self.assertEqual(self.stock_of(self.product), Decimal("20"))

    def test_void_of_credit_sale_reverses_the_debt(self):
        sale = self.sell(self.cashier, [(self.product, "1")], [("fiado", "10000")], customer_id=self.customer.id)
        self.c.void_sale.execute(self.admin, sale.id, "Venta duplicada")
        self.assertEqual(self.c.get_customer.execute(self.customer.id).balance, Money.zero())

    def test_only_admin_grants_credit(self):
        with self.assertRaisesRegex(PermissionDenied, "cupos"):
            self.c.create_customer.execute(
                self.cashier, CreateCustomerCommand(name="Vecino", credit_limit=Money.of("10000"))
            )
        neighbor = self.c.create_customer.execute(self.cashier, CreateCustomerCommand(name="Vecino"))
        self.assertTrue(neighbor.credit_limit.is_zero)

    def test_business_can_turn_off_credit(self):
        self.c.update_settings.execute(self.admin, {"credit_sales_enabled": False})
        with self.assertRaisesRegex(BusinessRuleViolation, "fiadas"):
            self.sell(self.cashier, [(self.product, "1")], [("fiado", "10000")], customer_id=self.customer.id)


class SettingsAndUsersTests(PosTestCase):
    def test_plan_user_limit(self):
        self.make_cashier("cajero1")
        second = self.make_cashier("cajero2")  # admin + 2 = 3, el límite del plan Mediano
        with self.assertRaisesRegex(BusinessRuleViolation, "3 usuarios"):
            self.make_cashier("cajero3")
        self.c.update_user.execute(self.admin, second.user_id, UpdateUserCommand(active=False))
        self.make_cashier("cajero3")

    def test_admin_cannot_lock_themselves_out(self):
        with self.assertRaises(BusinessRuleViolation):
            self.c.update_user.execute(self.admin, self.admin.user_id, UpdateUserCommand(role=Role.CASHIER))

    def test_duplicate_username(self):
        self.make_cashier("ana")
        with self.assertRaises(ConflictError):
            self.c.create_user.execute(
                self.admin, CreateUserCommand(username="ANA", full_name="Otra Ana", password="clave-segura-3")
            )

    def test_new_payment_method_by_configuration_only(self):
        methods = (*DEFAULT_PAYMENT_METHODS, PaymentMethodConfig(code="bancolombia", name="Bancolombia",
                                                                kind=PaymentKind.ELECTRONIC))
        self.c.update_settings.execute(self.admin, {"payment_methods": methods})
        product = self.make_product()
        self.open_cash(self.admin)
        sale = self.sell(self.admin, [(product, "1")], [("bancolombia", "2500")])
        self.assertEqual(sale.payments[0].method_name, "Bancolombia")

    def test_prices_without_tax_for_b2b_businesses(self):
        self.c.update_settings.execute(self.admin, {"prices_include_tax": False})
        product = self.make_product(price="10000")
        self.open_cash(self.admin)
        sale = self.sell(self.admin, [(product, "1")], [("efectivo", "11900")])
        self.assertEqual((sale.subtotal, sale.tax_total, sale.total),
                         (Money.of("10000"), Money.of("1900"), Money.of("11900")))


class ReportTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.rice = self.make_product(sku="ARROZ", name="Arroz", price="2500", stock="100")
        self.oil = self.make_product(sku="ACEITE", name="Aceite", price="9000", stock="100")
        self.open_cash(self.admin, "0")

    def test_summary_and_top_products(self):
        self.sell(self.admin, [(self.rice, "4"), (self.oil, "1")], [("efectivo", "19000")])
        self.clock.advance(days=1)
        self.sell(self.admin, [(self.rice, "2")], [("nequi", "5000")])
        voided = self.sell(self.admin, [(self.oil, "5")], [("efectivo", "45000")])
        self.c.void_sale.execute(self.admin, voided.id, "Prueba")

        summary = self.c.get_sales_summary.execute(self.admin, date(2026, 10, 5), date(2026, 10, 6))
        self.assertEqual((summary.sales_count, summary.voided_count), (2, 1))
        self.assertEqual(summary.total, Money.of("24000"))
        self.assertEqual(summary.average_ticket, Money.of("12000"))
        self.assertEqual([p.period for p in summary.by_period], ["2026-10-05", "2026-10-06"])
        self.assertEqual({t.code: t.amount for t in summary.by_payment_method},
                         {"efectivo": Money.of("19000"), "nequi": Money.of("5000")})

        monthly = self.c.get_sales_summary.execute(self.admin, date(2026, 10, 1), date(2026, 10, 31), "month")
        self.assertEqual([(p.period, p.sales_count) for p in monthly.by_period], [("2026-10", 2)])

        top = self.c.get_top_products.execute(self.admin, date(2026, 10, 5), date(2026, 10, 6))
        self.assertEqual([(p.sku, p.quantity) for p in top], [("ARROZ", Decimal("6")), ("ACEITE", Decimal("1"))])

    def test_reports_use_the_business_timezone(self):
        # 03:00 UTC del 6 de octubre son las 10:00 p. m. del 5 de octubre en Colombia.
        self.clock.current = datetime(2026, 10, 6, 3, 0, tzinfo=UTC)
        self.sell(self.admin, [(self.rice, "1")], [("efectivo", "2500")])
        summary = self.c.get_sales_summary.execute(self.admin, date(2026, 10, 5), date(2026, 10, 5))
        self.assertEqual(summary.sales_count, 1)

    def test_cashier_only_lists_own_sales(self):
        cashier = self.make_cashier()
        self.open_cash(cashier)
        self.sell(self.admin, [(self.rice, "1")], [("efectivo", "2500")])
        mine = self.sell(cashier, [(self.rice, "1")], [("efectivo", "2500")])
        listed = self.c.list_sales.execute(cashier, ListSalesQuery(date(2026, 10, 5), date(2026, 10, 5)))
        self.assertEqual([s.id for s in listed], [mine.id])
        with self.assertRaises(PermissionDenied):
            self.c.get_sales_summary.execute(cashier, date(2026, 10, 5), date(2026, 10, 5))
