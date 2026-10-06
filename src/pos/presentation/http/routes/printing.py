from __future__ import annotations

from flask import Blueprint

from ..context import authenticated, container, current_actor
from ..request import Body
from .settings import read_printer_config

bp = Blueprint("printing", __name__)


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
