from __future__ import annotations

from flask import Blueprint

from .. import presenters
from ..context import authenticated, business_today, container, current_actor
from ..request import query_date, query_int, query_text
from ..workbooks import sales_report_sheets, xlsx_download

bp = Blueprint("reports", __name__)


@bp.get("/reports/sales-summary")
@authenticated
def sales_summary():
    today = business_today()
    summary = container().get_sales_summary.execute(
        current_actor(),
        query_date("from", today),
        query_date("to", today),
        group_by=query_text("group_by") or "day",
    )
    return presenters.sales_summary(summary)


@bp.get("/reports/top-products")
@authenticated
def top_products():
    today = business_today()
    items = container().get_top_products.execute(
        current_actor(), query_date("from", today), query_date("to", today), limit=query_int("limit", 10)
    )
    return {"items": [presenters.product_sales(item) for item in items]}


@bp.get("/reports/export")
@authenticated
def export_report():
    today = business_today()
    date_from, date_to = query_date("from", today), query_date("to", today)
    export = container().export_sales_report.execute(current_actor(), date_from, date_to)
    return xlsx_download(sales_report_sheets(export), f"ventas-{date_from:%Y-%m-%d}-a-{date_to:%Y-%m-%d}.xlsx")
