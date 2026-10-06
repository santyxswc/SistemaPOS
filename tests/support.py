"""Utilidades de prueba: reloj controlable y un contenedor real sobre SQLite temporal."""

from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from pos.application.actor import Actor
from pos.application.use_cases.catalog import CreateProductCommand
from pos.application.use_cases.sales import CreateSaleCommand, PaymentInput, SaleItemInput
from pos.application.use_cases.users import CreateUserCommand
from pos.bootstrap import build_container
from pos.config import AppConfig
from pos.domain.catalog import Product
from pos.domain.sales import Sale
from pos.domain.shared.values import Money

ADMIN_PASSWORD = "clave-segura-1"
CASHIER_PASSWORD = "clave-segura-2"


class FixedClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 10, 5, 15, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)


class PosTestCase(unittest.TestCase):
    """Cada prueba usa una base de datos nueva y el contenedor real de la aplicación."""

    use_real_clock = False

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clock = FixedClock()
        config = AppConfig(
            database_path=os.path.join(tmp.name, "pos.sqlite3"),
            secret_key="s" * 48,
            password_iterations=1_000,  # rápido en pruebas; en producción 600.000
            business_name="Tienda de prueba",
        )
        self.c = build_container(config, clock=None if self.use_real_clock else self.clock)
        admin = self.c.bootstrap_admin.execute(username="admin", full_name="Dueña", password=ADMIN_PASSWORD)
        self.admin = Actor.from_user(admin)

    def make_cashier(self, username: str = "cajero") -> Actor:
        user = self.c.create_user.execute(
            self.admin, CreateUserCommand(username=username, full_name="Cajero Uno", password=CASHIER_PASSWORD)
        )
        return Actor.from_user(user)

    def make_product(
        self, sku: str = "ARROZ-500", name: str = "Arroz Diana 500 g", price: str = "2500", stock: str = "10", **extra
    ) -> Product:
        command = CreateProductCommand(sku=sku, name=name, price=Money.of(price), initial_stock=Decimal(stock), **extra)
        return self.c.create_product.execute(self.admin, command)

    def open_cash(self, actor: Actor, amount: str = "50000") -> None:
        self.c.open_cash_session.execute(actor, Money.of(amount))

    def sell(
        self,
        actor: Actor,
        items: Sequence[tuple[Product, str] | tuple[Product, str, str]],
        payments: Sequence[tuple[str, str]],
        customer_id: UUID | None = None,
    ) -> Sale:
        command = CreateSaleCommand(
            items=[
                SaleItemInput(
                    product_id=item[0].id,
                    quantity=Decimal(item[1]),
                    discount=Money.of(item[2]) if len(item) == 3 else None,
                )
                for item in items
            ],
            payments=[PaymentInput(method=method, amount=Money.of(amount)) for method, amount in payments],
            customer_id=customer_id,
        )
        return self.c.create_sale.execute(actor, command)

    def stock_of(self, product: Product) -> Decimal:
        return self.c.get_product.execute(product.id).stock
