"""La licencia hace cumplir el plan sin detener nunca las ventas."""

from datetime import date

from pos.application.use_cases.users import CreateUserCommand, UpdateUserCommand
from pos.domain.licensing import LicenseState
from pos.domain.shared.errors import BusinessRuleViolation, NotFoundError, PermissionDenied, ValidationError

from ..support import CASHIER_PASSWORD, PosTestCase, issue_license, tamper


class LicenseUseCaseTests(PosTestCase):
    def new_user(self, username):
        return self.c.create_user.execute(
            self.admin, CreateUserCommand(username=username, full_name=username.title(), password=CASHIER_PASSWORD)
        )

    def test_a_new_installation_starts_its_trial(self):
        status = self.c.get_license_status.execute()
        self.assertEqual((status.state, status.days_left), (LicenseState.TRIAL, 30))

    def test_installing_a_license_applies_its_user_limit(self):
        status = self.c.install_license.execute(self.admin, issue_license(max_users=2))
        self.assertEqual((status.state, status.max_users), (LicenseState.ACTIVE, 2))

        self.new_user("caja1")  # admin + caja1 = 2
        with self.assertRaisesRegex(BusinessRuleViolation, "Su plan permite 2 usuarios"):
            self.new_user("caja2")

    def test_reactivating_a_user_also_counts(self):
        self.c.install_license.execute(self.admin, issue_license(max_users=2))
        cashier = self.new_user("caja1")
        self.c.update_user.execute(self.admin, cashier.id, UpdateUserCommand(active=False))
        self.new_user("caja2")
        with self.assertRaises(BusinessRuleViolation):
            self.c.update_user.execute(self.admin, cashier.id, UpdateUserCommand(active=True))

    def test_when_the_trial_ends_sales_continue_but_no_more_users(self):
        cashier = self.make_cashier()
        product = self.make_product()
        self.clock.advance(days=31)

        status = self.c.get_license_status.execute()
        self.assertEqual(status.state, LicenseState.TRIAL_EXPIRED)
        with self.assertRaisesRegex(BusinessRuleViolation, "periodo de prueba terminó"):
            self.new_user("caja2")
        self.open_cash(cashier)
        self.sell(cashier, [(product, "1")], [("efectivo", "2500")])  # la tienda nunca se detiene

    def test_expired_licenses_are_rejected_when_installing(self):
        code = issue_license(issued_on=date(2025, 1, 1), expires_on=date(2025, 12, 31))
        with self.assertRaisesRegex(BusinessRuleViolation, "venció"):
            self.c.install_license.execute(self.admin, code)

    def test_only_who_manages_settings_can_install(self):
        with self.assertRaises(PermissionDenied):
            self.c.install_license.execute(self.make_cashier(), issue_license())

    def test_forged_code_is_rejected_and_a_tampered_stored_code_counts_as_no_license(self):
        with self.assertRaises(ValidationError):
            self.c.install_license.execute(self.admin, "POS1.e30.AAAA")
        self.c.install_license.execute(self.admin, issue_license(max_users=10))
        with self.c.uow_factory() as uow:
            uow.licensing.save_code(tamper(issue_license(max_users=10)))
            uow.commit()
        self.assertEqual(self.c.get_license_status.execute().state, LicenseState.TRIAL)


class ResetPasswordFromConsoleTests(PosTestCase):
    def test_sets_a_new_password_and_reactivates_the_account(self):
        cashier = self.make_cashier()
        self.c.update_user.execute(self.admin, cashier.user_id, UpdateUserCommand(active=False))

        self.c.reset_password_from_console.execute("CAJERO ", "clave-nueva-1")

        result = self.c.login.execute("cajero", "clave-nueva-1")
        self.assertTrue(result.user.active)

    def test_unknown_user_lists_the_administrators(self):
        with self.assertRaisesRegex(NotFoundError, "Administradores registrados: admin"):
            self.c.reset_password_from_console.execute("dueno", "clave-nueva-1")

    def test_validates_the_password(self):
        with self.assertRaises(ValidationError):
            self.c.reset_password_from_console.execute("admin", "corta")
