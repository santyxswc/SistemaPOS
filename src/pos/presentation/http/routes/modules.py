"""Qué módulos tiene esta instalación, para que la interfaz arme el menú y los ajustes."""

from __future__ import annotations

from flask import Blueprint

from ....application.modules import CATALOG
from ..context import authenticated, container

bp = Blueprint("modules", __name__)


@bp.get("/modules")
@authenticated
def list_modules():
    enabled = container().modules
    return {
        "items": [
            {
                "id": info.module.value,
                "name": info.name,
                "description": info.description,
                "enabled": enabled.is_enabled(info.module),
            }
            for info in CATALOG
        ]
    }
