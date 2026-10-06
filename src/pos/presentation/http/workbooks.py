"""Traducción entre hojas de cálculo y los casos de uso: columnas, encabezados y libros de Excel."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from flask import Response

from ...application.use_cases.catalog import CatalogExport
from ...application.use_cases.catalog_import import ProductImportRow
from ...application.use_cases.reports import SalesReportExport
from ...domain.catalog import Unit
from ...domain.shared.values import Money
from ..spreadsheets import XLSX_MIMETYPE, Row, Sheet, write_xlsx
from .request import InvalidPayload

UNIT_LABELS = {Unit.UNIT: "unidad", Unit.KILOGRAM: "kg", Unit.POUND: "lb", Unit.LITER: "litro"}


@dataclass(frozen=True)
class Column:
    field: str
    header: str  # como se exporta (y como se recomienda en la plantilla)
    synonyms: tuple[str, ...]  # otros encabezados que la gente usa en sus archivos


PRODUCT_COLUMNS: tuple[Column, ...] = (
    Column("sku", "Código", ("codigo", "cod", "sku", "referencia", "ref", "codigointerno", "item")),
    Column("name", "Nombre", ("nombre", "producto", "descripcion", "articulo", "nombredelproducto")),
    Column("price", "Precio", ("precio", "precioventa", "preciodeventa", "pventa", "valor", "preciounitario", "pvp")),
    Column("cost", "Costo", ("costo", "preciocosto", "preciodecosto", "pcosto", "costounitario", "preciocompra")),
    Column("tax_rate", "IVA %", ("iva", "impuesto", "tarifaiva", "porcentajeiva", "ivaporcentaje")),
    Column("barcode", "Código de barras", ("codigodebarras", "codigobarras", "barras", "ean", "barcode", "upc")),
    Column("category", "Categoría", ("categoria", "grupo", "linea", "familia", "seccion")),
    Column("unit", "Unidad", ("unidad", "unidaddemedida", "medida", "um", "presentacion")),
    Column("stock", "Existencias", ("existencias", "stock", "cantidad", "inventario", "saldo", "existencia")),
    Column("min_stock", "Stock mínimo", ("stockminimo", "minimo", "existenciaminima", "cantidadminima")),
)


def _header_key(text: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]", "", plain)


_BY_HEADER = {
    key: column.field
    for column in PRODUCT_COLUMNS
    for key in (*column.synonyms, _header_key(column.header), column.field.replace("_", ""))
}


def _find_header(rows: Sequence[Row]) -> tuple[int, dict[int, str]]:
    """Posición de la fila de encabezados y qué campo hay en cada columna."""
    for position, (_, cells) in enumerate(rows[:10]):
        mapping = {}
        for index, cell in enumerate(cells):
            field = _BY_HEADER.get(_header_key(cell))
            if field is not None and field not in mapping.values():
                mapping[index] = field
        if len(mapping) >= 2 and {"name", "sku", "barcode"} & set(mapping.values()):
            return position, mapping
    expected = ", ".join(column.header for column in PRODUCT_COLUMNS[:5])
    raise InvalidPayload(
        f"No se encontraron los encabezados. La primera fila debe tener columnas como: {expected}. "
        "Descargue la plantilla para ver un ejemplo."
    )


def import_rows(rows: Sequence[Row]) -> list[ProductImportRow]:
    """Arma las filas de productos debajo de los encabezados (puede haber un título encima)."""
    position, mapping = _find_header(rows)
    return [
        ProductImportRow(
            line=line,
            values={field: cells[index] for index, field in mapping.items() if index < len(cells)},
        )
        for line, cells in rows[position + 1 :]
    ]


def _amount(value: Money) -> Decimal:
    return value.amount


def catalog_sheet(export: CatalogExport) -> Sheet:
    return Sheet(
        name="Productos",
        header=[column.header for column in PRODUCT_COLUMNS] + ["Activo"],
        rows=[
            [
                product.sku,
                product.name,
                _amount(product.price),
                _amount(product.cost),
                product.tax_rate.percent.normalize(),
                product.barcode or "",
                export.category_names.get(product.category_id, "") if product.category_id else "",
                UNIT_LABELS[product.unit],
                product.stock.normalize() if product.track_stock else "",
                product.min_stock.normalize() if product.track_stock else "",
                "sí" if product.active else "no",
            ]
            for product in export.products
        ],
        money_columns=frozenset({2, 3}),
    )


def template_sheet() -> Sheet:
    return Sheet(
        name="Productos",
        header=[column.header for column in PRODUCT_COLUMNS],
        rows=[
            ["ARROZ-500", "Arroz Diana 500 g", Decimal(2500), Decimal(1900), Decimal(0), "7702511000014", "Granos",
             "unidad", Decimal(40), Decimal(10)],
            ["QUESO-CAMPESINO", "Queso campesino", Decimal(18000), Decimal(13000), Decimal(0), "", "Lácteos", "kg",
             Decimal("5.5"), Decimal(1)],
            ["GASEOSA-400", "Gaseosa 400 ml", Decimal(2800), Decimal(2000), Decimal(19), "7702004001234", "Bebidas",
             "unidad", Decimal(24), Decimal(6)],
        ],
        money_columns=frozenset({2, 3}),
    )


def sales_report_sheets(export: SalesReportExport) -> list[Sheet]:
    summary = export.summary
    overview = Sheet(
        name="Resumen",
        header=["Concepto", "Valor"],
        rows=[
            ["Desde", summary.date_from],
            ["Hasta", summary.date_to],
            ["Ventas (sin anuladas)", Decimal(summary.sales_count)],
            ["Anuladas", Decimal(summary.voided_count)],
            ["Base gravable", _amount(summary.subtotal)],
            ["Impuestos", _amount(summary.tax_total)],
            ["Descuentos", _amount(summary.discount_total)],
            ["Total vendido", _amount(summary.total)],
            ["Ticket promedio", _amount(summary.average_ticket)],
            *[[f"Recibido en {p.name}", _amount(p.amount)] for p in summary.by_payment_method],
        ],
        money_columns=frozenset({1}),
    )
    by_day = Sheet(
        name="Por día",
        header=["Día", "Ventas", "Total"],
        rows=[[p.period, Decimal(p.sales_count), _amount(p.total)] for p in summary.by_period],
        money_columns=frozenset({2}),
    )
    sales = Sheet(
        name="Ventas",
        header=["Número", "Fecha", "Estado", "Cajero", "Cliente", "Base", "Impuestos", "Descuentos", "Total", "Pagos"],
        rows=[
            [
                Decimal(row.number),
                row.created_at.astimezone(export.timezone),
                "Anulada" if row.status == "voided" else "Completada",
                row.cashier,
                row.customer or "",
                _amount(row.subtotal),
                _amount(row.tax_total),
                _amount(row.discount_total),
                _amount(row.total),
                ", ".join(f"{name} {amount.display()}" for name, amount in row.payments),
            ]
            for row in export.sales
        ],
        money_columns=frozenset({5, 6, 7, 8}),
    )
    products = Sheet(
        name="Productos vendidos",
        header=["Código", "Producto", "Cantidad", "Total vendido"],
        rows=[[p.sku, p.description, p.quantity.normalize(), _amount(p.total)] for p in export.products],
        money_columns=frozenset({3}),
    )
    return [overview, by_day, sales, products]


def xlsx_download(sheets: Sequence[Sheet], filename: str) -> Response:
    response = Response(write_xlsx(sheets), mimetype=XLSX_MIMETYPE)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.cache_control.no_store = True
    return response
