"""Proveedores de facturación electrónica.

Por defecto no se emite nada. Para la DIAN se escribe una clase con el método
`issue(document, sale, settings)` que llame al API del proveedor tecnológico elegido,
y se registra en `PROVIDERS`. Se activa con POS_INVOICE_PROVIDER en el .env.

`simulado` no le habla a nadie: genera un CUFE de prueba para recorrer todo el
flujo (bandeja, reintentos, pantalla de revisión) antes de contratar un proveedor.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from ..application.ports import InvoiceProvider
from ..domain.invoicing import DocumentKind, ElectronicDocument, IssuedDocument
from ..domain.sales import Sale
from ..domain.settings import BusinessSettings

# Consulta pública de documentos en el ambiente de habilitación (pruebas) de la DIAN.
DIAN_TEST_QR_URL = "https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey="


class SimulatedInvoiceProvider:
    """Acepta todo al instante. Solo para pruebas y demostraciones: el CUFE no es válido ante la DIAN."""

    name = "Simulado (pruebas, sin validez ante la DIAN)"

    def issue(self, document: ElectronicDocument, sale: Sale, settings: BusinessSettings) -> IssuedDocument:
        prefix = "NC" if document.kind is DocumentKind.CREDIT_NOTE else "POS"
        number = f"{prefix}{sale.number}"
        when = sale.created_at.astimezone(settings.tzinfo)
        fields = [number, when.strftime("%Y-%m-%d"), when.strftime("%H:%M:%S%z"), str(sale.subtotal),
                  str(sale.tax_total), str(sale.total), settings.tax_id or "222222222222", "simulado"]
        cufe = hashlib.sha384("".join(fields).encode()).hexdigest()
        qr = (
            f"NumFac: {number}\nFecFac: {when:%Y-%m-%d}\nNitFac: {settings.tax_id}\nValFac: {sale.subtotal}\n"
            f"ValIva: {sale.tax_total}\nValTolFac: {sale.total}\nCUFE: {cufe}\nQRCode: {DIAN_TEST_QR_URL}{cufe}"
        )
        return IssuedDocument(cufe=cufe, qr_data=qr, reference=number)


PROVIDERS: dict[str, Callable[[], InvoiceProvider]] = {
    "simulado": SimulatedInvoiceProvider,
}


def create_invoice_provider(name: str) -> InvoiceProvider | None:
    """Fábrica: el nombre viene de POS_INVOICE_PROVIDER. Vacío desactiva la facturación electrónica."""
    key = (name or "").strip().lower()
    if not key:
        return None
    try:
        return PROVIDERS[key]()
    except KeyError:
        options = ", ".join(sorted(PROVIDERS))
        raise RuntimeError(f"POS_INVOICE_PROVIDER={name!r} no existe (opciones: {options}, o vacío)") from None
