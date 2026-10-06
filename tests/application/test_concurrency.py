"""Dos cajas vendiendo la última unidad al mismo tiempo: solo una puede ganar."""

import threading

from pos.domain.shared.errors import InsufficientStock

from ..support import PosTestCase


class ConcurrentSalesTests(PosTestCase):
    use_real_clock = True

    def test_last_unit_is_sold_only_once(self):
        product = self.make_product(stock="1")
        cashiers = [self.make_cashier("caja1"), self.make_cashier("caja2")]
        for cashier in cashiers:
            self.open_cash(cashier)

        results: list[str] = []
        start = threading.Barrier(len(cashiers))

        def sell(cashier):
            start.wait()
            try:
                self.sell(cashier, [(product, "1")], [("efectivo", "2500")])
                results.append("vendida")
            except InsufficientStock:
                results.append("sin stock")

        threads = [threading.Thread(target=sell, args=(cashier,)) for cashier in cashiers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(sorted(results), ["sin stock", "vendida"])
        self.assertEqual(str(self.stock_of(product)), "0.000")
