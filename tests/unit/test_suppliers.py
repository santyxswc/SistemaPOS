"""Reglas de proveedores y de cómo se reparte un pago entre facturas."""

import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from pos.domain.shared.errors import BusinessRuleViolation, ValidationError
from pos.domain.shared.values import Money
from pos.domain.suppliers import (
    Purchase,
    PurchaseLine,
    PurchasePaymentMode,
    PurchaseStatus,
    Supplier,
    allocate_payment,
)

NOW = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)


def line(cost: str, qty: str = "1") -> PurchaseLine:
    return PurchaseLine(product_id=uuid4(), sku="X", description="X", quantity=Decimal(qty), unit_cost=Money.of(cost))


def credit_purchase(number: int, cost: str, due: date | None) -> Purchase:
    return Purchase.register(
        number=number, user_id=uuid4(), at=NOW, payment_mode=PurchasePaymentMode.CREDIT,
        lines=[line(cost)], supplier_id=uuid4(), due_date=due,
    )


class SupplierTests(unittest.TestCase):
    def test_cleans_data_and_tracks_debt(self):
        supplier = Supplier(name="  Postobón ", document=" 890903939 ", email="VENTAS@P.CO", created_at=NOW)
        self.assertEqual((supplier.name, supplier.document, supplier.email), ("Postobón", "890903939", "ventas@p.co"))
        supplier.add_debt(Money.of("100000"))
        supplier.pay(Money.of("40000"))
        self.assertEqual(supplier.balance, Money.of("60000"))

    def test_cannot_pay_more_than_owed(self):
        supplier = Supplier(name="Alpina", created_at=NOW, balance=Money.of("1000"))
        with self.assertRaises(BusinessRuleViolation):
            supplier.pay(Money.of("1000.01"))

    def test_inactive_supplier_cannot_receive_new_debt(self):
        supplier = Supplier(name="Alpina", created_at=NOW, active=False)
        with self.assertRaises(BusinessRuleViolation):
            supplier.add_debt(Money.of("10"))


class PurchaseTests(unittest.TestCase):
    def test_total_and_outstanding(self):
        purchase = Purchase.register(
            number=1, user_id=uuid4(), at=NOW, payment_mode=PurchasePaymentMode.CREDIT,
            lines=[line("1500", "24"), line("2333.333", "3")], supplier_id=uuid4(),
        )
        self.assertEqual(purchase.total, Money.of("42999.99"))  # el costo unitario va en centavos: 2333.33 × 3
        self.assertEqual(purchase.outstanding, purchase.total)
        self.assertEqual(purchase.status, PurchaseStatus.PENDING)
        self.assertEqual(len(purchase.pull_events()), 1)

    def test_cash_purchase_is_paid_from_the_start(self):
        purchase = Purchase.register(
            number=1, user_id=uuid4(), at=NOW, payment_mode=PurchasePaymentMode.CASH_DRAWER, lines=[line("100")]
        )
        self.assertEqual((purchase.status, purchase.outstanding), (PurchaseStatus.PAID, Money.zero()))

    def test_credit_needs_a_supplier_and_due_date_only_on_credit(self):
        with self.assertRaisesRegex(ValidationError, "proveedor"):
            Purchase.register(number=1, user_id=uuid4(), at=NOW, payment_mode=PurchasePaymentMode.CREDIT,
                              lines=[line("100")])
        with self.assertRaisesRegex(ValidationError, "vencimiento"):
            Purchase.register(number=1, user_id=uuid4(), at=NOW, payment_mode=PurchasePaymentMode.EXTERNAL,
                              lines=[line("100")], due_date=date(2026, 11, 1))
        with self.assertRaisesRegex(ValidationError, "al menos un producto"):
            Purchase.register(number=1, user_id=uuid4(), at=NOW, payment_mode=PurchasePaymentMode.EXTERNAL, lines=[])

    def test_overdue(self):
        purchase = credit_purchase(1, "100", date(2026, 10, 5))
        self.assertTrue(purchase.is_overdue(date(2026, 10, 6)))
        self.assertFalse(purchase.is_overdue(date(2026, 10, 5)))
        purchase.apply_payment(Money.of("100"))
        self.assertFalse(purchase.is_overdue(date(2026, 10, 6)))


class AllocatePaymentTests(unittest.TestCase):
    def test_pays_what_is_due_first_then_undated_invoices(self):
        undated = credit_purchase(1, "500", None)
        later = credit_purchase(2, "300", date(2026, 11, 30))
        sooner = credit_purchase(3, "200", date(2026, 10, 20))

        applied = allocate_payment([undated, later, sooner], Money.of("600"))

        self.assertEqual([(p.number, a) for p, a in applied], [(3, Money.of("200")), (2, Money.of("300")),
                                                              (1, Money.of("100"))])
        self.assertEqual(undated.outstanding, Money.of("400"))
        self.assertEqual((sooner.status, later.status), (PurchaseStatus.PAID, PurchaseStatus.PAID))

    def test_rejects_non_positive_amounts(self):
        with self.assertRaises(ValidationError):
            allocate_payment([credit_purchase(1, "10", None)], Money.zero())
