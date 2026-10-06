"""Convierte objetos del dominio en JSON. El dinero viaja como texto ("12500.00") para no perder exactitud."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ...application.actor import Actor
from ...application.ports import BackupFile, BackupResult
from ...application.use_cases.cash import CashSessionReport
from ...application.use_cases.catalog_import import ProductImportReport
from ...application.use_cases.customers import CustomerStatement
from ...application.use_cases.reports import PaymentTotal, ProductSales, SalesSummary
from ...application.use_cases.suppliers import (
    PayablesSummary,
    PurchaseDetails,
    SupplierPaymentResult,
    SupplierStatement,
)
from ...domain.cash import CashMovement, CashSession
from ...domain.catalog import Category, Product
from ...domain.customers import Customer, LedgerEntry
from ...domain.inventory import StockMovement
from ...domain.licensing import LicenseStatus
from ...domain.sales import Sale
from ...domain.settings import BusinessSettings
from ...domain.shared.values import Money, format_quantity
from ...domain.suppliers import Purchase, Supplier, SupplierLedgerEntry
from ...domain.users import (
    EDITABLE_ROLES,
    GRANTABLE_PERMISSIONS,
    PERMISSION_LABELS,
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    RolePermissions,
    User,
)

Json = dict[str, Any]


def money(value: Money | None) -> str | None:
    return None if value is None else str(value.amount)


def quantity(value: Decimal | None) -> str | None:
    return None if value is None else format_quantity(value)


def ts(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def uid(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def user(value: User) -> Json:
    return {
        "id": uid(value.id),
        "username": value.username,
        "full_name": value.full_name,
        "role": value.role.value,
        "active": value.active,
        "created_at": ts(value.created_at),
    }


def actor(value: Actor) -> Json:
    return {
        "id": uid(value.user_id),
        "username": value.username,
        "full_name": value.full_name,
        "role": value.role.value,
        "permissions": sorted(permission.value for permission in value.permissions),
    }


def settings(value: BusinessSettings) -> Json:
    return {
        "business_name": value.business_name,
        "tax_id": value.tax_id,
        "address": value.address,
        "phone": value.phone,
        "currency": value.currency,
        "timezone": value.timezone,
        "prices_include_tax": value.prices_include_tax,
        "default_tax_rate": str(value.default_tax_rate),
        "allow_negative_stock": value.allow_negative_stock,
        "credit_sales_enabled": value.credit_sales_enabled,
        "receipt_footer": value.receipt_footer,
        "backup_folder": value.backup_folder,
        "payment_methods": [
            {"code": m.code, "name": m.name, "kind": m.kind.value, "active": m.active}
            for m in value.payment_methods
        ],
    }


def license_status(value: LicenseStatus) -> Json:
    license = value.license
    return {
        "state": value.state.value,
        "valid": value.is_valid,
        "needs_attention": value.needs_attention,
        "message": value.message,
        "max_users": value.max_users,
        "expires_on": value.expires_on.isoformat() if value.expires_on else None,
        "days_left": value.days_left,
        "license": None
        if license is None
        else {
            "id": license.license_id,
            "business_name": license.business_name,
            "plan": license.plan,
            "max_users": license.max_users,
            "issued_on": license.issued_on.isoformat(),
            "expires_on": license.expires_on.isoformat() if license.expires_on else None,
        },
    }


def backup_file(value: BackupFile) -> Json:
    return {"name": value.name, "created_at": ts(value.created_at), "size_bytes": value.size_bytes}


def backup_result(value: BackupResult) -> Json:
    return {"file": backup_file(value.file), "extra_copy": value.extra_copy, "extra_error": value.extra_error}


def import_report(value: ProductImportReport) -> Json:
    return {
        "dry_run": value.dry_run,
        "total_rows": value.total_rows,
        "created": value.created,
        "updated": value.updated,
        "unchanged": value.unchanged,
        "skipped_existing": value.skipped_existing,
        "new_categories": value.new_categories,
        "errors": [{"line": issue.line, "message": issue.message} for issue in value.errors],
    }


def category(value: Category) -> Json:
    return {"id": uid(value.id), "name": value.name, "active": value.active}


def product(value: Product) -> Json:
    return {
        "id": uid(value.id),
        "sku": value.sku,
        "barcode": value.barcode,
        "name": value.name,
        "category_id": uid(value.category_id),
        "price": money(value.price),
        "cost": money(value.cost),
        "tax_rate": str(value.tax_rate),
        "unit": value.unit.value,
        "track_stock": value.track_stock,
        "stock": quantity(value.stock),
        "min_stock": quantity(value.min_stock),
        "is_low_stock": value.is_low_stock,
        "active": value.active,
        "updated_at": ts(value.updated_at),
    }


def stock_movement(value: StockMovement) -> Json:
    return {
        "id": uid(value.id),
        "product_id": uid(value.product_id),
        "type": value.type.value,
        "quantity": quantity(value.quantity),
        "stock_after": quantity(value.stock_after),
        "unit_cost": money(value.unit_cost),
        "reference": value.reference,
        "note": value.note,
        "user_id": uid(value.user_id),
        "created_at": ts(value.created_at),
    }


def customer(value: Customer) -> Json:
    return {
        "id": uid(value.id),
        "name": value.name,
        "document": value.document,
        "phone": value.phone,
        "email": value.email,
        "address": value.address,
        "credit_limit": money(value.credit_limit),
        "balance": money(value.balance),
        "available_credit": money(value.available_credit),
        "active": value.active,
    }


def ledger_entry(value: LedgerEntry) -> Json:
    return {
        "id": uid(value.id),
        "type": value.type.value,
        "amount": money(value.amount),
        "balance_after": money(value.balance_after),
        "sale_id": uid(value.sale_id),
        "note": value.note,
        "user_id": uid(value.user_id),
        "created_at": ts(value.created_at),
    }


def customer_statement(value: CustomerStatement) -> Json:
    return {"customer": customer(value.customer), "entries": [ledger_entry(e) for e in value.entries]}


def cash_movement(value: CashMovement) -> Json:
    return {
        "id": uid(value.id),
        "type": value.type.value,
        "amount": money(value.amount),
        "reference": value.reference,
        "note": value.note,
        "user_id": uid(value.user_id),
        "created_at": ts(value.created_at),
    }


def cash_session(value: CashSession) -> Json:
    return {
        "id": uid(value.id),
        "cashier_id": uid(value.cashier_id),
        "status": value.status.value,
        "opening_amount": money(value.opening_amount),
        "expected_cash": money(value.expected_cash),
        "counted_amount": money(value.counted_amount),
        "difference": money(value.difference),
        "opened_at": ts(value.opened_at),
        "closed_at": ts(value.closed_at),
        "closing_note": value.closing_note,
        "movements": [cash_movement(m) for m in value.movements],
    }


def payment_total(value: PaymentTotal) -> Json:
    return {"method": value.code, "name": value.name, "kind": value.kind.value, "amount": money(value.amount)}


def cash_report(value: CashSessionReport) -> Json:
    return {
        "session": cash_session(value.session),
        "sales_count": value.sales_count,
        "voided_count": value.voided_count,
        "sales_total": money(value.sales_total),
        "totals_by_method": [payment_total(t) for t in value.totals_by_method],
    }


def sale(value: Sale) -> Json:
    return {
        "id": uid(value.id),
        "number": value.number,
        "status": value.status.value,
        "cashier_id": uid(value.cashier_id),
        "cash_session_id": uid(value.cash_session_id),
        "customer_id": uid(value.customer_id),
        "subtotal": money(value.subtotal),
        "tax_total": money(value.tax_total),
        "discount_total": money(value.discount_total),
        "total": money(value.total),
        "change": money(value.change),
        "note": value.note,
        "created_at": ts(value.created_at),
        "voided_at": ts(value.voided_at),
        "void_reason": value.void_reason or None,
        "lines": [
            {
                "product_id": uid(line.product_id),
                "sku": line.sku,
                "description": line.description,
                "quantity": quantity(line.quantity),
                "unit_price": money(line.unit_price),
                "discount": money(line.discount),
                "tax_rate": str(line.tax_rate),
                "base": money(line.base),
                "tax": money(line.tax),
                "total": money(line.total),
            }
            for line in value.lines
        ],
        "payments": [
            {"method": p.method_code, "name": p.method_name, "kind": p.kind.value, "amount": money(p.amount)}
            for p in value.payments
        ],
    }


def sales_summary(value: SalesSummary) -> Json:
    return {
        "from": value.date_from.isoformat(),
        "to": value.date_to.isoformat(),
        "group_by": value.group_by,
        "sales_count": value.sales_count,
        "voided_count": value.voided_count,
        "subtotal": money(value.subtotal),
        "tax_total": money(value.tax_total),
        "discount_total": money(value.discount_total),
        "total": money(value.total),
        "average_ticket": money(value.average_ticket),
        "by_payment_method": [payment_total(t) for t in value.by_payment_method],
        "by_period": [
            {"period": p.period, "sales_count": p.sales_count, "total": money(p.total)} for p in value.by_period
        ],
    }


def product_sales(value: ProductSales) -> Json:
    return {
        "product_id": uid(value.product_id),
        "sku": value.sku,
        "description": value.description,
        "quantity": quantity(value.quantity),
        "total": money(value.total),
    }


def supplier(value: Supplier) -> Json:
    return {
        "id": uid(value.id),
        "name": value.name,
        "document": value.document,
        "contact_name": value.contact_name,
        "phone": value.phone,
        "email": value.email,
        "address": value.address,
        "notes": value.notes,
        "balance": money(value.balance),
        "active": value.active,
    }


def supplier_entry(value: SupplierLedgerEntry) -> Json:
    return {
        "id": uid(value.id),
        "type": value.type.value,
        "amount": money(value.amount),
        "balance_after": money(value.balance_after),
        "purchase_id": uid(value.purchase_id),
        "method": value.method,
        "note": value.note,
        "user_id": uid(value.user_id),
        "created_at": ts(value.created_at),
    }


def purchase(value: Purchase, supplier_name: str | None = None, today: date | None = None) -> Json:
    return {
        "id": uid(value.id),
        "number": value.number,
        "supplier_id": uid(value.supplier_id),
        "supplier_name": supplier_name,
        "invoice_number": value.invoice_number,
        "payment_mode": value.payment_mode.value,
        "status": value.status.value,
        "total": money(value.total),
        "outstanding": money(value.outstanding),
        "due_date": value.due_date.isoformat() if value.due_date else None,
        "overdue": value.is_overdue(today) if today else False,
        "note": value.note,
        "user_id": uid(value.user_id),
        "created_at": ts(value.created_at),
        "lines": [
            {
                "product_id": uid(line.product_id),
                "sku": line.sku,
                "description": line.description,
                "quantity": quantity(line.quantity),
                "unit_cost": money(line.unit_cost),
                "total": money(line.total),
            }
            for line in value.lines
        ],
    }


def purchase_details(value: PurchaseDetails, today: date | None = None) -> Json:
    return purchase(value.purchase, value.supplier_name, today)


def supplier_statement(value: SupplierStatement) -> Json:
    return {
        "supplier": supplier(value.supplier),
        "entries": [supplier_entry(e) for e in value.entries],
        "pending": [purchase(p, value.supplier.name, value.today) for p in value.pending],
    }


def supplier_payment(value: SupplierPaymentResult) -> Json:
    return {
        "entry": supplier_entry(value.entry),
        "applied": [{"purchase_id": uid(p.id), "number": p.number, "amount": money(amount)}
                    for p, amount in value.applied],
    }


def payables_summary(value: PayablesSummary) -> Json:
    return {
        "today": value.today.isoformat(),
        "total": money(value.total),
        "overdue": money(value.overdue),
        "due_soon": money(value.due_soon),
        "suppliers": [
            {
                "supplier": supplier(row.supplier),
                "overdue": money(row.overdue),
                "next_due_date": row.next_due_date.isoformat() if row.next_due_date else None,
            }
            for row in value.suppliers
        ],
    }


def role_permissions(value: RolePermissions) -> Json:
    """Lo que puede hacer cada rol y la lista de permisos con su nombre para la pantalla."""
    return {
        "roles": [
            {
                "role": role.value,
                "label": ROLE_LABELS[role],
                "editable": role in EDITABLE_ROLES,
                "customized": value.is_customized(role),
                "permissions": sorted(p.value for p in value.for_role(role)),
                "default_permissions": sorted(
                    p.value for p in (frozenset(Permission) if role is Role.ADMIN else ROLE_PERMISSIONS[role])
                ),
            }
            for role in Role
        ],
        "permissions": [
            {"code": p.value, "label": PERMISSION_LABELS[p], "grantable": p in GRANTABLE_PERMISSIONS}
            for p in Permission
        ],
    }
