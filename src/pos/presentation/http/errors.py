"""Traducción de errores de dominio a respuestas HTTP con un formato único."""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask
from werkzeug.exceptions import HTTPException

from ...domain.shared.errors import (
    AuthenticationError,
    BusinessRuleViolation,
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDenied,
    ValidationError,
)
from .request import InvalidPayload

logger = logging.getLogger("pos.http")

_STATUS: tuple[tuple[type[DomainError], int], ...] = (
    (AuthenticationError, 401),
    (PermissionDenied, 403),
    (NotFoundError, 404),
    (ConflictError, 409),
    (BusinessRuleViolation, 422),
    (ValidationError, 400),
)

_HTTP_MESSAGES = {404: "Ruta no encontrada", 405: "Método no permitido en esta ruta"}


def status_for(error: DomainError) -> int:
    for error_type, status in _STATUS:
        if isinstance(error, error_type):
            return status
    return 400


def error_body(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if field:
        body["field"] = field
    return {"error": body}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(DomainError)
    def handle_domain_error(error: DomainError) -> tuple[dict[str, Any], int]:
        return error_body(error.code, error.message), status_for(error)

    @app.errorhandler(InvalidPayload)
    def handle_invalid_payload(error: InvalidPayload) -> tuple[dict[str, Any], int]:
        return error_body("invalid_payload", error.message, error.field), 400

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[dict[str, Any], int]:
        status = error.code or 500
        message = _HTTP_MESSAGES.get(status, error.description or error.name)
        return error_body(error.name.lower().replace(" ", "_"), message), status

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception) -> tuple[dict[str, Any], int]:
        logger.exception("Error no controlado", exc_info=error)
        return error_body("internal_error", "Ocurrió un error inesperado; intente de nuevo"), 500
