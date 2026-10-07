"""Utilidades de prueba: reloj controlable y un contenedor real sobre SQLite temporal."""

from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pos.application.actor import Actor
from pos.application.modules import ModuleSet
from pos.application.use_cases.catalog import CreateProductCommand
from pos.application.use_cases.sales import CreateSaleCommand, PaymentInput, SaleItemInput
from pos.application.use_cases.users import CreateUserCommand
from pos.bootstrap import build_container
from pos.config import AppConfig
from pos.domain.catalog import Product
from pos.domain.licensing import License
from pos.domain.sales import Sale
from pos.domain.shared.values import Money
from pos.infrastructure.licensing import Ed25519LicenseVerifier, public_key_text, sign_license

ADMIN_PASSWORD = "clave-segura-1"
CASHIER_PASSWORD = "clave-segura-2"

# Clave de licencias solo para pruebas: el programa real trae la pública del proveedor.
TEST_LICENSE_KEY = Ed25519PrivateKey.generate()
TEST_LICENSE_VERIFIER = Ed25519LicenseVerifier(public_key_text(TEST_LICENSE_KEY))


def issue_license(
    *, plan: str = "Mediano", max_users: int | None = 3, issued_on: date = date(2026, 10, 1),
    expires_on: date | None = date(2027, 10, 1), business_name: str = "Tienda de prueba",
) -> str:
    license = License(license_id="prueba-1", business_name=business_name, plan=plan, max_users=max_users,
                      issued_on=issued_on, expires_on=expires_on)
    return sign_license(license, TEST_LICENSE_KEY)


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
    # Las pruebas existentes cubren todas las funciones; las de módulos apagan los que necesiten.
    modules = ModuleSet.all()

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clock = FixedClock()
        config = AppConfig(
            database_path=os.path.join(tmp.name, "pos.sqlite3"),
            secret_key="s" * 48,
            password_iterations=1_000,  # rápido en pruebas; en producción 600.000
            business_name="Tienda de prueba",
            modules=self.modules,
        )
        self.c = build_container(
            config,
            clock=None if self.use_real_clock else self.clock,
            license_verifier=TEST_LICENSE_VERIFIER,
            invoice_provider=self.make_invoice_provider(),
        )
        admin = self.c.bootstrap_admin.execute(username="admin", full_name="Dueña", password=ADMIN_PASSWORD)
        self.admin = Actor.from_user(admin)

    def make_invoice_provider(self):  # noqa: ANN201 - las pruebas de facturación devuelven uno falso
        return None

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


class ApiTestCase(PosTestCase):
    """La API por HTTP con el cliente de pruebas de Flask, ya con sesión de administrador."""

    use_real_clock = True  # los JWT se validan contra la hora real

    def setUp(self) -> None:
        super().setUp()
        from pos.presentation.http.app import create_app

        self.client = create_app(self.c).test_client()
        self.token = self.login("admin", ADMIN_PASSWORD)

    def login(self, username: str, password: str) -> str:
        response = self.client.post("/api/v1/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["access_token"]

    def api(self, method: str, url: str, token: str | None = None, **kwargs):  # noqa: ANN201
        headers = {"Authorization": f"Bearer {token or self.token}"}
        return self.client.open(url, method=method, headers=headers, **kwargs)


def tamper(code: str) -> str:
    """Cambia un carácter de la firma. Se toca el medio: el último carácter de base64 lleva
    bits de relleno que el decodificador ignora, y cambiarlo puede no alterar la firma."""
    prefix, data, signature = code.split(".")
    middle = len(signature) // 2
    replacement = "A" if signature[middle] != "A" else "B"
    return f"{prefix}.{data}.{signature[:middle]}{replacement}{signature[middle + 1:]}"
