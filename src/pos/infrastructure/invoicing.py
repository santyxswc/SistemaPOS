"""Facturación electrónica.

Por defecto no se emite nada. Para la DIAN se crea una clase con el mismo método
`issue_for_sale` que llame al API de un proveedor autorizado y se registra en
`bootstrap.py`. Ninguna otra parte del sistema cambia.
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger("pos.invoicing")


class NoInvoiceProvider:
    def issue_for_sale(self, sale_id: UUID) -> None:
        logger.debug("Facturación electrónica desactivada; venta %s sin documento electrónico", sale_id)
