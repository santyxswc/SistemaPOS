"""Reacciones a eventos de dominio. Se registran en el contenedor (bootstrap)."""

from __future__ import annotations

import logging

from ..domain.catalog import StockLow
from ..domain.sales import SaleCompleted
from ..domain.shared.values import format_quantity
from .ports import InvoiceProvider

logger = logging.getLogger("pos.events")


def log_low_stock(event: StockLow) -> None:
    """Hoy deja registro; mañana puede enviar un WhatsApp o un correo al dueño."""
    logger.warning(
        "Stock bajo: %s (quedan %s, mínimo %s)",
        event.product_name,
        format_quantity(event.stock),
        format_quantity(event.min_stock),
    )


class ElectronicInvoicingHandler:
    """Envía cada venta al proveedor de facturación electrónica configurado."""

    def __init__(self, provider: InvoiceProvider) -> None:
        self._provider = provider

    def __call__(self, event: SaleCompleted) -> None:
        self._provider.issue_for_sale(event.sale_id)
