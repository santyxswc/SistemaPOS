"""Lectura y validación de la entrada HTTP: cuerpo JSON y parámetros de consulta."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from flask import request

from ...domain.shared.values import Money, TaxRate, to_decimal

_MISSING = object()
_TRUE = {"1", "true", "yes", "si", "sí"}


class InvalidPayload(Exception):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class Body:
    """Acceso tipado a un objeto JSON; los errores dicen exactamente qué campo falló."""

    def __init__(self, data: Mapping[str, Any], prefix: str = "") -> None:
        self._data = data
        self._prefix = prefix

    @classmethod
    def from_request(cls) -> Body:
        raw = request.get_data(cache=True)
        if not raw.strip():
            return cls({})
        try:
            data = json.loads(raw, parse_float=Decimal)  # los decimales llegan exactos, nunca como float
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise InvalidPayload("El cuerpo de la petición no es JSON válido") from None
        if not isinstance(data, dict):
            raise InvalidPayload("Se esperaba un objeto JSON")
        return cls(data)

    def has(self, key: str) -> bool:
        return key in self._data

    def reject_unknown(self, allowed: set[str]) -> None:
        unknown = set(self._data) - allowed
        if unknown:
            raise InvalidPayload(f"Campos no permitidos: {', '.join(sorted(unknown))}")

    def text(self, key: str, *, required: bool = True, default: str | None = None) -> Any:
        value = self._get(key, required)
        if value is None:
            return default
        if not isinstance(value, str):
            raise self._invalid(key, "debe ser texto")
        return value

    def boolean(self, key: str, *, required: bool = False, default: bool | None = None) -> Any:
        value = self._get(key, required)
        if value is None:
            return default
        if not isinstance(value, bool):
            raise self._invalid(key, "debe ser true o false")
        return value

    def integer(self, key: str, *, required: bool = False) -> int | None:
        value = self._get(key, required)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise self._invalid(key, "debe ser un número entero")
        return value

    def decimal(self, key: str, *, required: bool = True) -> Any:
        value = self._get(key, required)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
            raise self._invalid(key, "debe ser un número")
        return to_decimal(value, self._name(key))

    def money(self, key: str, *, required: bool = True) -> Any:
        value = self.decimal(key, required=required)
        return None if value is None else Money(value)

    def tax_rate(self, key: str, *, required: bool = False) -> TaxRate | None:
        value = self.decimal(key, required=required)
        return None if value is None else TaxRate(value)

    def uuid(self, key: str, *, required: bool = True) -> Any:
        value = self._get(key, required)
        if value is None:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            raise self._invalid(key, "no es un identificador válido") from None

    def object(self, key: str, *, required: bool = True) -> Body:
        value = self._get(key, required)
        if value is None:
            return Body({}, prefix=f"{self._name(key)}.")
        if not isinstance(value, dict):
            raise self._invalid(key, "debe ser un objeto")
        return Body(value, prefix=f"{self._name(key)}.")

    def strings(self, key: str, *, required: bool = True) -> list[str]:
        value = self._get(key, required)
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise self._invalid(key, "debe ser una lista de textos")
        return value

    def items(self, key: str, *, required: bool = True) -> list[Body]:
        value = self._get(key, required)
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise self._invalid(key, "debe ser una lista de objetos")
        return [Body(item, prefix=f"{self._name(key)}[{index}].") for index, item in enumerate(value)]

    def _get(self, key: str, required: bool) -> Any:
        value = self._data.get(key, _MISSING)
        if value is _MISSING or value is None:
            if required:
                raise InvalidPayload(f"El campo '{self._name(key)}' es obligatorio", self._name(key))
            return None
        return value

    def _name(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _invalid(self, key: str, problem: str) -> InvalidPayload:
        return InvalidPayload(f"'{self._name(key)}' {problem}", self._name(key))


def query_text(name: str) -> str | None:
    value = request.args.get(name, "").strip()
    return value or None


def query_bool(name: str, default: bool = False) -> bool:
    value = request.args.get(name)
    return default if value is None else value.strip().lower() in _TRUE


def query_int(name: str, default: int, *, minimum: int = 0, maximum: int = 1000) -> int:
    value = request.args.get(name)
    if value is None:
        return default
    try:
        number = int(value)
    except ValueError:
        raise InvalidPayload(f"'{name}' debe ser un número entero", name) from None
    return max(minimum, min(number, maximum))


def query_uuid(name: str) -> UUID | None:
    value = query_text(name)
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise InvalidPayload(f"'{name}' no es un identificador válido", name) from None


def query_date(name: str, default: date) -> date:
    value = query_text(name)
    if value is None:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InvalidPayload(f"'{name}' debe tener el formato AAAA-MM-DD", name) from None
