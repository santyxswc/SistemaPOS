from decimal import Decimal
from unittest import TestCase

from pos.domain.shared.errors import ValidationError
from pos.domain.shared.values import Money, TaxRate
from pos.domain.taxes import TaxExcludedPolicy, TaxIncludedPolicy


class MoneyTests(TestCase):
    def test_rounds_half_up_to_cents(self):
        self.assertEqual(Money.of("10.005").amount, Decimal("10.01"))

    def test_arithmetic_is_exact(self):
        self.assertEqual(Money.of("0.1") + Money.of("0.2"), Money.of("0.3"))

    def test_rejects_binary_floats(self):
        with self.assertRaises(ValidationError):
            Money.of(0.1)

    def test_rejects_garbage(self):
        with self.assertRaises(ValidationError):
            Money.of("doce mil")

    def test_colombian_display_format(self):
        self.assertEqual(Money.of("12500").display(), "$12.500")
        self.assertEqual(Money.of("1234567.5").display(), "$1.234.567,50")

    def test_no_negative_zero(self):
        self.assertEqual(str(-Money.zero()), "0.00")


class TaxPolicyTests(TestCase):
    def test_price_with_tax_included_is_split(self):
        result = TaxIncludedPolicy().breakdown(Money.of("11900"), TaxRate.of(19))
        self.assertEqual((result.base, result.tax, result.total), (Money.of(10000), Money.of(1900), Money.of(11900)))

    def test_tax_added_on_top(self):
        result = TaxExcludedPolicy().breakdown(Money.of("10000"), TaxRate.of(19))
        self.assertEqual(result.total, Money.of("11900"))

    def test_base_plus_tax_always_equals_total(self):
        result = TaxIncludedPolicy().breakdown(Money.of("999.99"), TaxRate.of(19))
        self.assertEqual(result.base + result.tax, result.total)

    def test_rate_must_be_a_percentage(self):
        with self.assertRaises(ValidationError):
            TaxRate.of(101)
