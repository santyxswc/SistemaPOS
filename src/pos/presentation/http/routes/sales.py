from __future__ import annotations

from uuid import UUID

from flask import Blueprint

from ....application.use_cases.sales import CreateSaleCommand, ListSalesQuery, PaymentInput, SaleItemInput
from .. import presenters
from ..context import authenticated, business_today, container, current_actor
from ..request import Body, query_date, query_int, query_uuid

bp = Blueprint("sales", __name__)


@bp.post("/sales")
@authenticated
def create_sale():
    body = Body.from_request()
    command = CreateSaleCommand(
        items=[
            SaleItemInput(
                product_id=item.uuid("product_id"),
                quantity=item.decimal("quantity"),
                discount=item.money("discount", required=False),
            )
            for item in body.items("items")
        ],
        payments=[
            PaymentInput(method=payment.text("method"), amount=payment.money("amount"))
            for payment in body.items("payments")
        ],
        customer_id=body.uuid("customer_id", required=False),
        note=body.text("note", required=False, default=""),
    )
    return presenters.sale(container().create_sale.execute(current_actor(), command)), 201


@bp.get("/sales")
@authenticated
def list_sales():
    today = business_today()
    query = ListSalesQuery(
        date_from=query_date("from", today),
        date_to=query_date("to", today),
        cashier_id=query_uuid("cashier_id"),
        limit=query_int("limit", 50),
        offset=query_int("offset", 0, maximum=1_000_000),
    )
    return {"items": [presenters.sale(s) for s in container().list_sales.execute(current_actor(), query)]}


@bp.get("/sales/<uuid:sale_id>")
@authenticated
def get_sale(sale_id: UUID):
    return presenters.sale(container().get_sale.execute(current_actor(), sale_id))


@bp.post("/sales/<uuid:sale_id>/void")
@authenticated
def void_sale(sale_id: UUID):
    body = Body.from_request()
    return presenters.sale(container().void_sale.execute(current_actor(), sale_id, body.text("reason")))
