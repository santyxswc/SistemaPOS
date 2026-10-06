"""Licencia de uso: estado actual y activación de un código enviado por el proveedor."""

from __future__ import annotations

from flask import Blueprint

from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import Body

bp = Blueprint("licensing", __name__)


@bp.get("/license")
@authenticated
def license_status():
    return presenters.license_status(container().get_license_status.execute())


@bp.post("/license")
@authenticated
def install_license():
    body = Body.from_request()
    return presenters.license_status(container().install_license.execute(current_actor(), body.text("code")))
