"""Fábrica de la aplicación Flask."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask, Response, request

from ... import __version__
from ...application.modules import Module
from ..web import register_web
from .context import CONTAINER_KEY
from .errors import register_error_handlers
from .routes import (
    auth,
    backups,
    branding,
    cash,
    catalog,
    catalog_files,
    customers,
    inventory,
    invoicing,
    licensing,
    modules,
    printing,
    reports,
    sales,
    settings,
    setup,
    suppliers,
    users,
)

if TYPE_CHECKING:
    from ...bootstrap import Container

API_PREFIX = "/api/v1"

# El núcleo: lo que tiene cualquier negocio.
CORE_ROUTES = (setup, auth, modules, branding, users, settings, backups, catalog, inventory, cash, sales)

# Las rutas de cada módulo opcional solo existen si el módulo está encendido para este cliente.
# Los módulos que no aparecen aquí (fiado, descuentos, permisos...) se apagan por permisos.
OPTIONAL_ROUTES = {
    Module.CUSTOMERS: (customers,),
    Module.SUPPLIERS: (suppliers,),
    Module.REPORTS: (reports,),
    Module.SPREADSHEETS: (catalog_files,),
    Module.DIRECT_PRINTING: (printing,),
    Module.INVOICING: (invoicing,),
    Module.LICENSING: (licensing,),
}


def create_app(container: Container) -> Flask:
    app = Flask("pos", static_folder=None)
    app.json.sort_keys = False  # type: ignore[attr-defined]
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # archivos de Excel; nada legítimo pesa más
    app.extensions[CONTAINER_KEY] = container

    register_error_handlers(app)
    _register_cors(app, container.config.cors_origins)
    route_modules = [*CORE_ROUTES]
    for module, routes in OPTIONAL_ROUTES.items():
        if container.modules.is_enabled(module):
            route_modules.extend(routes)
    for routes in route_modules:
        app.register_blueprint(routes.bp, url_prefix=API_PREFIX)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    _register_security_headers(app)
    register_web(app)
    return app


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'",
        )
        return response


def _register_cors(app: Flask, origins: tuple[str, ...]) -> None:
    """Permite que el frontend (React en otro puerto u origen) consuma la API."""
    if not origins:
        return

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        origin = request.headers.get("Origin")
        if origin and (origin in origins or "*" in origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Idempotency-Key"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "600"
            response.vary.add("Origin")
        return response
