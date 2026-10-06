"""Eventos de dominio: hechos importantes que ya ocurrieron (venta hecha, stock bajo...).

Permiten reaccionar (notificar, facturar a la DIAN, sincronizar) sin acoplar esas
reacciones a la lógica que produjo el hecho.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    occurred_at: datetime
