"""Fábrica de la aplicación Flask."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask, Response, request

from ... import __version__
from .context import CONTAINER_KEY
from .errors import register_error_handlers
from .routes import auth, cash, catalog, customers, inventory, reports, sales, settings, users

if TYPE_CHECKING:
    from ...bootstrap import Container

API_PREFIX = "/api/v1"


def create_app(container: Container) -> Flask:
    app = Flask("pos", static_folder=None)
    app.json.sort_keys = False  # type: ignore[attr-defined]
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.extensions[CONTAINER_KEY] = container

    register_error_handlers(app)
    _register_cors(app, container.config.cors_origins)
    for module in (auth, users, settings, catalog, inventory, cash, sales, customers, reports):
        app.register_blueprint(module.bp, url_prefix=API_PREFIX)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


def _register_cors(app: Flask, origins: tuple[str, ...]) -> None:
    """Permite que el frontend (React en otro puerto u origen) consuma la API."""
    if not origins:
        return

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        origin = request.headers.get("Origin")
        if origin and (origin in origins or "*" in origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "600"
            response.vary.add("Origin")
        return response
