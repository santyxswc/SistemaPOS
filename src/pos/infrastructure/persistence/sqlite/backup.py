"""Respaldo en caliente de la base de datos SQLite.

Usa la API de respaldo de SQLite: la copia es consistente aunque haya cajas
vendiendo en ese momento (copiar el archivo a mano no lo garantiza en modo WAL).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

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

    for old in sorted(folder.glob(f"{PREFIX}*{SUFFIX}"))[:-keep]:
        old.unlink()
    return target
