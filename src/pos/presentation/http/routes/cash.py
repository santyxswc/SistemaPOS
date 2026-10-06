from __future__ import annotations

from uuid import UUID

from flask import Blueprint

from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import Body, query_int

bp = Blueprint("cash", __name__)


@bp.post("/cash-sessions")
@authenticated
def open_session():
    body = Body.from_request()
    session = container().open_cash_session.execute(current_actor(), body.money("opening_amount"))
    return presenters.cash_session(session), 201


@bp.get("/cash-sessions")
@authenticated
def list_sessions():
    items = container().list_cash_sessions.execute(
        current_actor(), limit=query_int("limit", 30), offset=query_int("offset", 0, maximum=1_000_000)
    )
    return {"items": [presenters.cash_session(s) for s in items]}


@bp.get("/cash-sessions/current")
@authenticated
def current_session():
    return presenters.cash_report(container().get_current_cash_session.execute(current_actor()))


@bp.post("/cash-sessions/current/movements")
@authenticated
def register_movement():
    body = Body.from_request()
    movement = container().register_cash_movement.execute(
        current_actor(), kind=body.text("type"), amount=body.money("amount"), note=body.text("note")
    )
    return presenters.cash_movement(movement), 201


@bp.post("/cash-sessions/current/close")
@authenticated
def close_current_session():
    body = Body.from_request()
    report = container().close_cash_session.execute(
        current_actor(),
        counted_amount=body.money("counted_amount"),
        note=body.text("note", required=False, default=""),
    )
    return presenters.cash_report(report)


@bp.post("/cash-sessions/<uuid:session_id>/close")
@authenticated
def close_session(session_id: UUID):
    body = Body.from_request()
    report = container().close_cash_session.execute(
        current_actor(),
        counted_amount=body.money("counted_amount"),
        note=body.text("note", required=False, default=""),
        session_id=session_id,
    )
    return presenters.cash_report(report)


@bp.get("/cash-sessions/<uuid:session_id>")
@authenticated
def session_report(session_id: UUID):
    return presenters.cash_report(container().get_cash_session_report.execute(current_actor(), session_id))
