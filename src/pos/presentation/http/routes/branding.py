"""Nombre y logo del negocio. Leerlos es público: la pantalla de inicio los muestra antes de entrar."""

from __future__ import annotations

from flask import Blueprint, Response, request

from ..context import authenticated, container, current_actor
from ..request import InvalidPayload

bp = Blueprint("branding", __name__)


@bp.get("/branding")
def branding():
    value = container().get_branding.execute()
    return {"business_name": value.business_name, "logo_version": value.logo_version}


@bp.get("/branding/logo")
def logo():
    value = container().get_logo.execute()
    response = Response(value.data, mimetype=value.content_type)
    # La interfaz pide /branding/logo?v=<versión>: si el logo cambia, cambia la dirección.
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@bp.put("/branding/logo")
@authenticated
def update_logo():
    """Imagen en el campo `file` (multipart): PNG, JPG o WebP de hasta 1 MB."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise InvalidPayload("Adjunte la imagen del logo en el campo 'file'", "file")
    value = container().update_logo.execute(current_actor(), upload.read())
    return {"logo_version": value.version}


@bp.delete("/branding/logo")
@authenticated
def remove_logo():
    container().remove_logo.execute(current_actor())
    return "", 204
