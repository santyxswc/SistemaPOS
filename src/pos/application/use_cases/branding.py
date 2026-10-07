"""Marca del negocio: nombre y logo para la pantalla de inicio, el menú y el tiquete."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.branding import Logo
from ...domain.shared.errors import NotFoundError
from ...domain.users import Permission
from ..actor import Actor
from ..common import require_settings
from ..ports import Clock, UnitOfWorkFactory


@dataclass(frozen=True)
class Branding:
    business_name: str
    logo_version: str | None  # None: el negocio no tiene logo


class GetBranding:
    """Público: la pantalla de inicio de sesión la muestra antes de que alguien entre."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self) -> Branding:
        with self._uow(read_only=True) as uow:
            logo = uow.logo.get()
            return Branding(business_name=require_settings(uow).business_name, logo_version=logo and logo.version)


class GetLogo:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self) -> Logo:
        with self._uow(read_only=True) as uow:
            logo = uow.logo.get()
        if logo is None:
            raise NotFoundError("El negocio no tiene logo")
        return logo


class UpdateLogo:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, data: bytes) -> Logo:
        actor.require(Permission.MANAGE_SETTINGS)
        logo = Logo.from_upload(data, self._clock.now())
        with self._uow() as uow:
            uow.logo.save(logo)
            uow.commit()
        return logo


class RemoveLogo:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor) -> None:
        actor.require(Permission.MANAGE_SETTINGS)
        with self._uow() as uow:
            uow.logo.delete()
            uow.commit()
