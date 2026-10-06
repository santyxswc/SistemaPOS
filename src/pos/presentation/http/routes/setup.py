"""Configuración inicial desde el navegador: la primera vez no hay que usar la consola."""

from __future__ import annotations

from flask import Blueprint

from ....application.use_cases.users import InitialSetupCommand
from .. import presenters
from ..context import container
from ..request import Body

bp = Blueprint("setup", __name__)


@bp.get("/setup")
def setup_status():
    return {"needs_setup": container().get_setup_status.execute()}


@bp.post("/setup")
def complete_setup():
    body = Body.from_request()
    command = InitialSetupCommand(
        business_name=body.text("business_name"),
        username=body.text("username"),
        full_name=body.text("full_name"),
        password=body.text("password"),
    )
    container().complete_initial_setup.execute(command)
    # Entra de una vez: quien acaba de crear la cuenta no tiene que volver a escribir la contraseña.
    result = container().login.execute(command.username, command.password)
    return {
        "access_token": result.token,
        "token_type": "Bearer",
        "expires_in": result.expires_in,
        "user": presenters.user(result.user),
    }, 201
