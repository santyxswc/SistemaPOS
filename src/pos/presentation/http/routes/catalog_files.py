"""Productos en Excel o CSV: plantilla, importación y exportación del catálogo (módulo «excel»)."""

from __future__ import annotations

from flask import Blueprint, request

from ...spreadsheets import SpreadsheetError, read_rows
from .. import presenters
from ..context import authenticated, business_today, container, current_actor
from ..request import InvalidPayload, query_bool
from ..workbooks import catalog_sheet, import_rows, template_sheet, xlsx_download

bp = Blueprint("catalog_files", __name__)


@bp.get("/products/export")
@authenticated
def export_products():
    export = container().export_catalog.execute(current_actor(), include_inactive=query_bool("include_inactive"))
    return xlsx_download([catalog_sheet(export)], f"productos-{business_today():%Y-%m-%d}.xlsx")


@bp.get("/products/import-template")
@authenticated
def import_template():
    return xlsx_download([template_sheet()], "plantilla-productos.xlsx")


@bp.post("/products/import")
@authenticated
def import_products():
    """Archivo en el campo `file` (multipart). Por defecto solo es una vista previa (`dry_run=true`)."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise InvalidPayload("Adjunte el archivo de Excel o CSV en el campo 'file'", "file")
    try:
        rows = read_rows(upload.read(), upload.filename)
    except SpreadsheetError as error:
        raise InvalidPayload(str(error), "file") from None
    report = container().import_products.execute(
        current_actor(),
        import_rows(rows),
        update_existing=query_bool("update_existing"),
        dry_run=query_bool("dry_run", default=True),
    )
    return presenters.import_report(report)
