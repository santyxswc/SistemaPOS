from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from pos.domain.cash import CashSession, CashSessionClosed
from pos.domain.catalog import Product, StockLow, Unit
from pos.domain.customers import Customer
from pos.domain.shared.errors import (
    BusinessRuleViolation,
    CreditLimitExceeded,
    InsufficientStock,
    ValidationError,
)
from pos.domain.shared.values import Money, TaxRate

AT = datetime(2026, 10, 5, 15, tzinfo=timezone.utc)
USER = uuid4()


class CashSessionTests(TestCase):
    def setUp(self):
        self.session = CashSession.open(cashier_id=USER, opening_amount=Money.of("50000"), at=AT)

    def test_expected_cash_follows_movements(self):
        self.session.register_sale(sale_number=1, cash_amount=Money.of("12000"), user_id=USER, at=AT)
        self.session.withdraw(amount=Money.of("2000"), note="Pago del hielo", user_id=USER, at=AT)
        self.assertEqual(self.session.expected_cash, Money.of("60000"))

    def test_cannot_withdraw_more_than_available(self):
        with self.assertRaisesRegex(BusinessRuleViolation, "efectivo"):
            self.session.withdraw(amount=Money.of("60000"), note="Proveedor", user_id=USER, at=AT)

    def test_withdrawal_needs_a_reason(self):
        with self.assertRaises(ValidationError):
            self.session.withdraw(amount=Money.of("1000"), note="", user_id=USER, at=AT)

    def test_close_reports_difference_and_locks_the_session(self):
        self.session.close(counted_amount=Money.of("49000"), at=AT)
        self.assertEqual(self.session.difference, Money.of("-1000"))
        self.assertIsInstance(self.session.pull_events()[0], CashSessionClosed)
        with self.assertRaises(BusinessRuleViolation):
            self.session.deposit(amount=Money.of("1000"), note="Sencillo", user_id=USER, at=AT)


def product(**overrides) -> Product:
    data = dict(sku="leche-1", name="Leche 1 L", price=Money.of("4500"), tax_rate=TaxRate.of(0),
                created_at=AT, stock=Decimal("5"), min_stock=Decimal("2"), cost=Money.of("1000"))
    data.update(overrides)
    return Product(**data)


class ProductTests(TestCase):
    def test_normalizes_sku(self):
        self.assertEqual(product().sku, "LECHE-1")

    def test_cannot_sell_more_than_stock(self):
        with self.assertRaises(InsufficientStock):
            product().remove_stock(Decimal("6"), allow_negative=False, at=AT)

    def test_negative_stock_when_the_business_allows_it(self):
        item = product()
        item.remove_stock(Decimal("6"), allow_negative=True, at=AT)
        self.assertEqual(item.stock, Decimal("-1"))

    def test_low_stock_event_only_when_crossing_the_minimum(self):
        item = product()
        item.remove_stock(Decimal("2"), allow_negative=False, at=AT)  # queda 3
        self.assertEqual(item.pull_events(), [])
        item.remove_stock(Decimal("1"), allow_negative=False, at=AT)  # queda 2 = mínimo
        self.assertIsInstance(item.pull_events()[0], StockLow)
        item.remove_stock(Decimal("1"), allow_negative=False, at=AT)
        self.assertEqual(item.pull_events(), [])

    def test_purchase_recalculates_average_cost(self):
        item = product(stock=Decimal("10"))
        item.add_stock(Decimal("10"), at=AT, unit_cost=Money.of("2000"))
        self.assertEqual(item.cost, Money.of("1500"))

    def test_units_must_be_whole_but_kilos_can_be_fractional(self):
        with self.assertRaises(ValidationError):
            product().check_quantity("1.5")
        self.assertEqual(product(unit=Unit.KILOGRAM).check_quantity("1.5"), Decimal("1.500"))

    def test_update_validates_before_changing(self):
        item = product()
        with self.assertRaises(ValidationError):
            item.update(at=AT, price=Money.of("-1"))
        self.assertEqual(item.price, Money.of("4500"))


class CustomerTests(TestCase):
    def setUp(self):
        self.customer = Customer(name="Doña Rosa", credit_limit=Money.of("50000"), created_at=AT)

    def test_charge_within_limit(self):
        self.customer.charge(Money.of("30000"))
        self.assertEqual(self.customer.available_credit, Money.of("20000"))

    def test_limit_is_enforced(self):
        self.customer.charge(Money.of("30000"))
        with self.assertRaises(CreditLimitExceeded):
            self.customer.charge(Money.of("25000"))

    def test_payment_cannot_exceed_debt(self):
        self.customer.charge(Money.of("10000"))
        with self.assertRaises(BusinessRuleViolation):
            self.customer.receive_payment(Money.of("15000"))
