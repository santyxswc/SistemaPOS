"""Módulos por cliente: lo que se apaga desaparece de la API, de los permisos y de la interfaz."""

import tempfile
import unittest
from pathlib import Path

from pos.application.modules import Module, ModuleSet, parse_module_names
from pos.config import AppConfig, read_env_file, set_env_values
from pos.domain.shared.errors import ValidationError
from pos.domain.users import Permission

from ..support import CASHIER_PASSWORD, ApiTestCase


class ModuleSetTests(unittest.TestCase):
    def test_factory_modules_leave_licensing_off(self):
        modules = ModuleSet.defaults()
        self.assertTrue(modules.is_enabled(Module.SUPPLIERS))
        self.assertFalse(modules.is_enabled(Module.LICENSING))

    def test_a_module_without_its_requirement_turns_off(self):
        modules = ModuleSet.configure(disable={Module.CUSTOMERS}, enable={Module.CREDIT})
        self.assertFalse(modules.is_enabled(Module.CREDIT))
        self.assertEqual(modules.blocked_by(Module.CREDIT), Module.CUSTOMERS)

    def test_permissions_of_disabled_modules_disappear(self):
        available = ModuleSet.configure(disable={Module.SUPPLIERS, Module.CREDIT}).available_permissions
        self.assertNotIn(Permission.MANAGE_SUPPLIERS, available)
        self.assertNotIn(Permission.COLLECT_PAYMENTS, available)
        self.assertIn(Permission.MANAGE_CUSTOMERS, available)
        self.assertIn(Permission.SELL, available)

    def test_names_are_read_like_the_technician_writes_them(self):
        self.assertEqual(parse_module_names(" Proveedores ; reportes,"), {Module.SUPPLIERS, Module.REPORTS})
        with self.assertRaises(ValidationError):
            parse_module_names("proveedor")

    def test_env_configuration(self):
        base = {"POS_SECRET_KEY": "s" * 48}
        config = AppConfig.from_env({**base, "POS_MODULES_DISABLED": "reportes", "POS_MODULES_ENABLED": "licencias"})
        self.assertFalse(config.modules.is_enabled(Module.REPORTS))
        self.assertTrue(config.modules.is_enabled(Module.LICENSING))
        with self.assertRaisesRegex(ValidationError, "POS_MODULES"):
            AppConfig.from_env({**base, "POS_MODULES_DISABLED": "inventarios"})

    def test_env_file_keeps_comments_when_changing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("# clave\nPOS_SECRET_KEY=abc\nPOS_MODULES_DISABLED=\n", encoding="utf-8")
            set_env_values(env, {"POS_MODULES_DISABLED": "proveedores", "POS_MODULES_ENABLED": "licencias"})
            self.assertTrue(env.read_text(encoding="utf-8").startswith("# clave\n"))
            self.assertEqual(
                read_env_file(env),
                {"POS_SECRET_KEY": "abc", "POS_MODULES_DISABLED": "proveedores", "POS_MODULES_ENABLED": "licencias"},
            )


class StoreWithoutSuppliersOrReportsTests(ApiTestCase):
    """Un cliente que pidió el sistema sin proveedores, sin reportes y sin fiado."""

    modules = ModuleSet.configure(disable={Module.SUPPLIERS, Module.REPORTS, Module.CREDIT})

    def test_their_routes_do_not_exist(self):
        for url in ("/api/v1/suppliers", "/api/v1/reports/sales-summary", "/api/v1/license"):
            self.assertEqual(self.api("GET", url).status_code, 404, url)
        self.assertEqual(self.api("GET", "/api/v1/customers").status_code, 200)

    def test_the_interface_receives_the_module_list_and_trimmed_permissions(self):
        modules = {m["id"]: m["enabled"] for m in self.api("GET", "/api/v1/modules").get_json()["items"]}
        self.assertEqual((modules["proveedores"], modules["reportes"], modules["clientes"]), (False, False, True))
        permissions = self.api("GET", "/api/v1/auth/me").get_json()["permissions"]
        self.assertNotIn("manage_suppliers", permissions)
        self.assertNotIn("view_reports", permissions)
        self.assertIn("manage_customers", permissions)
        roles = self.api("GET", "/api/v1/roles").get_json()
        self.assertNotIn("view_reports", [p["code"] for p in roles["permissions"]])

    def test_credit_sales_are_rejected(self):
        product = self.make_product()
        customer = self.api("POST", "/api/v1/customers", json={"name": "Doña Marta"})
        self.assertEqual(customer.status_code, 201, customer.get_json())
        self.api("POST", "/api/v1/cash-sessions", json={"opening_amount": "0"})
        sale = self.api("POST", "/api/v1/sales", json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "payments": [{"method": "fiado", "amount": "2500"}],
            "customer_id": customer.get_json()["id"],
        })
        self.assertEqual(sale.status_code, 422, sale.get_json())

    def test_editing_a_role_keeps_the_permissions_of_hidden_modules(self):
        # El supervisor de fábrica ve reportes y maneja fiados: con esos módulos apagados, guardar su rol
        # no se los quita, para que vuelvan intactos si el cliente los pide después.
        response = self.api("PUT", "/api/v1/roles/supervisor", json={"permissions": ["sell", "operate_cash"]})
        self.assertEqual(response.status_code, 200, response.get_json())
        with self.c.uow_factory(read_only=True) as uow:
            granted = uow.roles.get().for_role("supervisor")
        hidden = {Permission.VIEW_REPORTS, Permission.GRANT_CREDIT, Permission.COLLECT_PAYMENTS}
        self.assertEqual(granted, {Permission.SELL, Permission.OPERATE_CASH, *hidden})


class WithoutLicensingTests(ApiTestCase):
    """De fábrica no hay licencias: ni periodo de prueba ni límite de usuarios."""

    modules = ModuleSet.defaults()

    def test_any_number_of_users(self):
        for number in range(6):
            response = self.api("POST", "/api/v1/users", json={
                "username": f"cajero{number}", "full_name": f"Cajero {number}", "password": CASHIER_PASSWORD,
            })
            self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(self.api("GET", "/api/v1/license").status_code, 404)


class WithoutRolePermissionsTests(ApiTestCase):
    modules = ModuleSet.configure(disable={Module.ROLE_PERMISSIONS})

    def test_roles_use_factory_permissions_and_cannot_be_edited(self):
        with self.c.uow_factory() as uow:
            uow.roles.save(uow.roles.get().with_role("cashier", {Permission.SELL}))
            uow.commit()
        self.make_cashier()
        token = self.login("cajero", CASHIER_PASSWORD)
        permissions = self.api("GET", "/api/v1/auth/me", token).get_json()["permissions"]
        self.assertIn("operate_cash", permissions)  # de fábrica, no la personalización guardada
        response = self.api("PUT", "/api/v1/roles/cashier", json={"reset": True})
        self.assertEqual(response.status_code, 404)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class LogoTests(ApiTestCase):
    def upload(self, data: bytes, token: str | None = None):  # noqa: ANN201
        import io

        return self.api("PUT", "/api/v1/branding/logo", token, data={"file": (io.BytesIO(data), "logo.png")},
                        content_type="multipart/form-data")

    def test_upload_show_and_remove(self):
        self.assertIsNone(self.client.get("/api/v1/branding").get_json()["logo_version"])
        self.assertEqual(self.upload(PNG).status_code, 200)

        branding = self.client.get("/api/v1/branding").get_json()  # sin sesión: lo usa la pantalla de inicio
        self.assertEqual(branding["business_name"], "Tienda de prueba")
        self.assertIsNotNone(branding["logo_version"])
        image = self.client.get(f"/api/v1/branding/logo?v={branding['logo_version']}")
        self.assertEqual((image.status_code, image.mimetype, image.data), (200, "image/png", PNG))

        self.assertEqual(self.api("DELETE", "/api/v1/branding/logo").status_code, 204)
        self.assertEqual(self.client.get("/api/v1/branding/logo").status_code, 404)

    def test_only_images_from_the_administrator(self):
        rejected = self.upload(b"<svg onload=alert(1)>")
        self.assertEqual(rejected.status_code, 400, rejected.get_json())
        self.make_cashier()
        self.assertEqual(self.upload(PNG, self.login("cajero", CASHIER_PASSWORD)).status_code, 403)
