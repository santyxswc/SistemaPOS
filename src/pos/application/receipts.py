"""Tiquete como documento: qué se imprime y en qué orden, sin saber de impresoras.

El constructor arma el tiquete con objetos simples (texto, dos columnas, separador,
código QR). Cada impresora lo traduce a su idioma: hoy ESC/POS para las térmicas;
mañana podría ser un PDF o un tiquete por WhatsApp, sin tocar estas reglas.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ..domain.invoicing import DocumentStatus, ElectronicDocument
from ..domain.sales import Sale
from ..domain.settings import BusinessSettings
from ..domain.shared.values import Money, TaxRate, format_quantity


class Align(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass(frozen=True)
class Text:
    text: str
    align: Align = Align.LEFT
    bold: bool = False
    large: bool = False  # doble alto y ancho (nombre del negocio, total)


@dataclass(frozen=True)
class Columns:
    """Texto a la izquierda y valor a la derecha en la misma línea."""

    left: str
    right: str
    bold: bool = False
    large: bool = False


@dataclass(frozen=True)
class Separator:
    pass


@dataclass(frozen=True)
class QrCode:
    data: str


ReceiptItem = Text | Columns | Separator | QrCode


@dataclass(frozen=True)
class ReceiptDocument:
    items: tuple[ReceiptItem, ...]

    def plain_text(self, width: int = 48) -> str:
        """Vista en texto (registro y pruebas): cada elemento en su línea."""
        lines: list[str] = []
        for item in self.items:
            if isinstance(item, Separator):
                lines.append("-" * width)
            elif isinstance(item, Columns):
                lines.append(f"{item.left} {item.right}")
            elif isinstance(item, QrCode):
                lines.append("[QR]")
            else:
                lines.append(item.text)
        return "\n".join(lines)


class ReceiptBuilder:
    """Constructor paso a paso (patrón Builder) para que cada tiquete se arme igual."""

    def __init__(self) -> None:
        self._items: list[ReceiptItem] = []

    def text(self, text: str, *, align: Align = Align.LEFT, bold: bool = False, large: bool = False) -> ReceiptBuilder:
        if text:
            self._items.append(Text(text, align, bold, large))
        return self

    def columns(self, left: str, right: str, *, bold: bool = False, large: bool = False) -> ReceiptBuilder:
        self._items.append(Columns(left, right, bold, large))
        return self

    def separator(self) -> ReceiptBuilder:
        self._items.append(Separator())
        return self

    def qr(self, data: str) -> ReceiptBuilder:
        if data:
            self._items.append(QrCode(data))
        return self

    def build(self) -> ReceiptDocument:
        return ReceiptDocument(tuple(self._items))


def _local(moment: datetime, settings: BusinessSettings) -> str:
    return moment.astimezone(settings.tzinfo).strftime("%d/%m/%Y %I:%M %p").lower().replace("am", "a. m.").replace(
        "pm", "p. m."
    )


def _header(builder: ReceiptBuilder, settings: BusinessSettings) -> None:
    builder.text(settings.business_name, align=Align.CENTER, bold=True, large=True)
    builder.text(f"NIT {settings.tax_id}" if settings.tax_id else "", align=Align.CENTER)
    builder.text(settings.address, align=Align.CENTER)
    builder.text(f"Tel. {settings.phone}" if settings.phone else "", align=Align.CENTER)


def sale_receipt(
    sale: Sale,
    settings: BusinessSettings,
    *,
    cashier_name: str,
    customer_name: str | None = None,
    document: ElectronicDocument | None = None,
    copy: bool = False,
) -> ReceiptDocument:
    builder = ReceiptBuilder()
    _header(builder, settings)
    builder.separator()
    builder.columns(f"Venta #{sale.number}", _local(sale.created_at, settings), bold=True)
    builder.text(f"Atendió: {cashier_name}")
    if customer_name:
        builder.text(f"Cliente: {customer_name}")
    if copy:
        builder.text("*** COPIA ***", align=Align.CENTER, bold=True)
    if sale.is_voided:
        builder.text("*** VENTA ANULADA ***", align=Align.CENTER, bold=True, large=True)
    builder.separator()

    for line in sale.lines:
        builder.text(line.description)
        amount = line.total + line.discount if line.discount.is_positive else line.total  # antes del descuento
        builder.columns(f"  {format_quantity(line.quantity)} x {line.unit_price.display()}", amount.display())
        if line.discount.is_positive:
            builder.columns("  Descuento", f"-{line.discount.display()}")
    builder.separator()

    builder.columns("Subtotal", sale.subtotal.display())
    taxes: dict[TaxRate, Money] = defaultdict(Money.zero)
    for line in sale.lines:
        taxes[line.tax_rate] += line.tax
    for rate, amount in sorted(taxes.items(), key=lambda item: item[0].percent):
        if rate.percent > Decimal(0):
            builder.columns(f"Impuesto {rate} %", amount.display())
    if sale.discount_total.is_positive:
        builder.columns("Descuentos", f"-{sale.discount_total.display()}")
    builder.columns("TOTAL", sale.total.display(), bold=True, large=True)
    for payment in sale.payments:
        builder.columns(payment.method_name, payment.amount.display())
    if sale.change.is_positive:
        builder.columns("Vueltas", sale.change.display(), bold=True)

    if document is not None and document.status is DocumentStatus.ACCEPTED and document.cufe:
        builder.separator()
        builder.text("Documento equivalente electrónico", align=Align.CENTER)
        builder.text(f"CUFE: {document.cufe}")
        builder.qr(document.qr_data)
    builder.separator()
    builder.text(settings.receipt_footer, align=Align.CENTER)
    return builder.build()


def printer_test_receipt(settings: BusinessSettings, *, at: datetime, width: int) -> ReceiptDocument:
    """Página de prueba: confirma ancho del papel, tildes, negrilla y corte."""
    builder = ReceiptBuilder()
    _header(builder, settings)
    builder.separator()
    builder.text("Prueba de impresión", align=Align.CENTER, bold=True)
    builder.text(_local(at, settings), align=Align.CENTER)
    builder.text("Tildes: áéíóú ñ Ñ ¿? ¡!")
    builder.columns("Izquierda", "Derecha")
    builder.text(("1234567890" * 5)[:width])
    builder.text(f"La línea de arriba debe llegar justo al borde ({width} caracteres).")
    builder.separator()
    return builder.build()
