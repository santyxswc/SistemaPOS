"""Copias de seguridad desde Ajustes: ver las últimas y respaldar ahora."""

from __future__ import annotations

from flask import Blueprint

from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import query_int

bp = Blueprint("backups", __name__)


@bp.get("/backups")
@authenticated
def list_backups():
    items = container().list_backups.execute(current_actor(), limit=query_int("limit", 10))
    return {"items": [presenters.backup_file(item) for item in items]}


@bp.post("/backups")
@authenticated
def run_backup():
    return presenters.backup_result(container().run_backup.execute(current_actor())), 201
