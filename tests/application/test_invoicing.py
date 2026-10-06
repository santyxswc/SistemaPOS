"""Bandeja de salida de documentos electrónicos con un proveedor falso."""

import threading
import unittest
from datetime import UTC, datetime
from uuid import uuid4

from pos.domain.invoicing import (
    RETRY_DELAYS,
    DocumentKind,
    DocumentStatus,
    ElectronicDocument,
    InvoiceRejected,
    IssuedDocument,
)
from pos.domain.shared.errors import BusinessRuleViolation, PermissionDenied
from pos.infrastructure.background import PeriodicWorker
from pos.infrastructure.invoicing import SimulatedInvoiceProvider, create_invoice_provider

from ..support import ApiTestCase, PosTestCase

NOW = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)


class FakeProvider:
    name = "Proveedor de prueba"

    def __init__(self):
        self.outcomes: list[str] = []  # "ok", "fail" o "reject", en orden; vacío = ok
        self.sent: list[tuple[DocumentKind, int]] = []

    def issue(self, document, sale, settings):
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if outcome == "fail":
            raise ConnectionError("Sin conexión con el proveedor")
        if outcome == "reject":
            raise InvoiceRejected("NIT del adquiriente inválido")
        self.sent.append((document.kind, sale.number))
        return IssuedDocument(cufe=f"cufe-{document.kind}-{sale.number}", qr_data="QR", reference="R1")


def new_document() -> ElectronicDocument:
    return ElectronicDocument.enqueue(sale_id=uuid4(), sale_number=1, kind=DocumentKind.INVOICE, at=NOW)


class ElectronicDocumentTests(unittest.TestCase):
    def test_backs_off_and_gives_up_after_the_last_delay(self):
        document = new_document()
        self.assertTrue(document.is_due(NOW))
        document.mark_failed("caído", at=NOW)
        self.assertEqual(document.next_attempt_at, NOW + RETRY_DELAYS[0])
        self.assertFalse(document.is_due(NOW))
        for _ in range(len(RETRY_DELAYS)):
            document.mark_failed("caído", at=NOW)
        self.assertEqual((document.status, document.next_attempt_at), (DocumentStatus.FAILED, None))

    def test_rejected_waits_for_a_person_and_can_be_retried(self):
        document = new_document()
        document.pull_events()
        document.mark_rejected("NIT inválido", at=NOW)
        self.assertEqual(document.status, DocumentStatus.REJECTED)
        with self.assertRaises(BusinessRuleViolation):
            document.mark_failed("x", at=NOW)
        document.retry(at=NOW)
        self.assertEqual((document.status, document.attempts), (DocumentStatus.PENDING, 0))
        self.assertEqual(len(document.pull_events()), 1)  # despierta al proceso de envío
        with self.assertRaises(BusinessRuleViolation):
            document.retry(at=NOW)

    def test_simulated_provider_and_factory(self):
        self.assertIsNone(create_invoice_provider(""))
        self.assertIsInstance(create_invoice_provider(" Simulado "), SimulatedInvoiceProvider)
        with self.assertRaisesRegex(RuntimeError, "opciones"):
            create_invoice_provider("dian-directo")


class OutboxFlowTests(PosTestCase):
    def make_invoice_provider(self):
        self.provider = FakeProvider()
        return self.provider

    def setUp(self):
        super().setUp()
        self.rice = self.make_product()
        self.open_cash(self.admin)
        self.process = self.c.background_workers[0]

    def documents(self, *statuses):
        return self.c.list_electronic_documents.execute(self.admin, statuses=set(statuses) or None)

    def test_each_sale_leaves_its_document_and_the_worker_sends_it(self):
        sale = self.sell(self.admin, [(self.rice, "1")], [("efectivo", "2500")])
        [pending] = self.documents(DocumentStatus.PENDING)
        self.assertEqual((pending.sale_id, pending.kind), (sale.id, DocumentKind.INVOICE))

        self.process.run_once()

        [accepted] = self.documents()
        self.assertEqual((accepted.status, accepted.cufe), (DocumentStatus.ACCEPTED, "cufe-invoice-1"))

    def test_a_failure_is_retried_later_without_blocking_the_sale(self):
        self.provider.outcomes = ["fail"]
        self.sell(self.admin, [(self.rice, "1")], [("efectivo", "2500")])
        self.process.run_once()
        [document] = self.documents()
        self.assertEqual((document.status, document.attempts), (DocumentStatus.PENDING, 1))
        self.assertIn("Sin conexión", document.last_error)

        self.process.run_once()  # todavía no es hora
        self.assertEqual(self.provider.sent, [])
        self.clock.advance(minutes=1)
        self.process.run_once()
        self.assertEqual(self.documents()[0].status, DocumentStatus.ACCEPTED)

    def test_rejection_needs_a_manual_retry(self):
        self.provider.outcomes = ["reject"]
        self.sell(self.admin, [(self.rice, "1")], [("efectivo", "2500")])
        self.process.run_once()
        status = self.c.get_invoicing_status.execute(self.admin)
        self.assertEqual((status.enabled, status.needs_attention), (True, 1))
        [rejected] = self.documents(DocumentStatus.REJECTED)

        self.c.retry_electronic_document.execute(self.admin, rejected.id)
        self.process.run_once()

        self.assertEqual(self.documents()[0].status, DocumentStatus.ACCEPTED)
        self.assertEqual(self.c.get_invoicing_status.execute(self.admin).needs_attention, 0)

    def test_void_sends_a_credit_note_after_the_invoice(self):
        self.provider.outcomes = ["fail"]
        sale = self.sell(self.admin, [(self.rice, "1")], [("efectivo", "2500")])
        self.process.run_once()  # el documento de la venta falla
        self.c.void_sale.execute(self.admin, sale.id, "Se equivocó de producto")
        self.process.run_once()  # la nota crédito espera: la venta no está aceptada
        self.assertEqual(self.provider.sent, [])

        self.clock.advance(minutes=5)
        self.process.run_once()
        self.assertEqual(self.provider.sent, [(DocumentKind.INVOICE, 1), (DocumentKind.CREDIT_NOTE, 1)])

    def test_cashiers_cannot_review_or_retry(self):
        cashier = self.make_cashier()
        with self.assertRaises(PermissionDenied):
            self.c.list_electronic_documents.execute(cashier)


class DisabledInvoicingTests(PosTestCase):
    def test_without_provider_sales_leave_no_documents(self):
        rice = self.make_product()
        self.open_cash(self.admin)
        sale = self.sell(self.admin, [(rice, "1")], [("efectivo", "2500")])
        self.c.void_sale.execute(self.admin, sale.id, "prueba")
        status = self.c.get_invoicing_status.execute(self.admin)
        self.assertEqual((status.enabled, sum(status.counts.values())), (False, 0))
        self.assertEqual(self.c.background_workers, ())


class PeriodicWorkerTests(unittest.TestCase):
    def test_wakes_up_on_demand_and_survives_errors(self):
        calls = []
        ran_twice = threading.Event()

        def job():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("falla de prueba")
            ran_twice.set()

        worker = PeriodicWorker("prueba", job, interval_seconds=3600)
        worker.start()
        self.addCleanup(worker.stop)
        worker.wake()
        self.assertTrue(ran_twice.wait(5))
        self.assertTrue(worker.running)


class InvoicingApiTests(ApiTestCase):
    def make_invoice_provider(self):
        return SimulatedInvoiceProvider()

    def test_status_documents_and_simulated_cufe(self):
        product = self.api("POST", "/api/v1/products", json={"sku": "PAN", "name": "Pan", "price": "500",
                                                                  "initial_stock": "5"}).get_json()
        self.api("POST", "/api/v1/cash-sessions", json={"opening_amount": "0"})
        self.api("POST", "/api/v1/sales", json={"items": [{"product_id": product["id"], "quantity": 1}],
                                               "payments": [{"method": "efectivo", "amount": "500"}]})
        self.c.background_workers[0].run_once()

        status = self.api("GET", "/api/v1/invoicing").get_json()
        self.assertEqual((status["enabled"], status["counts"]["accepted"]), (True, 1))
        [document] = self.api("GET", "/api/v1/invoicing/documents?status=accepted").get_json()["items"]
        self.assertEqual(len(document["cufe"]), 96)  # SHA-384 en hexadecimal, como el CUFE real
        self.assertIn("QRCode: https://catalogo-vpfe-hab.dian.gov.co", document["qr_data"])

        not_retryable = self.api("POST", f"/api/v1/invoicing/documents/{document['id']}/retry")
        self.assertEqual(not_retryable.status_code, 422)
        bad_filter = self.api("GET", "/api/v1/invoicing/documents?status=perdido")
        self.assertEqual(bad_filter.status_code, 400)
