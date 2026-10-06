from datetime import UTC, datetime
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from pos.domain.payments import PaymentKind
from pos.domain.sales import Sale, SaleCompleted, SaleLine, SalePayment, SaleVoided
from pos.domain.shared.errors import BusinessRuleViolation, ValidationError
from pos.domain.shared.values import Money, TaxRate
from pos.domain.taxes import TaxIncludedPolicy

AT = datetime(2026, 10, 5, 15, tzinfo=UTC)


def line(price="5000", qty="2", discount="0"):
    return SaleLine.build(
        product_id=uuid4(),
        sku="P-1",
        description="Producto",
        quantity=Decimal(qty),
        unit_price=Money.of(price),
        discount=Money.of(discount),
        tax_rate=TaxRate.of(19),
        tax_policy=TaxIncludedPolicy(),
    )


def pay(kind: PaymentKind, amount: str) -> SalePayment:
    return SalePayment(method_code=kind.value, method_name=kind.value, kind=kind, amount=Money.of(amount))


def make_sale(lines, payments, customer_id=None) -> Sale:
    return Sale.create(
        number=1, cashier_id=uuid4(), cash_session_id=uuid4(), lines=lines, payments=payments,
        at=AT, customer_id=customer_id,
    )


class SaleTests(TestCase):
    def test_cash_gives_change(self):
        sale = make_sale([line()], [pay(PaymentKind.CASH, "20000")])
        self.assertEqual(sale.total, Money.of("10000"))
        self.assertEqual(sale.change, Money.of("10000"))
        self.assertEqual(sale.cash_in_drawer, Money.of("10000"))
        self.assertIsInstance(sale.pull_events()[0], SaleCompleted)

    def test_incomplete_payment_is_rejected(self):
        with self.assertRaisesRegex(BusinessRuleViolation, r"faltan \$1\.000"):
            make_sale([line()], [pay(PaymentKind.CASH, "9000")])

    def test_only_cash_can_give_change(self):
        with self.assertRaises(BusinessRuleViolation):
            make_sale([line()], [pay(PaymentKind.ELECTRONIC, "15000")])

    def test_mixed_payment_deducts_change_from_cash(self):
        sale = make_sale([line()], [pay(PaymentKind.ELECTRONIC, "6000"), pay(PaymentKind.CASH, "5000")])
        applied = {p.kind: p.amount for p in sale.applied_payments()}
        self.assertEqual(applied, {PaymentKind.ELECTRONIC: Money.of(6000), PaymentKind.CASH: Money.of(4000)})

    def test_credit_needs_a_customer(self):
        with self.assertRaisesRegex(BusinessRuleViolation, "cliente"):
            make_sale([line()], [pay(PaymentKind.CREDIT, "10000")])

    def test_credit_amount_is_tracked(self):
        sale = make_sale([line()], [pay(PaymentKind.CREDIT, "10000")], customer_id=uuid4())
        self.assertEqual(sale.credit_amount, Money.of("10000"))
        self.assertTrue(sale.cash_in_drawer.is_zero)

    def test_tax_is_computed_after_discount(self):
        discounted = line(price="11900", qty="1", discount="1900")
        self.assertEqual(discounted.total, Money.of("10000"))
        self.assertEqual(discounted.base, Money.of("8403.36"))
        self.assertEqual(discounted.tax, Money.of("1596.64"))

    def test_discount_cannot_exceed_the_line(self):
        with self.assertRaises(ValidationError):
            line(price="1000", qty="1", discount="1500")

    def test_void_once_with_reason(self):
        sale = make_sale([line()], [pay(PaymentKind.CASH, "10000")])
        sale.pull_events()
        with self.assertRaises(ValidationError):
            sale.void(by=uuid4(), reason="  ", at=AT)
        sale.void(by=uuid4(), reason="Cliente devolvió el producto", at=AT)
        self.assertTrue(sale.is_voided)
        self.assertIsInstance(sale.pull_events()[0], SaleVoided)
        with self.assertRaises(BusinessRuleViolation):
            sale.void(by=uuid4(), reason="otra vez", at=AT)
