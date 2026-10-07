"""La API completa a través de HTTP (cliente de pruebas de Flask)."""

from ..support import ADMIN_PASSWORD, CASHIER_PASSWORD, ApiTestCase, issue_license, tamper


class HttpApiTests(ApiTestCase):
    def test_idempotency_key_makes_sale_retries_safe(self):
        product_id = self.api("POST", "/api/v1/products", json={
            "sku": "PAN", "name": "Pan", "price": "500", "initial_stock": "10",
        }).get_json()["id"]
        self.api("POST", "/api/v1/cash-sessions", json={"opening_amount": "0"})
        payload = {"items": [{"product_id": product_id, "quantity": 1}],
                   "payments": [{"method": "efectivo", "amount": "500"}]}
        headers = {"Authorization": f"Bearer {self.token}", "Idempotency-Key": "venta-123"}

        first = self.client.post("/api/v1/sales", json=payload, headers=headers)
        retry = self.client.post("/api/v1/sales", json=payload, headers=headers)

        self.assertEqual((first.status_code, retry.status_code), (201, 201))
        self.assertEqual(first.get_json()["id"], retry.get_json()["id"])
        self.assertEqual(self.api("GET", f"/api/v1/products/{product_id}").get_json()["stock"], "9")

    def test_health(self):
        self.assertEqual(self.client.get("/health").get_json()["status"], "ok")

    def test_requires_a_valid_token(self):
        response = self.client.get("/api/v1/products")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "authentication_failed")
        self.assertEqual(self.api("GET", "/api/v1/products", token="basura").status_code, 401)

    def test_wrong_password_does_not_reveal_the_user(self):
        response = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "otra-clave"})
        nobody = self.client.post("/api/v1/auth/login", json={"username": "nadie", "password": "otra-clave"})
        self.assertEqual((response.status_code, nobody.status_code), (401, 401))
        self.assertEqual(response.get_json(), nobody.get_json())

    def test_too_many_failed_logins_answer_429(self):
        for _ in range(5):
            self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "otra-clave"})
        response = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.get_json()["error"]["code"], "too_many_attempts")

    def test_full_day_over_http(self):
        product = self.api("POST", "/api/v1/products", json={
            "sku": "gaseosa-400", "name": "Gaseosa 400 ml", "price": "3000",
            "barcode": "7702004001234", "initial_stock": "24", "min_stock": "6",
        })
        self.assertEqual(product.status_code, 201, product.get_json())
        product_id = product.get_json()["id"]

        scanned = self.api("GET", "/api/v1/products/lookup?code=7702004001234").get_json()
        self.assertEqual(scanned["id"], product_id)

        self.assertEqual(self.api("POST", "/api/v1/cash-sessions", json={"opening_amount": "50000"}).status_code, 201)
        sale = self.api("POST", "/api/v1/sales", json={
            "items": [{"product_id": product_id, "quantity": 2}],
            "payments": [{"method": "efectivo", "amount": "10000"}],
        })
        self.assertEqual(sale.status_code, 201, sale.get_json())
        body = sale.get_json()
        self.assertEqual((body["number"], body["total"], body["change"]), (1, "6000.00", "4000.00"))
        self.assertEqual(body["lines"][0]["tax_rate"], "19")

        current = self.api("GET", "/api/v1/cash-sessions/current").get_json()
        self.assertEqual(current["session"]["expected_cash"], "56000.00")
        self.assertEqual(current["units_sold"], "2")
        self.assertEqual(
            [(p["description"], p["quantity"], p["total"]) for p in current["products"]],
            [("Gaseosa 400 ml", "2", "6000.00")],
        )

        closed = self.api("POST", "/api/v1/cash-sessions/current/close", json={"counted_amount": "56000"})
        self.assertEqual(closed.get_json()["session"]["difference"], "0.00")

        summary = self.api("GET", "/api/v1/reports/sales-summary").get_json()
        self.assertEqual((summary["sales_count"], summary["total"]), (1, "6000.00"))
        self.assertEqual(self.api("GET", f"/api/v1/products/{product_id}").get_json()["stock"], "22")

    def test_clear_validation_errors(self):
        missing = self.api("POST", "/api/v1/products", json={"sku": "X1", "name": "Sin precio"})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.get_json()["error"]["field"], "price")

        wrong = self.api("POST", "/api/v1/products", json={"sku": "X1", "name": "Precio raro", "price": "mil"})
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.get_json()["error"]["code"], "validation_error")

        broken = self.api("POST", "/api/v1/products", data="{no es json", content_type="application/json")
        self.assertEqual(broken.status_code, 400)

    def test_decimal_json_numbers_stay_exact(self):
        product = self.api("POST", "/api/v1/products", json={
            "sku": "QUESO", "name": "Queso campesino", "price": 18000, "unit": "lb", "initial_stock": 3.5,
        })
        self.assertEqual(product.status_code, 201, product.get_json())
        self.assertEqual(product.get_json()["stock"], "3.5")

    def test_business_rules_return_422_and_permissions_403(self):
        self.api("POST", "/api/v1/users", json={
            "username": "luis", "full_name": "Luis Cajero", "password": CASHIER_PASSWORD,
        })
        cashier_token = self.login("luis", CASHIER_PASSWORD)
        product = self.api("POST", "/api/v1/products", json={"sku": "PAN", "name": "Pan", "price": "500"})
        product_id = product.get_json()["id"]

        no_cash = self.api("POST", "/api/v1/sales", token=cashier_token, json={
            "items": [{"product_id": product_id, "quantity": 1}],
            "payments": [{"method": "efectivo", "amount": "500"}],
        })
        self.assertEqual(no_cash.status_code, 422)

        forbidden = self.api("GET", "/api/v1/reports/sales-summary", token=cashier_token)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.get_json()["error"]["code"], "permission_denied")

        me = self.api("GET", "/api/v1/auth/me", token=cashier_token).get_json()
        self.assertIn("sell", me["permissions"])
        self.assertNotIn("void_sales", me["permissions"])

    def test_settings_can_be_customized_per_business(self):
        response = self.api("PATCH", "/api/v1/settings", json={
            "business_name": "Sabor Callejero",
            "default_tax_rate": "8",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        settings = self.api("GET", "/api/v1/settings").get_json()
        self.assertEqual((settings["business_name"], settings["default_tax_rate"]), ("Sabor Callejero", "8"))
        unknown = self.api("PATCH", "/api/v1/settings", json={"color": "rojo"})
        self.assertEqual(unknown.status_code, 400)

    def test_the_user_limit_comes_from_the_license_and_cannot_be_edited(self):
        response = self.api("PATCH", "/api/v1/settings", json={"max_users": 99})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("max_users", self.api("GET", "/api/v1/settings").get_json())

    def test_license_status_and_activation(self):
        trial = self.api("GET", "/api/v1/license").get_json()
        self.assertEqual((trial["state"], trial["valid"], trial["license"]), ("trial", True, None))

        code = issue_license(plan="Mediano", max_users=4, expires_on=None)
        response = self.api("POST", "/api/v1/license", json={"code": code})
        self.assertEqual(response.status_code, 200, response.get_json())
        active = response.get_json()
        self.assertEqual((active["state"], active["max_users"], active["license"]["plan"]), ("active", 4, "Mediano"))

        forged = self.api("POST", "/api/v1/license", json={"code": tamper(code)})
        self.assertEqual(forged.status_code, 400)

    def test_unknown_routes_answer_json(self):
        response = self.api("GET", "/api/v1/no-existe")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["message"], "Ruta no encontrada")
