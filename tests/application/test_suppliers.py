"""Compras de mercancía y cuentas por pagar contra SQLite real."""

from datetime import date
from decimal import Decimal

from pos.application.use_cases.suppliers import (
    CreateSupplierCommand,
    ListPurchasesQuery,
    PaySupplierCommand,
    PurchaseItemInput,
    ReceivePurchaseCommand,
)
from pos.application.use_cases.users import CreateUserCommand
from pos.domain.cash import CashMovementType
from pos.domain.shared.errors import BusinessRuleViolation, ConflictError, PermissionDenied, ValidationError
from pos.domain.shared.values import Money
from pos.domain.suppliers import PurchasePaymentMode, PurchaseStatus
from pos.domain.users import Role

from ..support import CASHIER_PASSWORD, PosTestCase

CASH = PurchasePaymentMode.CASH_DRAWER
CREDIT = PurchasePaymentMode.CREDIT
EXTERNAL = PurchasePaymentMode.EXTERNAL


class SupplierFlowTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.supplier = self.c.create_supplier.execute(
            self.admin, CreateSupplierCommand(name="Distribuidora El Sol", document="900111222", phone="3001234567")
        )
        self.rice = self.make_product(stock="10")  # costo 0
        self.soda = self.make_product(sku="GASEOSA", name="Gaseosa 400 ml", price="3000", stock="0")

    def receive(self, mode, items, actor=None, **extra):
        command = ReceivePurchaseCommand(
            items=[PurchaseItemInput(product_id=p.id, quantity=Decimal(q), unit_cost=Money.of(c)) for p, q, c in items],
            payment_mode=mode,
            supplier_id=extra.pop("supplier_id", self.supplier.id),
            **extra,
        )
        return self.c.receive_purchase.execute(actor or self.admin, command).purchase

    def test_credit_purchase_updates_stock_cost_and_debt(self):
        purchase = self.receive(CREDIT, [(self.rice, "10", "1800"), (self.soda, "24", "1500")],
                                invoice_number="FV-1001", due_date=date(2026, 10, 20))

        self.assertEqual((purchase.number, purchase.total), (1, Money.of("54000")))
        self.assertEqual(self.stock_of(self.rice), Decimal("20"))
        rice = self.c.get_product.execute(self.rice.id)
        self.assertEqual(rice.cost, Money.of("900"))  # promedio: 10 a $0 y 10 a $1.800
        self.assertEqual(self.c.get_supplier.execute(self.supplier.id).balance, Money.of("54000"))

        kardex = self.c.list_stock_movements.execute(self.admin, self.soda.id)
        self.assertEqual((kardex[0].reference, kardex[0].unit_cost), ("Compra #1", Money.of("1500")))
        statement = self.c.get_supplier_statement.execute(self.admin, self.supplier.id)
        self.assertEqual([p.number for p in statement.pending], [1])
        self.assertIn("FV-1001", statement.entries[0].note)

    def test_cash_purchase_comes_out_of_the_drawer(self):
        self.open_cash(self.admin, "100000")
        self.receive(CASH, [(self.soda, "12", "1500")])

        report = self.c.get_current_cash_session.execute(self.admin)
        self.assertEqual(report.session.expected_cash, Money.of("82000"))
        movement = report.session.movements[-1]
        self.assertEqual(movement.type, CashMovementType.SUPPLIER_PAYMENT)
        self.assertIn("Distribuidora El Sol", movement.reference)
        self.assertEqual(self.c.get_supplier.execute(self.supplier.id).balance, Money.zero())

    def test_cash_purchase_needs_an_open_drawer_with_enough_money(self):
        with self.assertRaisesRegex(BusinessRuleViolation, "abra la caja"):
            self.receive(CASH, [(self.soda, "12", "1500")])
        self.open_cash(self.admin, "1000")
        with self.assertRaisesRegex(BusinessRuleViolation, "efectivo"):
            self.receive(CASH, [(self.soda, "12", "1500")])
        self.assertEqual(self.stock_of(self.soda), Decimal("0"))  # nada quedó a medias

    def test_external_purchase_without_supplier(self):
        purchase = self.receive(EXTERNAL, [(self.soda, "6", "1500")], supplier_id=None)
        self.assertEqual((purchase.status, purchase.supplier_id), (PurchaseStatus.PAID, None))
        self.assertEqual(self.stock_of(self.soda), Decimal("6"))

    def test_validations(self):
        with self.assertRaisesRegex(ValidationError, "proveedor"):
            self.receive(CREDIT, [(self.soda, "1", "10")], supplier_id=None)
        with self.assertRaisesRegex(ValidationError, "pasado"):
            self.receive(CREDIT, [(self.soda, "1", "10")], due_date=date(2026, 1, 1))
        with self.assertRaisesRegex(ValidationError, "enteras"):
            self.receive(EXTERNAL, [(self.soda, "1.5", "10")])
        with self.assertRaisesRegex(ValidationError, "mayor que cero"):
            self.receive(CREDIT, [(self.soda, "1", "0")])

    def test_payment_goes_to_the_invoice_due_first(self):
        first = self.receive(CREDIT, [(self.soda, "10", "1000")], due_date=date(2026, 11, 30))
        second = self.receive(CREDIT, [(self.soda, "5", "1000")], due_date=date(2026, 10, 15))

        result = self.c.pay_supplier.execute(
            self.admin, PaySupplierCommand(supplier_id=self.supplier.id, amount=Money.of("8000"), method="Nequi")
        )

        self.assertEqual([(p.number, a) for p, a in result.applied], [(second.number, Money.of("5000")),
                                                                     (first.number, Money.of("3000"))])
        self.assertEqual((result.entry.balance_after, result.entry.method), (Money.of("7000"), "Nequi"))
        pending = self.c.list_purchases.execute(self.admin, ListPurchasesQuery(pending_only=True))
        self.assertEqual([(d.purchase.number, d.purchase.outstanding) for d in pending], [(1, Money.of("7000"))])

    def test_payment_from_the_drawer_and_over_payment(self):
        self.receive(CREDIT, [(self.soda, "10", "1000")])
        self.open_cash(self.admin, "50000")
        with self.assertRaisesRegex(BusinessRuleViolation, "supera"):
            self.c.pay_supplier.execute(
                self.admin, PaySupplierCommand(supplier_id=self.supplier.id, amount=Money.of("10001"))
            )
        self.c.pay_supplier.execute(
            self.admin,
            PaySupplierCommand(supplier_id=self.supplier.id, amount=Money.of("10000"), from_cash_drawer=True),
        )
        report = self.c.get_current_cash_session.execute(self.admin)
        self.assertEqual(report.session.expected_cash, Money.of("40000"))

    def test_payables_summary_orders_by_what_is_overdue(self):
        other = self.c.create_supplier.execute(self.admin, CreateSupplierCommand(name="Alpina"))
        self.receive(CREDIT, [(self.soda, "10", "1000")], due_date=date(2026, 10, 8))
        self.receive(CREDIT, [(self.soda, "2", "1000")], supplier_id=other.id, due_date=date(2026, 10, 7))
        self.receive(CREDIT, [(self.soda, "1", "1000")], supplier_id=other.id)
        self.clock.advance(days=3)  # 8 de octubre: la de Alpina del 7 venció

        summary = self.c.get_payables_summary.execute(self.admin)

        self.assertEqual((summary.total, summary.overdue, summary.due_soon),
                         (Money.of("13000"), Money.of("2000"), Money.of("10000")))
        self.assertEqual([row.supplier.name for row in summary.suppliers], ["Alpina", "Distribuidora El Sol"])
        self.assertEqual(summary.suppliers[1].next_due_date, date(2026, 10, 8))

    def test_document_must_be_unique(self):
        with self.assertRaises(ConflictError):
            self.c.create_supplier.execute(self.admin, CreateSupplierCommand(name="Otro", document="900111222"))

    def test_permissions(self):
        cashier = self.make_cashier()
        supervisor_user = self.c.create_user.execute(self.admin, CreateUserCommand(
            username="encargado", full_name="Encargado", password=CASHIER_PASSWORD, role=Role.SUPERVISOR))
        from pos.application.actor import Actor

        supervisor = Actor.from_user(supervisor_user)
        with self.assertRaises(PermissionDenied):
            self.c.create_supplier.execute(cashier, CreateSupplierCommand(name="X"))
        with self.assertRaises(PermissionDenied):
            self.receive(EXTERNAL, [(self.soda, "1", "10")], actor=cashier)
        # El supervisor recibe mercancía y ve las compras, pero no paga ni crea proveedores.
        self.receive(EXTERNAL, [(self.soda, "1", "10")], actor=supervisor)
        self.assertEqual(len(self.c.list_purchases.execute(supervisor, ListPurchasesQuery())), 1)
        with self.assertRaises(PermissionDenied):
            self.c.get_payables_summary.execute(supervisor)
