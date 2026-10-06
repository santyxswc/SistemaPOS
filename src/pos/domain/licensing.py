"""Licencia de uso: qué plan compró el negocio y qué pasa cuando no hay licencia o vence.

Las reglas comerciales viven aquí, en un solo lugar. La firma criptográfica que
impide falsificar una licencia es asunto de la infraestructura.

Política:
- Sin licencia, el sistema funciona completo en modo de prueba por TRIAL_DAYS días.
- Con licencia vigente, el límite de usuarios es el del plan comprado.
- Con la prueba o la licencia vencidas, el negocio sigue vendiendo (nunca se
  secuestran los datos ni se detiene una caja), pero no se pueden crear ni
  reactivar usuarios por encima de EXPIRED_MAX_USERS y los administradores ven el aviso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .shared.errors import ValidationError
from .shared.values import required_text

TRIAL_DAYS = 30
TRIAL_MAX_USERS = 3
EXPIRED_MAX_USERS = 1
WARN_DAYS_BEFORE_EXPIRY = 15


@dataclass(frozen=True, kw_only=True)
class License:
    """Lo que dice una licencia emitida por el proveedor del sistema."""

    license_id: str
    business_name: str
    plan: str
    max_users: int | None  # None = sin límite
    issued_on: date
    expires_on: date | None = None  # None = no vence

    def __post_init__(self) -> None:
        object.__setattr__(self, "license_id", required_text(self.license_id, "id de la licencia"))
        object.__setattr__(self, "business_name", required_text(self.business_name, "negocio de la licencia"))
        object.__setattr__(self, "plan", required_text(self.plan, "plan"))
        if self.max_users is not None and self.max_users < 1:
            raise ValidationError("La licencia debe permitir al menos un usuario")
        if self.expires_on is not None and self.expires_on < self.issued_on:
            raise ValidationError("La licencia vence antes de haber sido emitida")


class LicenseState(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    TRIAL_EXPIRED = "trial_expired"
    EXPIRED = "expired"


@dataclass(frozen=True, kw_only=True)
class LicenseStatus:
    state: LicenseState
    max_users: int | None
    expires_on: date | None
    days_left: int | None
    license: License | None = None

    @property
    def is_valid(self) -> bool:
        return self.state in (LicenseState.TRIAL, LicenseState.ACTIVE)

    @property
    def needs_attention(self) -> bool:
        """Los administradores deben ver un aviso: vencida o a punto de vencer."""
        if not self.is_valid:
            return True
        return self.days_left is not None and self.days_left <= WARN_DAYS_BEFORE_EXPIRY

    @property
    def message(self) -> str:
        days = self.days_left
        match self.state:
            case LicenseState.TRIAL:
                return f"Periodo de prueba: {'queda 1 día' if days == 1 else f'quedan {days} días'}"
            case LicenseState.TRIAL_EXPIRED:
                return "El periodo de prueba terminó. Comuníquese con su proveedor para activar la licencia."
            case LicenseState.EXPIRED:
                return "La licencia venció. Comuníquese con su proveedor para renovarla."
        plan = self.license.plan if self.license else ""
        if days is None:
            return f"Licencia {plan} activa, sin vencimiento"
        return f"Licencia {plan} activa: vence en {days} día{'s' if days != 1 else ''}"


def evaluate_license(license: License | None, *, installed_on: date, today: date) -> LicenseStatus:
    """Decide el estado de la licencia en una fecha (la del negocio, no la UTC)."""
    if license is None:
        trial_end = date.fromordinal(installed_on.toordinal() + TRIAL_DAYS)
        days_left = (trial_end - today).days
        if days_left > 0:
            return LicenseStatus(
                state=LicenseState.TRIAL, max_users=TRIAL_MAX_USERS, expires_on=trial_end, days_left=days_left
            )
        return LicenseStatus(
            state=LicenseState.TRIAL_EXPIRED, max_users=EXPIRED_MAX_USERS, expires_on=trial_end, days_left=0
        )

    if license.expires_on is None:
        return LicenseStatus(
            state=LicenseState.ACTIVE, max_users=license.max_users, expires_on=None, days_left=None, license=license
        )
    days_left = (license.expires_on - today).days
    if days_left >= 0:  # el día del vencimiento todavía es válido
        return LicenseStatus(
            state=LicenseState.ACTIVE,
            max_users=license.max_users,
            expires_on=license.expires_on,
            days_left=days_left,
            license=license,
        )
    return LicenseStatus(
        state=LicenseState.EXPIRED,
        max_users=EXPIRED_MAX_USERS,
        expires_on=license.expires_on,
        days_left=0,
        license=license,
    )
