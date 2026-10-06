from __future__ import annotations

from flask import Blueprint

from ....domain.payments import PaymentKind, PaymentMethodConfig
from ....domain.shared.values import parse_enum
from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import Body

bp = Blueprint("settings", __name__)

_TEXT_FIELDS = ("business_name", "tax_id", "address", "phone", "currency", "timezone", "receipt_footer",
                "backup_folder")
_FLAG_FIELDS = ("prices_include_tax", "allow_negative_stock", "credit_sales_enabled")


@bp.get("/settings")
@authenticated
def get_settings():
    return presenters.settings(container().get_settings.execute())


@bp.patch("/settings")
@authenticated
def update_settings():
    body = Body.from_request()
    body.reject_unknown({*_TEXT_FIELDS, *_FLAG_FIELDS, "default_tax_rate", "payment_methods"})
    changes: dict[str, object] = {}
    for key in _TEXT_FIELDS:
        if body.has(key):
            changes[key] = body.text(key, required=False, default="")
    for key in _FLAG_FIELDS:
        if body.has(key):
            changes[key] = body.boolean(key, required=True)
    if body.has("default_tax_rate"):
        changes["default_tax_rate"] = body.tax_rate("default_tax_rate", required=True)
    if body.has("payment_methods"):
        changes["payment_methods"] = tuple(
            PaymentMethodConfig(
                code=method.text("code"),
                name=method.text("name"),
                kind=parse_enum(PaymentKind, method.text("kind"), "tipo de pago"),
                active=method.boolean("active", default=True),
            )
            for method in body.items("payment_methods")
        )
    return presenters.settings(container().update_settings.execute(current_actor(), changes))
