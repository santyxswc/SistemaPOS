from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Hora real en UTC. Las fechas se guardan en UTC y se muestran en la zona del negocio."""

    def now(self) -> datetime:
        return datetime.now(UTC)
