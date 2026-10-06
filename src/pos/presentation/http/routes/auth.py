from __future__ import annotations

from flask import Blueprint

from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import Body

bp = Blueprint("auth", __name__)


@bp.post("/auth/login")
def login():
    body = Body.from_request()
    result = container().login.execute(body.text("username"), body.text("password"))
    return {
        "access_token": result.token,
        "token_type": "Bearer",
        "expires_in": result.expires_in,
        "user": presenters.user(result.user),
    }


@bp.get("/auth/me")
@authenticated
def me():
    return presenters.actor(current_actor())


@bp.post("/auth/change-password")
@authenticated
def change_password():
    body = Body.from_request()
    container().change_own_password.execute(
        current_actor(), body.text("current_password"), body.text("new_password")
    )
    return "", 204
