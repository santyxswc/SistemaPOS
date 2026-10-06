"""Proveedores, compras y cuentas por pagar a través de HTTP."""

from datetime import date, timedelta

from ..support import ApiTestCase


class SuppliersApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.product_id = self.api("POST", "/api/v1/products", json={
            "sku": "LECHE", "name": "Leche 1 L", "price": "4500", "initial_stock": "0",
        }).get_json()["id"]

    def create_supplier(self, **extra):
        response = self.api("POST", "/api/v1/suppliers", json={"name": "Alpina", "document": "860025900", **extra})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def test_purchase_on_credit_then_pay(self):
        supplier = self.create_supplier(contact_name="Carlos", notes="Visita los martes")
        due = (date.today() + timedelta(days=15)).isoformat()

        purchase = self.api("POST", "/api/v1/purchases", json={
            "supplier_id": supplier["id"], "payment_mode": "credit", "invoice_number": "A-77", "due_date": due,
            "items": [{"product_id": self.product_id, "quantity": "24", "unit_cost": "3200"}],
        })
        self.assertEqual(purchase.status_code, 201, purchase.get_json())
        body = purchase.get_json()
        self.assertEqual((body["number"], body["total"], body["status"], body["supplier_name"]),
                         (1, "76800.00", "pending", "Alpina"))
        self.assertEqual(self.api("GET", f"/api/v1/products/{self.product_id}").get_json()["stock"], "24")

        payables = self.api("GET", "/api/v1/suppliers/payables").get_json()
        self.assertEqual((payables["total"], payables["overdue"]), ("76800.00", "0.00"))
        self.assertEqual(payables["suppliers"][0]["next_due_date"], due)

        paid = self.api("POST", f"/api/v1/suppliers/{supplier['id']}/payments",
                        json={"amount": "76800", "method": "Transferencia"})
        self.assertEqual(paid.status_code, 201, paid.get_json())
        self.assertEqual(paid.get_json()["applied"], [{"purchase_id": body["id"], "number": 1, "amount": "76800.00"}])

        statement = self.api("GET", f"/api/v1/suppliers/{supplier['id']}/statement").get_json()
        self.assertEqual((statement["supplier"]["balance"], statement["pending"]), ("0.00", []))
        self.assertEqual([e["type"] for e in statement["entries"]], ["payment", "purchase"])
        listed = self.api("GET", "/api/v1/purchases").get_json()["items"]
        self.assertEqual(listed[0]["status"], "paid")

    def test_search_and_edit(self):
        supplier = self.create_supplier()
        found = self.api("GET", "/api/v1/suppliers?q=alpi").get_json()["items"]
        self.assertEqual([s["id"] for s in found], [supplier["id"]])

        edited = self.api("PATCH", f"/api/v1/suppliers/{supplier['id']}", json={"phone": "6015551234",
                                                                               "active": False})
        self.assertEqual((edited.get_json()["phone"], edited.get_json()["active"]), ("6015551234", False))
        self.assertEqual(self.api("GET", "/api/v1/suppliers").get_json()["items"], [])
        unknown = self.api("PATCH", f"/api/v1/suppliers/{supplier['id']}", json={"balance": "0"})
        self.assertEqual(unknown.status_code, 400)

    def test_invalid_input(self):
        bad_mode = self.api("POST", "/api/v1/purchases", json={
            "payment_mode": "trueque", "items": [{"product_id": self.product_id, "quantity": "1", "unit_cost": "1"}],
        })
        self.assertEqual(bad_mode.status_code, 400)
        bad_date = self.api("POST", "/api/v1/purchases", json={
            "payment_mode": "external", "due_date": "mañana",
            "items": [{"product_id": self.product_id, "quantity": "1", "unit_cost": "1"}],
        })
        self.assertEqual(bad_date.get_json()["error"]["field"], "due_date")
        duplicated = self.api("POST", "/api/v1/suppliers", json={"name": "Otra", "document": "1"})
        again = self.api("POST", "/api/v1/suppliers", json={"name": "Otra más", "document": "1"})
        self.assertEqual((duplicated.status_code, again.status_code), (201, 409))
