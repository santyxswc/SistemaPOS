"""Configuración del negocio."""

from __future__ import annotations

from collections.abc import Mapping

from ...domain.settings import BusinessSettings
from ...domain.users import Permission
from ..actor import Actor
from ..common import require_settings
from ..ports import UnitOfWorkFactory


class EnsureSettings:
    """Crea la configuración por defecto en la instalación inicial."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, business_name: str) -> BusinessSettings:
        with self._uow() as uow:
            settings = uow.settings.get()
            if settings is None:
                settings = BusinessSettings(business_name=business_name)
                uow.settings.save(settings)
                uow.commit()
        return settings


class GetSettings:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self) -> BusinessSettings:
        with self._uow() as uow:
            return require_settings(uow)


class UpdateSettings:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, changes: Mapping[str, object]) -> BusinessSettings:
        actor.require(Permission.MANAGE_SETTINGS)
        with self._uow() as uow:
            settings = require_settings(uow).updated(**changes)
            uow.settings.save(settings)
            uow.commit()
        return settings
