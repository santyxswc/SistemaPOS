"""Aviso de versión nueva: el administrador se entera sin que nadie tenga que llamarlo."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from ...domain.users import Permission
from ..actor import Actor
from ..ports import Clock, ReleaseInfo, ReleaseSource

CHECK_EVERY = timedelta(hours=6)
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(text: str) -> tuple[int, int, int] | None:
    """'v0.3.0' → (0, 3, 0). Las versiones de prueba ('0.4.0-beta') no cuentan."""
    match = _VERSION.match((text or "").strip())
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


@dataclass(frozen=True)
class UpdateStatus:
    current: str
    latest: ReleaseInfo | None
    checked_at: datetime | None

    @property
    def available(self) -> bool:
        if self.latest is None:
            return False
        latest, current = parse_version(self.latest.version), parse_version(self.current)
        return latest is not None and current is not None and latest > current


class CheckForUpdates:
    """Pregunta por la última versión publicada como mucho cada 6 horas (la respuesta se recuerda)."""

    def __init__(self, source: ReleaseSource, current_version: str, clock: Clock) -> None:
        self._source = source
        self._current = current_version
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: UpdateStatus | None = None

    def execute(self, actor: Actor, *, force: bool = False) -> UpdateStatus:
        actor.require(Permission.MANAGE_SETTINGS)
        return self.status(force=force)

    def status(self, *, force: bool = False) -> UpdateStatus:
        """Sin permisos: lo usa también el ícono junto al reloj, que corre en el equipo del negocio."""
        now = self._clock.now()
        with self._lock:
            cached = self._cached
            if not force and cached is not None and cached.checked_at and now - cached.checked_at < CHECK_EVERY:
                return cached
            latest = self._source.latest()
            if latest is None and cached is not None:
                latest = cached.latest  # sin internet: se conserva lo último que se supo
            self._cached = UpdateStatus(current=self._current, latest=latest, checked_at=now)
            return self._cached
