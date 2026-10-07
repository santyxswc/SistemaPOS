"""Impresión directa en la impresora térmica y apertura del cajón (módulo «impresion»)."""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint

from ..context import authenticated, container, current_actor
from ..request import Body
from .settings import read_printer_config

bp = Blueprint("printing", __name__)


@bp.post("/sales/<uuid:sale_id>/print")
@authenticated
def print_sale(sale_id: UUID):
    """{"copy": true} para reimprimir."""
    body = Body.from_request()
    container().print_sale_receipt.execute(current_actor(), sale_id, copy=body.boolean("copy", default=False))
    return "", 204


@bp.get("/printing/printers")
@authenticated
def printers():
    return {"items": container().list_printers.execute(current_actor())}


@bp.post("/printing/test")
@authenticated
def test_page():
    """Sin cuerpo prueba la impresora guardada; con {"printer": {...}} prueba una sin guardar."""
    body = Body.from_request()
    config = read_printer_config(body.object("printer")) if body.has("printer") else None
    container().print_test_receipt.execute(current_actor(), config)
    return "", 204


@bp.post("/cash-drawer/open")
@authenticated
def open_drawer():
    container().open_cash_drawer.execute(current_actor())
    return "", 204
