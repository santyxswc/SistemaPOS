"""Objetos de valor con aritmética exacta: dinero, cantidades y tasas de impuesto."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from typing import TypeVar

from .errors import ValidationError

_CENT = Decimal("0.01")
_QUANTITY_STEP = Decimal("0.001")

E = TypeVar("E", bound=Enum)


def required_text(value: str | None, label: str) -> str:
    """Texto obligatorio sin espacios sobrantes."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"El campo {label} es obligatorio")
    return cleaned


def to_decimal(value: object, field: str = "valor") -> Decimal:
    """Convierte texto, enteros o Decimal a Decimal.

    Rechaza float a propósito: 0.1 + 0.2 no da 0.3 en binario y en un POS eso
    termina en descuadres de caja.
    """
    if isinstance(value, (bool, float)):
        raise ValidationError(f"{field}: envíe el número como texto o entero")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(str(value).strip())
        except InvalidOperation:
            raise ValidationError(f"{field}: «{value}» no es un número válido") from None
    else:
        raise ValidationError(f"{field}: se esperaba un número")
    if not result.is_finite():
        raise ValidationError(f"{field}: debe ser un número finito")
    return result


_THOUSANDS_GROUPS = re.compile(r"\d{1,3}([.,]\d{3})+")


def parse_local_decimal(value: object, field: str = "valor") -> Decimal:
    """Lee números como los escribe la gente en Colombia: «$2.500», «2.500,50», «19 %», «1,5».

    - Con punto y coma a la vez, el último separador es el decimal: 2.500,50 y 2,500.50.
    - Con un solo tipo de separador repetido en grupos de tres (2.500 o 1.250.000) son miles.
    - En otro caso el separador es decimal: 2,5 o 2.75.
    Los Decimal (celdas numéricas de Excel) se aceptan tal cual.
    """
    if isinstance(value, Decimal) or isinstance(value, int) and not isinstance(value, bool):
        return to_decimal(value, field)
    text = re.sub(r"[\s$%]", "", str(value or "")).replace("COP", "")
    if not text:
        raise ValidationError(f"{field}: falta el número")
    sign = ""
    if text[0] in "+-":
        sign, text = ("-" if text[0] == "-" else ""), text[1:]
    if "." in text and "," in text:
        decimal_mark = "." if text.rfind(".") > text.rfind(",") else ","
        thousands = "," if decimal_mark == "." else "."
        text = text.replace(thousands, "").replace(decimal_mark, ".")
    elif _THOUSANDS_GROUPS.fullmatch(text) and len({ch for ch in text if ch in ".,"}) == 1:
        text = text.replace(".", "").replace(",", "")
    else:
        text = text.replace(",", ".")
    return to_decimal(sign + text, field)


def to_quantity(value: object, field: str = "cantidad") -> Decimal:
    """Cantidades con tres decimales (sirve para unidades, kilos, libras o litros)."""
    return to_decimal(value, field).quantize(_QUANTITY_STEP, rounding=ROUND_HALF_UP)


def format_quantity(value: Decimal) -> str:
    """5.000 → '5'; 2.500 → '2.5'."""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def parse_enum(enum_type: type[E], value: object, field: str) -> E:
    """Convierte un texto en un valor de Enum con un mensaje de error claro."""
    try:
        return enum_type(value)
    except ValueError:
        options = ", ".join(str(member.value) for member in enum_type)
        raise ValidationError(f"{field}: «{value}» no es válido (opciones: {options})") from None


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """Dinero en la moneda del negocio, siempre redondeado a centavos (ROUND_HALF_UP)."""

    amount: Decimal

    def __post_init__(self) -> None:
        exact = to_decimal(self.amount, "monto").quantize(_CENT, rounding=ROUND_HALF_UP)
        if exact.is_zero():
            exact = exact.copy_abs()  # evita "-0.00"
        object.__setattr__(self, "amount", exact)

    @classmethod
    def zero(cls) -> Money:
        return cls(Decimal(0))

    @classmethod
    def of(cls, value: object, field: str = "monto") -> Money:
        return cls(to_decimal(value, field))

    @classmethod
    def sum(cls, values: Iterable[Money]) -> Money:
        total = cls.zero()
        for value in values:
            total = total + value
        return total

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_positive(self) -> bool:
        return self.amount > 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.amount + other.amount)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.amount - other.amount)

    def __mul__(self, factor: object) -> Money:
        if isinstance(factor, bool) or not isinstance(factor, (int, Decimal)):
            return NotImplemented
        return Money(self.amount * factor)

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        return Money(-self.amount)

    def display(self) -> str:
        """Formato colombiano para mensajes: $12.500 o $12.500,50."""
        sign = "-" if self.amount < 0 else ""
        whole, cents = f"{abs(self.amount):,.2f}".split(".")
        whole = whole.replace(",", ".")
        return f"{sign}${whole}" if cents == "00" else f"{sign}${whole},{cents}"

    def __str__(self) -> str:
        return str(self.amount)


@dataclass(frozen=True, slots=True)
class TaxRate:
    """Porcentaje de impuesto: 19 o 5 (IVA), 8 (impuesto al consumo), 0 (exento)."""

    percent: Decimal

    def __post_init__(self) -> None:
        value = to_decimal(self.percent, "impuesto")
        if not Decimal(0) <= value <= Decimal(100):
            raise ValidationError("El impuesto debe estar entre 0 y 100 %")
        object.__setattr__(self, "percent", value.quantize(_CENT))

    @classmethod
    def of(cls, value: object) -> TaxRate:
        return cls(to_decimal(value, "impuesto"))

    @property
    def fraction(self) -> Decimal:
        return self.percent / 100

    def __str__(self) -> str:
        return format_quantity(self.percent)
