"""Métodos de pago configurables y su comportamiento (Strategy + registro).

- Agregar "Bancolombia" o "Transferencia" es solo configuración: un método de tipo ELECTRONIC.
- Un tipo de pago nuevo (bonos, puntos...) se agrega aquí con su comportamiento,
  sin modificar ventas ni caja (principio abierto/cerrado).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .shared.errors import ValidationError
from .shared.values import parse_enum


class PaymentKind(StrEnum):
    CASH = "cash"
    ELECTRONIC = "electronic"
    CREDIT = "credit"


@dataclass(frozen=True)
class PaymentBehavior:
    goes_to_cash_drawer: bool
    can_give_change: bool
    requires_customer: bool


_BEHAVIORS: dict[PaymentKind, PaymentBehavior] = {
    PaymentKind.CASH: PaymentBehavior(
        goes_to_cash_drawer=True, can_give_change=True, requires_customer=False
    ),
    PaymentKind.ELECTRONIC: PaymentBehavior(
        goes_to_cash_drawer=False, can_give_change=False, requires_customer=False
    ),
    PaymentKind.CREDIT: PaymentBehavior(
        goes_to_cash_drawer=False, can_give_change=False, requires_customer=True
    ),
}


def behavior_for(kind: PaymentKind) -> PaymentBehavior:
    return _BEHAVIORS[kind]


@dataclass(frozen=True, kw_only=True)
class PaymentMethodConfig:
    """Un método de pago tal como lo configura cada negocio."""

    code: str
    name: str
    kind: PaymentKind
    active: bool = True

    def __post_init__(self) -> None:
        code = (self.code or "").strip().lower()
        name = (self.name or "").strip()
        if not code or not name:
            raise ValidationError("Cada método de pago necesita código y nombre")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", parse_enum(PaymentKind, self.kind, "tipo de pago"))

    @property
    def behavior(self) -> PaymentBehavior:
        return behavior_for(self.kind)


DEFAULT_PAYMENT_METHODS: tuple[PaymentMethodConfig, ...] = (
    PaymentMethodConfig(code="efectivo", name="Efectivo", kind=PaymentKind.CASH),
    PaymentMethodConfig(code="nequi", name="Nequi", kind=PaymentKind.ELECTRONIC),
    PaymentMethodConfig(code="daviplata", name="Daviplata", kind=PaymentKind.ELECTRONIC),
    PaymentMethodConfig(code="tarjeta", name="Tarjeta débito/crédito", kind=PaymentKind.ELECTRONIC),
    PaymentMethodConfig(code="fiado", name="Fiado", kind=PaymentKind.CREDIT),
)
