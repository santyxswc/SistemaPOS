"""Acceso al contenedor y autenticación por token Bearer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar, cast

from flask import current_app, g, request

from ...application.actor import Actor
from ...domain.shared.errors import AuthenticationError

if TYPE_CHECKING:
    from ...bootstrap import Container

CONTAINER_KEY = "pos.container"
F = TypeVar("F", bound=Callable[..., Any])


def container() -> Container:
    return current_app.extensions[CONTAINER_KEY]


def authenticated(view: F) -> F:
    """Exige un token válido. Los permisos los revisa cada caso de uso, no la API."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthenticationError("Inicie sesión para continuar")
        g.actor = container().resolve_actor.execute(token.strip())
        return view(*args, **kwargs)

    return cast(F, wrapper)


def current_actor() -> Actor:
    return g.actor


def business_today() -> date:
    return datetime.now(container().get_settings.execute().tzinfo).date()
