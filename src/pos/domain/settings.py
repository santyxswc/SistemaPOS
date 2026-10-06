"""Configuración del negocio: todo lo que cambia de un cliente a otro sin tocar código."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .payments import DEFAULT_PAYMENT_METHODS, PaymentMethodConfig
from .shared.errors import ValidationError
from .shared.values import TaxRate
from .taxes import TaxExcludedPolicy, TaxIncludedPolicy, TaxPolicy


@dataclass(frozen=True, kw_only=True)
class BusinessSettings:
    business_name: str
    tax_id: str = ""
    address: str = ""
    phone: str = ""
    currency: str = "COP"
    timezone: str = "America/Bogota"
    prices_include_tax: bool = True
    default_tax_rate: TaxRate = field(default_factory=lambda: TaxRate.of(19))
    allow_negative_stock: bool = False
    credit_sales_enabled: bool = True
    max_users: int | None = 3
    receipt_footer: str = "¡Gracias por su compra!"
    payment_methods: tuple[PaymentMethodConfig, ...] = DEFAULT_PAYMENT_METHODS

    def __post_init__(self) -> None:
        if not self.business_name.strip():
            raise ValidationError("El nombre del negocio es obligatorio")
        if self.max_users is not None and self.max_users < 1:
            raise ValidationError("El máximo de usuarios debe ser mayor que cero")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValidationError(f"Zona horaria desconocida: {self.timezone}") from None
        codes = [method.code for method in self.payment_methods]
        if len(codes) != len(set(codes)):
            raise ValidationError("Hay métodos de pago con el código repetido")
        if not any(method.active for method in self.payment_methods):
            raise ValidationError("Debe haber al menos un método de pago activo")

    @property
    def tax_policy(self) -> TaxPolicy:
        return TaxIncludedPolicy() if self.prices_include_tax else TaxExcludedPolicy()

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def payment_method(self, code: str) -> PaymentMethodConfig:
        wanted = (code or "").strip().lower()
        for method in self.payment_methods:
            if method.code == wanted and method.active:
                return method
        raise ValidationError(f"Método de pago no disponible: {code}")

    def updated(self, **changes: object) -> BusinessSettings:
        """Devuelve una copia validada con los cambios aplicados (la configuración es inmutable)."""
        known = {f.name for f in dataclasses.fields(self)}
        unknown = set(changes) - known
        if unknown:
            raise ValidationError(f"Campos de configuración desconocidos: {', '.join(sorted(unknown))}")
        return dataclasses.replace(self, **changes)  # type: ignore[arg-type]
