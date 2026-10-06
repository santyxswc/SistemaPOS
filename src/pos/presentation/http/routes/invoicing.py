from __future__ import annotations

from uuid import UUID

from flask import Blueprint

from ....domain.invoicing import DocumentStatus
from ....domain.shared.values import parse_enum
from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import query_int, query_text

bp = Blueprint("invoicing", __name__)


@bp.get("/invoicing")
@authenticated
def status():
    return presenters.invoicing_status(container().get_invoicing_status.execute(current_actor()))


@bp.get("/invoicing/documents")
@authenticated
def documents():
    """?status=failed,rejected filtra por estado."""
    raw = query_text("status")
    statuses = {parse_enum(DocumentStatus, s.strip(), "estado") for s in raw.split(",") if s.strip()} if raw else None
    items = container().list_electronic_documents.execute(
        current_actor(),
        statuses=statuses,
        limit=query_int("limit", 50),
        offset=query_int("offset", 0, maximum=1_000_000),
    )
    return {"items": [presenters.electronic_document(d) for d in items]}


@bp.post("/invoicing/documents/<uuid:document_id>/retry")
@authenticated
def retry(document_id: UUID):
    document = container().retry_electronic_document.execute(current_actor(), document_id)
    return presenters.electronic_document(document)
