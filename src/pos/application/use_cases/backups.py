"""Copias de seguridad: a pedido, al cerrar la caja y desde la tarea programada."""

from __future__ import annotations

import logging

from ...domain.cash import CashSessionClosed
from ...domain.users import Permission
from ..actor import Actor
from ..common import require_settings
from ..ports import BackupFile, BackupResult, BackupService, Clock, UnitOfWorkFactory

logger = logging.getLogger("pos.backup")


class RunBackup:
    """Respalda la base de datos y la copia a la carpeta adicional configurada en Ajustes."""

    def __init__(self, uow: UnitOfWorkFactory, backups: BackupService, clock: Clock) -> None:
        self._uow = uow
        self._backups = backups
        self._clock = clock

    def execute(self, actor: Actor) -> BackupResult:
        actor.require(Permission.MANAGE_SETTINGS)
        return self.execute_unattended()

    def execute_unattended(self) -> BackupResult:
        """Para la tarea programada y las reacciones automáticas (no hay un usuario detrás)."""
        with self._uow(read_only=True) as uow:
            settings = require_settings(uow)
        # Nombre del archivo con la hora del negocio: es la que el dueño reconoce al restaurar.
        at = self._clock.now().astimezone(settings.tzinfo)
        result = self._backups.create(at=at, extra_folder=settings.backup_folder or None)
        logger.info("Respaldo creado: %s (copia adicional: %s)", result.file.name, result.extra_copy or "no")
        return result


class ListBackups:
    def __init__(self, backups: BackupService) -> None:
        self._backups = backups

    def execute(self, actor: Actor, limit: int = 10) -> list[BackupFile]:
        actor.require(Permission.MANAGE_SETTINGS)
        return self._backups.list_recent(limit=max(1, min(limit, 50)))


class BackupOnCashClose:
    """Al cerrar la caja se respalda: es un momento natural y la tarea de la noche puede no correr
    (el computador se apaga antes de las 10 p. m.)."""

    def __init__(self, run_backup: RunBackup) -> None:
        self._run_backup = run_backup

    def __call__(self, event: CashSessionClosed) -> None:
        self._run_backup.execute_unattended()
