from __future__ import annotations

from collections.abc import Callable
from datetime import date
from uuid import UUID

from flask import Blueprint

from ....application.use_cases.suppliers import (
    CreateSupplierCommand,
    ListPurchasesQuery,
    PaySupplierCommand,
    PurchaseItemInput,
    ReceivePurchaseCommand,
)
from ....domain.shared.values import parse_enum
from ....domain.suppliers import PurchasePaymentMode
from .. import presenters
from ..context import authenticated, business_today, container, current_actor
from ..request import Body, InvalidPayload, query_bool, query_int, query_text, query_uuid

bp = Blueprint("suppliers", __name__)


def _optional_date(body: Body, key: str) -> date | None:
    text = body.text(key, required=False)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise InvalidPayload(f"'{key}' debe tener el formato AAAA-MM-DD", key) from None


def _query_optional_date(name: str) -> date | None:
    text = query_text(name)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise InvalidPayload(f"'{name}' debe tener el formato AAAA-MM-DD", name) from None


@bp.get("/suppliers")
@authenticated
def search_suppliers():
    items = container().search_suppliers.execute(
        text=query_text("q"),
        include_inactive=query_bool("include_inactive"),
        with_balance_only=query_bool("with_balance"),
        limit=query_int("limit", 50),
        offset=query_int("offset", 0, maximum=1_000_000),
    )
    return {"items": [presenters.supplier(s) for s in items]}


@bp.post("/suppliers")
@authenticated
def create_supplier():
    body = Body.from_request()
    command = CreateSupplierCommand(
        name=body.text("name"),
        document=body.text("document", required=False),
        contact_name=body.text("contact_name", required=False, default=""),
        phone=body.text("phone", required=False, default=""),
        email=body.text("email", required=False, default=""),
        address=body.text("address", required=False, default=""),
        notes=body.text("notes", required=False, default=""),
    )
    return presenters.supplier(container().create_supplier.execute(current_actor(), command)), 201


@bp.get("/suppliers/payables")
@authenticated
def payables():
    return presenters.payables_summary(container().get_payables_summary.execute(current_actor()))


@bp.get("/suppliers/<uuid:supplier_id>")
@authenticated
def get_supplier(supplier_id: UUID):
    return presenters.supplier(container().get_supplier.execute(supplier_id))


@bp.patch("/suppliers/<uuid:supplier_id>")
@authenticated
def update_supplier(supplier_id: UUID):
    body = Body.from_request()
    readers: dict[str, Callable[[], object]] = {
        "name": lambda: body.text("name"),
        "document": lambda: body.text("document", required=False),
        "contact_name": lambda: body.text("contact_name", required=False, default=""),
        "phone": lambda: body.text("phone", required=False, default=""),
        "email": lambda: body.text("email", required=False, default=""),
        "address": lambda: body.text("address", required=False, default=""),
        "notes": lambda: body.text("notes", required=False, default=""),
        "active": lambda: body.boolean("active", required=True),
    }
    body.reject_unknown(set(readers))
    changes = {key: read() for key, read in readers.items() if body.has(key)}
    return presenters.supplier(container().update_supplier.execute(current_actor(), supplier_id, changes))


@bp.get("/suppliers/<uuid:supplier_id>/statement")
@authenticated
def supplier_statement(supplier_id: UUID):
    statement = container().get_supplier_statement.execute(
        current_actor(), supplier_id, limit=query_int("limit", 50)
    )
    return presenters.supplier_statement(statement)


@bp.post("/suppliers/<uuid:supplier_id>/payments")
@authenticated
def pay_supplier(supplier_id: UUID):
    body = Body.from_request()
    command = PaySupplierCommand(
        supplier_id=supplier_id,
        amount=body.money("amount"),
        from_cash_drawer=body.boolean("from_cash_drawer", default=False),
        method=body.text("method", required=False, default=""),
        note=body.text("note", required=False, default=""),
    )
    return presenters.supplier_payment(container().pay_supplier.execute(current_actor(), command)), 201


@bp.post("/purchases")
@authenticated
def receive_purchase():
    body = Body.from_request()
    command = ReceivePurchaseCommand(
        items=[
            PurchaseItemInput(
                product_id=item.uuid("product_id"),
                quantity=item.decimal("quantity"),
                unit_cost=item.money("unit_cost"),
            )
            for item in body.items("items")
        ],
        payment_mode=parse_enum(PurchasePaymentMode, body.text("payment_mode"), "forma de pago"),
        supplier_id=body.uuid("supplier_id", required=False),
        invoice_number=body.text("invoice_number", required=False, default=""),
        due_date=_optional_date(body, "due_date"),
        note=body.text("note", required=False, default=""),
    )
    details = container().receive_purchase.execute(current_actor(), command)
    return presenters.purchase_details(details, business_today()), 201


@bp.get("/purchases")
@authenticated
def list_purchases():
    query = ListPurchasesQuery(
        supplier_id=query_uuid("supplier_id"),
        pending_only=query_bool("pending"),
        date_from=_query_optional_date("from"),
        date_to=_query_optional_date("to"),
        limit=query_int("limit", 50),
        offset=query_int("offset", 0, maximum=1_000_000),
    )
    today = business_today()
    items = container().list_purchases.execute(current_actor(), query)
    return {"items": [presenters.purchase_details(p, today) for p in items]}


@bp.get("/purchases/<uuid:purchase_id>")
@authenticated
def get_purchase(purchase_id: UUID):
    return presenters.purchase_details(container().get_purchase.execute(current_actor(), purchase_id), business_today())
