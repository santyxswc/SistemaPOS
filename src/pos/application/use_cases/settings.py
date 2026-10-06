"""Configuración del negocio."""

from __future__ import annotations

from collections.abc import Mapping

from ...domain.settings import BusinessSettings
from ...domain.users import Permission
from ..actor import Actor
from ..common import require_settings
from ..ports import BackupService, Clock, UnitOfWorkFactory


class EnsureSettings:
    """Prepara una instalación nueva: configuración por defecto y fecha de instalación.

    La fecha marca el inicio del periodo de prueba. Una instalación anterior a las
    licencias la recibe la primera vez que arranca con esta versión.
    """

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, business_name: str) -> BusinessSettings:
        with self._uow() as uow:
            settings = uow.settings.get()
            changed = False
            if settings is None:
                settings = BusinessSettings(business_name=business_name)
                uow.settings.save(settings)
                changed = True
            if uow.licensing.get_installed_at() is None:
                uow.licensing.save_installed_at(self._clock.now())
                changed = True
            if changed:
                uow.commit()
        return settings


class GetSettings:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self) -> BusinessSettings:
        with self._uow(read_only=True) as uow:
            return require_settings(uow)


class UpdateSettings:
    def __init__(self, uow: UnitOfWorkFactory, backups: BackupService) -> None:
        self._uow = uow
        self._backups = backups

    def execute(self, actor: Actor, changes: Mapping[str, object]) -> BusinessSettings:
        actor.require(Permission.MANAGE_SETTINGS)
        folder = changes.get("backup_folder")
        if isinstance(folder, str) and folder.strip():
            changes = {**changes, "backup_folder": folder.strip()}
            self._backups.check_folder(folder.strip())  # mejor avisar hoy que descubrirlo el día del daño
        with self._uow() as uow:
            settings = require_settings(uow).updated(**changes)
            uow.settings.save(settings)
            uow.commit()
        return settings
