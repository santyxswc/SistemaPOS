from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from flask import Blueprint, request

from ....application.use_cases.catalog import CreateProductCommand
from ....domain.catalog import Unit
from ....domain.shared.values import parse_enum
from ...spreadsheets import SpreadsheetError, read_rows
from .. import presenters
from ..context import authenticated, business_today, container, current_actor
from ..request import Body, InvalidPayload, query_bool, query_int, query_text, query_uuid
from ..workbooks import catalog_sheet, import_rows, template_sheet, xlsx_download

bp = Blueprint("catalog", __name__)


@bp.get("/categories")
@authenticated
def list_categories():
    items = container().list_categories.execute(include_inactive=query_bool("include_inactive"))
    return {"items": [presenters.category(c) for c in items]}


@bp.post("/categories")
@authenticated
def create_category():
    body = Body.from_request()
    return presenters.category(container().create_category.execute(current_actor(), body.text("name"))), 201


@bp.get("/products")
@authenticated
def search_products():
    items = container().search_products.execute(
        text=query_text("q"),
        category_id=query_uuid("category_id"),
        include_inactive=query_bool("include_inactive"),
        limit=query_int("limit", 50),
        offset=query_int("offset", 0, maximum=1_000_000),
    )
    return {"items": [presenters.product(p) for p in items]}


@bp.get("/products/lookup")
@authenticated
def lookup_product():
    return presenters.product(container().find_product_by_code.execute(query_text("code") or ""))


@bp.post("/products")
@authenticated
def create_product():
    body = Body.from_request()
    command = CreateProductCommand(
        sku=body.text("sku"),
        name=body.text("name"),
        price=body.money("price"),
        tax_rate=body.tax_rate("tax_rate"),
        cost=body.money("cost", required=False),
        unit=parse_enum(Unit, body.text("unit", required=False, default="unit"), "unidad"),
        barcode=body.text("barcode", required=False),
        category_id=body.uuid("category_id", required=False),
        track_stock=body.boolean("track_stock", default=True),
        initial_stock=body.decimal("initial_stock", required=False) or Decimal(0),
        min_stock=body.decimal("min_stock", required=False) or Decimal(0),
    )
    return presenters.product(container().create_product.execute(current_actor(), command)), 201


@bp.get("/products/<uuid:product_id>")
@authenticated
def get_product(product_id: UUID):
    return presenters.product(container().get_product.execute(product_id))


@bp.patch("/products/<uuid:product_id>")
@authenticated
def update_product(product_id: UUID):
    body = Body.from_request()
    readers: dict[str, Callable[[], object]] = {
        "sku": lambda: body.text("sku"),
        "name": lambda: body.text("name"),
        "price": lambda: body.money("price"),
        "cost": lambda: body.money("cost"),
        "tax_rate": lambda: body.tax_rate("tax_rate", required=True),
        "unit": lambda: parse_enum(Unit, body.text("unit"), "unidad"),
        "barcode": lambda: body.text("barcode", required=False),
        "category_id": lambda: body.uuid("category_id", required=False),
        "track_stock": lambda: body.boolean("track_stock", required=True),
        "min_stock": lambda: body.decimal("min_stock"),
        "active": lambda: body.boolean("active", required=True),
    }
    body.reject_unknown(set(readers))
    changes = {key: read() for key, read in readers.items() if body.has(key)}
    return presenters.product(container().update_product.execute(current_actor(), product_id, changes))


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
