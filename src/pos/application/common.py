"""Utilidades compartidas por los casos de uso."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import TypeVar

from ..domain.settings import BusinessSettings
from ..domain.shared.errors import BusinessRuleViolation, NotFoundError, ValidationError
from .ports import UnitOfWork

T = TypeVar("T")

MAX_PAGE_SIZE = 200


def require_settings(uow: UnitOfWork) -> BusinessSettings:
    settings = uow.settings.get()
    if settings is None:
        raise BusinessRuleViolation("El sistema no está configurado: ejecute la instalación inicial")
    return settings


def get_or_404(value: T | None, message: str) -> T:
    if value is None:
        raise NotFoundError(message)
    return value


def page_size(limit: int, maximum: int = MAX_PAGE_SIZE) -> int:
    return max(1, min(limit, maximum))


def local_day_range(date_from: date, date_to: date, tz: tzinfo) -> tuple[datetime, datetime]:
    """Convierte días locales del negocio (inclusive) a un rango UTC [inicio, fin)."""
    if date_to < date_from:
        raise ValidationError("La fecha inicial no puede ser posterior a la final")
    if (date_to - date_from).days > 366:
        raise ValidationError("El rango máximo es de un año")
    start = datetime.combine(date_from, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return start, end
