from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from flask import Blueprint

from ....application.use_cases.customers import CreateCustomerCommand
from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import Body, query_bool, query_int, query_text

bp = Blueprint("customers", __name__)


@bp.get("/customers")
@authenticated
def search_customers():
    items = container().search_customers.execute(
        text=query_text("q"),
        include_inactive=query_bool("include_inactive"),
        limit=query_int("limit", 50),
        offset=query_int("offset", 0, maximum=1_000_000),
    )
    return {"items": [presenters.customer(c) for c in items]}


@bp.post("/customers")
@authenticated
def create_customer():
    body = Body.from_request()
    command = CreateCustomerCommand(
        name=body.text("name"),
        document=body.text("document", required=False),
        phone=body.text("phone", required=False, default=""),
        email=body.text("email", required=False, default=""),
        address=body.text("address", required=False, default=""),
        credit_limit=body.money("credit_limit", required=False),
    )
    return presenters.customer(container().create_customer.execute(current_actor(), command)), 201


@bp.get("/customers/<uuid:customer_id>")
@authenticated
def get_customer(customer_id: UUID):
    return presenters.customer(container().get_customer.execute(customer_id))


@bp.patch("/customers/<uuid:customer_id>")
@authenticated
def update_customer(customer_id: UUID):
    body = Body.from_request()
    readers: dict[str, Callable[[], object]] = {
        "name": lambda: body.text("name"),
        "document": lambda: body.text("document", required=False),
        "phone": lambda: body.text("phone", required=False, default=""),
        "email": lambda: body.text("email", required=False, default=""),
        "address": lambda: body.text("address", required=False, default=""),
        "credit_limit": lambda: body.money("credit_limit"),
        "active": lambda: body.boolean("active", required=True),
    }
    body.reject_unknown(set(readers))
    changes = {key: read() for key, read in readers.items() if body.has(key)}
    return presenters.customer(container().update_customer.execute(current_actor(), customer_id, changes))


@bp.get("/customers/<uuid:customer_id>/statement")
@authenticated
def customer_statement(customer_id: UUID):
    statement = container().get_customer_statement.execute(
        current_actor(), customer_id, limit=query_int("limit", 50)
    )
    return presenters.customer_statement(statement)


@bp.post("/customers/<uuid:customer_id>/payments")
@authenticated
def register_payment(customer_id: UUID):
    body = Body.from_request()
    entry = container().register_customer_payment.execute(
        current_actor(),
        customer_id=customer_id,
        amount=body.money("amount"),
        method=body.text("method"),
        note=body.text("note", required=False, default=""),
    )
    return presenters.ledger_entry(entry), 201
