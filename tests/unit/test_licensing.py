"""Reglas de la licencia y firma de los códigos."""

import unittest
from datetime import date

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pos.domain.licensing import (
    EXPIRED_MAX_USERS,
    TRIAL_DAYS,
    TRIAL_MAX_USERS,
    License,
    LicenseState,
    evaluate_license,
)
from pos.domain.shared.errors import ValidationError
from pos.infrastructure.licensing import Ed25519LicenseVerifier, public_key_text, sign_license

from ..support import TEST_LICENSE_KEY, TEST_LICENSE_VERIFIER, issue_license, tamper

INSTALLED = date(2026, 10, 1)


def a_license(**changes):
    data = dict(license_id="L1", business_name="Tienda", plan="Básico", max_users=2,
                issued_on=date(2026, 10, 1), expires_on=date(2027, 10, 1))
    data.update(changes)
    return License(**data)


class LicensePolicyTests(unittest.TestCase):
    def test_without_license_the_trial_is_complete_and_then_limited(self):
        trial = evaluate_license(None, installed_on=INSTALLED, today=date(2026, 10, 11))
        self.assertEqual((trial.state, trial.max_users, trial.days_left), (LicenseState.TRIAL, TRIAL_MAX_USERS, 20))
        self.assertTrue(trial.is_valid)

        last_day = evaluate_license(None, installed_on=INSTALLED, today=date(2026, 10, TRIAL_DAYS))
        self.assertEqual(last_day.days_left, 1)

        over = evaluate_license(None, installed_on=INSTALLED, today=date(2026, 11, 1))
        self.assertEqual((over.state, over.max_users), (LicenseState.TRIAL_EXPIRED, EXPIRED_MAX_USERS))
        self.assertFalse(over.is_valid)
        self.assertTrue(over.needs_attention)

    def test_active_license_uses_the_plan_until_the_last_day_inclusive(self):
        license = a_license(max_users=5, expires_on=date(2027, 1, 31))
        active = evaluate_license(license, installed_on=INSTALLED, today=date(2027, 1, 31))
        self.assertEqual((active.state, active.max_users, active.days_left), (LicenseState.ACTIVE, 5, 0))
        self.assertTrue(active.needs_attention)  # vence hoy: hay que avisar

        expired = evaluate_license(license, installed_on=INSTALLED, today=date(2027, 2, 1))
        self.assertEqual((expired.state, expired.max_users), (LicenseState.EXPIRED, EXPIRED_MAX_USERS))

    def test_perpetual_license_without_user_limit(self):
        status = evaluate_license(a_license(max_users=None, expires_on=None), installed_on=INSTALLED,
                                  today=date(2040, 1, 1))
        self.assertEqual((status.state, status.max_users, status.days_left), (LicenseState.ACTIVE, None, None))
        self.assertFalse(status.needs_attention)

    def test_rejects_inconsistent_licenses(self):
        with self.assertRaises(ValidationError):
            a_license(max_users=0)
        with self.assertRaises(ValidationError):
            a_license(expires_on=date(2026, 1, 1))


class LicenseSignatureTests(unittest.TestCase):
    def test_round_trip_keeps_every_field(self):
        code = issue_license(business_name="Panadería Ñapa", max_users=None, expires_on=None)
        license = TEST_LICENSE_VERIFIER.verify(code)
        self.assertEqual((license.business_name, license.max_users, license.expires_on), ("Panadería Ñapa", None, None))

    def test_tolerates_line_breaks_from_chat_apps(self):
        code = issue_license()
        wrapped = "\n".join(code[i : i + 40] for i in range(0, len(code), 40))
        self.assertEqual(TEST_LICENSE_VERIFIER.verify(f"  {wrapped}\n").plan, "Mediano")

    def test_changing_any_data_breaks_the_signature(self):
        code = issue_license(max_users=3)
        prefix, _, signature = code.split(".")
        other_data = issue_license(max_users=99).split(".")[1]  # datos de otra licencia con la firma original
        for bad in (f"{prefix}.{other_data}.{signature}", tamper(code), "hola", ""):
            with self.subTest(code=bad[:20]), self.assertRaises(ValidationError):
                TEST_LICENSE_VERIFIER.verify(bad)

    def test_a_license_signed_with_another_key_is_rejected(self):
        intruder = Ed25519PrivateKey.generate()
        code = sign_license(a_license(), intruder)
        with self.assertRaises(ValidationError):
            TEST_LICENSE_VERIFIER.verify(code)
        self.assertEqual(Ed25519LicenseVerifier(public_key_text(intruder)).verify(code).plan, "Básico")

    def test_the_test_key_is_not_the_product_key(self):
        from pos.infrastructure.license_key import PUBLIC_KEY

        self.assertNotEqual(public_key_text(TEST_LICENSE_KEY), PUBLIC_KEY)
