"""Concurrencia: dos cajas vendiendo la última unidad, y lecturas que no esperan a quien escribe."""

import sqlite3
import threading
import time

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


class ReadOnlyTransactionTests(PosTestCase):
    def test_queries_do_not_wait_for_a_writer(self):
        product = self.make_product()
        writer = self.c.uow_factory()
        with writer:  # una escritura en curso tiene tomado el candado de la base de datos
            started = time.perf_counter()
            self.assertEqual(self.c.get_product.execute(product.id).name, product.name)
            self.assertEqual(len(self.c.search_products.execute(text="arroz")), 1)
            self.assertLess(time.perf_counter() - started, 1.0)

    def test_read_only_unit_of_work_cannot_write(self):
        product = self.make_product()
        with self.c.uow_factory(read_only=True) as uow:
            loaded = uow.products.get(product.id)
            with self.assertRaises(sqlite3.OperationalError):
                uow.products.save(loaded)
            with self.assertRaises(RuntimeError):
                uow.commit()
