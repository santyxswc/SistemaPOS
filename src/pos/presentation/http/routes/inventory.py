from __future__ import annotations

from flask import Blueprint

from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import Body, InvalidPayload, query_int, query_uuid

bp = Blueprint("inventory", __name__)


@bp.post("/inventory/purchases")
@authenticated
def register_purchase():
    body = Body.from_request()
    movement = container().register_purchase.execute(
        current_actor(),
        product_id=body.uuid("product_id"),
        quantity=body.decimal("quantity"),
        unit_cost=body.money("unit_cost", required=False),
        note=body.text("note", required=False, default=""),
    )
    return presenters.stock_movement(movement), 201


@bp.post("/inventory/adjustments")
@authenticated
def adjust_stock():
    body = Body.from_request()
    movement = container().adjust_stock.execute(
        current_actor(),
        product_id=body.uuid("product_id"),
        counted_quantity=body.decimal("counted_quantity"),
        reason=body.text("reason"),
    )
    return presenters.stock_movement(movement), 201


@bp.get("/inventory/low-stock")
@authenticated
def low_stock():
    return {"items": [presenters.product(p) for p in container().list_low_stock.execute()]}


@bp.get("/inventory/movements")
@authenticated
def stock_movements():
    product_id = query_uuid("product_id")
    if product_id is None:
        raise InvalidPayload("Indique el producto con ?product_id=", "product_id")
    items = container().list_stock_movements.execute(current_actor(), product_id, limit=query_int("limit", 50))
    return {"items": [presenters.stock_movement(m) for m in items]}
