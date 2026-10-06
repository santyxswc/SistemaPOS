"""Respaldo en caliente de la base de datos SQLite.

Usa la API de respaldo de SQLite: la copia es consistente aunque haya cajas
vendiendo en ese momento (copiar el archivo a mano no lo garantiza en modo WAL).
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from ....application.ports import BackupFile, BackupResult
from ....domain.shared.errors import ValidationError

logger = logging.getLogger("pos.backup")

PREFIX = "pos-"
SUFFIX = ".sqlite3"


def backup_database(database: str, target_dir: str | Path, *, now: datetime, keep: int = 30) -> Path:
    """Crea `pos-AAAAMMDD-HHMMSS.sqlite3` en `target_dir` y deja solo los `keep` más recientes."""
    if keep < 1:
        raise ValueError("keep debe ser al menos 1")
    folder = Path(target_dir)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{PREFIX}{now:%Y%m%d-%H%M%S}{SUFFIX}"

    source = sqlite3.connect(database)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError(f"El respaldo {target} quedó dañado")
    finally:
        destination.close()
        source.close()

    _prune(folder, keep)
    return target


EXTRA_SUBFOLDER = "Respaldos Punto de Venta"


def _describe(path: Path, at: datetime | None = None) -> BackupFile:
    stat = path.stat()
    created = at or datetime.fromtimestamp(stat.st_mtime).astimezone()
    return BackupFile(name=path.name, created_at=created, size_bytes=stat.st_size)


class SqliteBackupService:
    """Respaldos en `data/backups` y, opcionalmente, una copia en otra carpeta (USB, OneDrive...)."""

    def __init__(self, database: str, folder: str | Path, *, keep: int = 30) -> None:
        self._database = database
        self._folder = Path(folder)
        self._keep = keep

    def create(self, *, at: datetime, extra_folder: str | None = None) -> BackupResult:
        target = backup_database(self._database, self._folder, now=at, keep=self._keep)
        file = _describe(target, at)
        if not extra_folder:
            return BackupResult(file=file)
        destination = Path(extra_folder) / EXTRA_SUBFOLDER
        try:
            if not Path(extra_folder).is_dir():  # USB desconectada: no crear la carpeta en el disco local
                raise FileNotFoundError(2, "la carpeta no está disponible")
            destination.mkdir(exist_ok=True)
            shutil.copy2(target, destination / target.name)
            _prune(destination, self._keep)
        except OSError as error:
            logger.warning("No se pudo copiar el respaldo a %s: %s", destination, error)
            return BackupResult(file=file, extra_error=f"No se pudo copiar a {extra_folder}: {error.strerror or error}")
        return BackupResult(file=file, extra_copy=str(destination / target.name))

    def list_recent(self, limit: int = 10) -> list[BackupFile]:
        if not self._folder.is_dir():
            return []
        files = sorted(self._folder.glob(f"{PREFIX}*{SUFFIX}"), reverse=True)[:limit]
        return [_describe(path) for path in files]

    def check_folder(self, folder: str) -> None:
        path = Path(folder)
        if not path.is_absolute():
            raise ValidationError("Escriba la ruta completa de la carpeta, por ejemplo E:\\ o C:\\Users\\...\\OneDrive")
        if not path.is_dir():
            raise ValidationError(f"La carpeta {folder} no existe o no está conectada")
        probe = path / ".prueba-punto-de-venta"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
        except OSError:
            message = f"No se puede guardar en {folder}: revise que no esté protegida contra escritura"
            raise ValidationError(message) from None


def _prune(folder: Path, keep: int) -> None:
    for old in sorted(folder.glob(f"{PREFIX}*{SUFFIX}"))[:-keep]:
        old.unlink()
