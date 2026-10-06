"""Permisos por rol personalizados por cada negocio."""

from pos.domain.shared.errors import BusinessRuleViolation, PermissionDenied, ValidationError
from pos.domain.users import ROLE_PERMISSIONS, Permission, Role, RolePermissions

from ..support import CASHIER_PASSWORD, ApiTestCase, PosTestCase


class RolePermissionsDomainTests(PosTestCase):
    def test_admin_always_has_everything_and_others_start_with_factory_defaults(self):
        policy = RolePermissions()
        self.assertEqual(policy.for_role(Role.ADMIN), frozenset(Permission))
        self.assertEqual(policy.for_role(Role.CASHIER), ROLE_PERMISSIONS[Role.CASHIER])
        self.assertFalse(policy.is_customized(Role.CASHIER))

    def test_admin_only_permissions_cannot_be_granted(self):
        with self.assertRaisesRegex(ValidationError, "Solo el administrador"):
            RolePermissions({Role.SUPERVISOR: {Permission.MANAGE_USERS}})
        with self.assertRaisesRegex(ValidationError, "no se pueden cambiar"):
            RolePermissions({Role.ADMIN: set()})


class RolePermissionsUseCaseTests(PosTestCase):
    use_real_clock = True  # los JWT se validan contra la hora real

    def test_letting_cashiers_see_reports_applies_on_their_next_request(self):
        self.make_cashier()
        token = self.c.login.execute("cajero", CASHIER_PASSWORD).token
        before = self.c.resolve_actor.execute(token)
        self.assertFalse(before.can(Permission.VIEW_REPORTS))

        self.c.update_role_permissions.execute(
            self.admin, Role.CASHIER, {*ROLE_PERMISSIONS[Role.CASHIER], Permission.VIEW_REPORTS}
        )

        after = self.c.resolve_actor.execute(token)
        self.assertTrue(after.can(Permission.VIEW_REPORTS))
        self.assertTrue(self.c.get_role_permissions.execute(self.admin).is_customized(Role.CASHIER))

    def test_taking_away_a_permission_and_resetting(self):
        self.make_cashier()
        token = self.c.login.execute("cajero", CASHIER_PASSWORD).token
        self.c.update_role_permissions.execute(self.admin, Role.CASHIER, {Permission.SELL, Permission.OPERATE_CASH})
        self.assertFalse(self.c.resolve_actor.execute(token).can(Permission.MANAGE_CUSTOMERS))

        policy = self.c.update_role_permissions.execute(self.admin, Role.CASHIER, None)

        self.assertFalse(policy.is_customized(Role.CASHIER))
        self.assertTrue(self.c.resolve_actor.execute(token).can(Permission.MANAGE_CUSTOMERS))

    def test_only_who_manages_users_can_change_roles_and_admin_cannot_be_changed(self):
        cashier = self.make_cashier()
        with self.assertRaises(PermissionDenied):
            self.c.update_role_permissions.execute(cashier, Role.CASHIER, {Permission.VIEW_REPORTS})
        with self.assertRaises(BusinessRuleViolation):
            self.c.update_role_permissions.execute(self.admin, Role.ADMIN, set())


class RolePermissionsApiTests(ApiTestCase):
    def test_list_and_update_over_http(self):
        roles = self.api("GET", "/api/v1/roles").get_json()
        cashier = next(r for r in roles["roles"] if r["role"] == "cashier")
        self.assertEqual((cashier["label"], cashier["editable"], cashier["customized"]), ("Cajero", True, False))
        admin = next(r for r in roles["roles"] if r["role"] == "admin")
        self.assertFalse(admin["editable"])
        grantable = {p["code"]: p["grantable"] for p in roles["permissions"]}
        self.assertEqual((grantable["manage_users"], grantable["view_reports"]), (False, True))

        updated = self.api("PUT", "/api/v1/roles/cashier", json={"permissions": ["sell", "operate_cash",
                                                                                  "view_reports"]})
        self.assertEqual(updated.status_code, 200, updated.get_json())
        cashier = next(r for r in updated.get_json()["roles"] if r["role"] == "cashier")
        self.assertEqual(cashier["permissions"], ["operate_cash", "sell", "view_reports"])

        self.api("POST", "/api/v1/users", json={"username": "luis", "full_name": "Luis", "password": CASHIER_PASSWORD})
        me = self.api("GET", "/api/v1/auth/me", token=self.login("luis", CASHIER_PASSWORD)).get_json()
        self.assertEqual(me["permissions"], ["operate_cash", "sell", "view_reports"])

        reset = self.api("PUT", "/api/v1/roles/cashier", json={"reset": True}).get_json()
        self.assertFalse(next(r for r in reset["roles"] if r["role"] == "cashier")["customized"])

    def test_rejects_reserved_or_unknown_permissions(self):
        reserved = self.api("PUT", "/api/v1/roles/supervisor", json={"permissions": ["manage_settings"]})
        self.assertEqual(reserved.status_code, 400)
        unknown = self.api("PUT", "/api/v1/roles/supervisor", json={"permissions": ["volar"]})
        self.assertEqual(unknown.status_code, 400)
        not_a_list = self.api("PUT", "/api/v1/roles/supervisor", json={"permissions": "sell"})
        self.assertEqual(not_a_list.get_json()["error"]["field"], "permissions")
