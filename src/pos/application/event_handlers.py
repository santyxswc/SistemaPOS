"""Reacciones a eventos de dominio. Se registran en el contenedor (bootstrap)."""

from __future__ import annotations

import logging

from ..domain.catalog import StockLow
from ..domain.shared.values import format_quantity

logger = logging.getLogger("pos.events")


def log_low_stock(event: StockLow) -> None:
    """Hoy deja registro; mañana puede enviar un WhatsApp o un correo al dueño."""
    logger.warning(
        "Stock bajo: %s (quedan %s, mínimo %s)",
        event.product_name,
        format_quantity(event.stock),
        format_quantity(event.min_stock),
    )

