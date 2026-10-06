"""Proveedores: datos, compras de mercancía con su factura, cuentas por pagar y pagos.

Una compra afecta en una sola transacción el inventario (existencia y costo promedio),
la caja (si se paga con el efectivo del cajón) y la cuenta del proveedor (si es a crédito).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from ...domain.inventory import MovementType, StockMovement
from ...domain.shared.errors import ConflictError, ValidationError
from ...domain.shared.values import Money
from ...domain.suppliers import (
    PAYMENT_MODE_LABELS,
    Purchase,
    PurchaseLine,
    PurchasePaymentMode,
    Supplier,
    SupplierEntryType,
    SupplierLedgerEntry,
    allocate_payment,
)
from ...domain.users import Permission
from ..actor import Actor
from ..common import get_or_404, local_day_range, page_size, require_settings
from ..ports import Clock, PurchaseFilter, UnitOfWork, UnitOfWorkFactory
from .cash import require_open_session

PURCHASE_SEQUENCE = "purchase"
DUE_SOON_DAYS = 7
MAX_PENDING_FOR_SUMMARY = 5_000


def _ensure_unique_document(uow: UnitOfWork, supplier: Supplier) -> None:
    if supplier.document is None:
        return
    other = uow.suppliers.get_by_document(supplier.document)
    if other is not None and other.id != supplier.id:
        raise ConflictError(f"Ya existe un proveedor con el documento {supplier.document}")


def _business_today(uow: UnitOfWork, clock: Clock) -> date:
    return clock.now().astimezone(require_settings(uow).tzinfo).date()


def _supplier_names(uow: UnitOfWork, purchases: Sequence[Purchase]) -> dict[UUID, str]:
    names: dict[UUID, str] = {}
    for supplier_id in {p.supplier_id for p in purchases if p.supplier_id is not None}:
        supplier = uow.suppliers.get(supplier_id)
        if supplier is not None:
            names[supplier_id] = supplier.name
    return names


# --- proveedores ----------------------------------------------------------------------


@dataclass(frozen=True)
class CreateSupplierCommand:
    name: str
    document: str | None = None
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    notes: str = ""


class CreateSupplier:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, command: CreateSupplierCommand) -> Supplier:
        actor.require(Permission.MANAGE_SUPPLIERS)
        supplier = Supplier(
            name=command.name,
            document=command.document,
            contact_name=command.contact_name,
            phone=command.phone,
            email=command.email,
            address=command.address,
            notes=command.notes,
            created_at=self._clock.now(),
        )
        with self._uow() as uow:
            _ensure_unique_document(uow, supplier)
            uow.suppliers.add(supplier)
            uow.commit()
        return supplier


class UpdateSupplier:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, supplier_id: UUID, changes: Mapping[str, object]) -> Supplier:
        actor.require(Permission.MANAGE_SUPPLIERS)
        with self._uow() as uow:
            supplier = get_or_404(uow.suppliers.get(supplier_id), "Proveedor no encontrado")
            supplier.update(**changes)
            _ensure_unique_document(uow, supplier)
            uow.suppliers.save(supplier)
            uow.commit()
        return supplier


class GetSupplier:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, supplier_id: UUID) -> Supplier:
        with self._uow(read_only=True) as uow:
            return get_or_404(uow.suppliers.get(supplier_id), "Proveedor no encontrado")


class SearchSuppliers:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(
        self,
        *,
        text: str | None = None,
        include_inactive: bool = False,
        with_balance_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Supplier]:
        with self._uow(read_only=True) as uow:
            return uow.suppliers.search(
                text=text,
                include_inactive=include_inactive,
                with_balance_only=with_balance_only,
                limit=page_size(limit),
                offset=max(0, offset),
            )


@dataclass(frozen=True)
class SupplierStatement:
    supplier: Supplier
    entries: list[SupplierLedgerEntry]
    pending: list[Purchase]  # facturas con saldo, la que vence primero arriba
    today: date


class GetSupplierStatement:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, supplier_id: UUID, limit: int = 50) -> SupplierStatement:
        actor.require(Permission.MANAGE_SUPPLIERS)
        with self._uow(read_only=True) as uow:
            supplier = get_or_404(uow.suppliers.get(supplier_id), "Proveedor no encontrado")
            entries = uow.supplier_ledger.list_for_supplier(supplier_id, limit=page_size(limit))
            pending = uow.purchases.list_pending_for_supplier(supplier_id)
            today = _business_today(uow, self._clock)
        pending.sort(key=lambda p: (p.due_date is None, p.due_date or date.max, p.created_at))
        return SupplierStatement(supplier=supplier, entries=entries, pending=pending, today=today)


# --- compras -------------------------------------------------------------------------


@dataclass(frozen=True)
class PurchaseItemInput:
    product_id: UUID
    quantity: Decimal
    unit_cost: Money


@dataclass(frozen=True)
class ReceivePurchaseCommand:
    items: Sequence[PurchaseItemInput]
    payment_mode: PurchasePaymentMode
    supplier_id: UUID | None = None
    invoice_number: str = ""
    due_date: date | None = None
    note: str = ""


@dataclass(frozen=True)
class PurchaseDetails:
    purchase: Purchase
    supplier_name: str | None


class ReceivePurchase:
    """Entrada de mercancía con varios productos: lo que llega en la factura del proveedor."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, command: ReceivePurchaseCommand) -> PurchaseDetails:
        actor.require(Permission.MANAGE_INVENTORY)
        if not command.items:
            raise ValidationError("La compra debe tener al menos un producto")
        now = self._clock.now()
        with self._uow() as uow:
            supplier = None
            if command.supplier_id is not None:
                supplier = get_or_404(uow.suppliers.get(command.supplier_id), "Proveedor no encontrado")
                if not supplier.active:
                    raise ValidationError(f"El proveedor «{supplier.name}» está inactivo")
            if command.due_date is not None and command.due_date < _business_today(uow, self._clock):
                raise ValidationError("La fecha de vencimiento no puede estar en el pasado")

            products = uow.products.get_many([item.product_id for item in command.items])
            lines = []
            for item in command.items:
                product = get_or_404(products.get(item.product_id), "Producto no encontrado")
                if item.unit_cost.is_negative:
                    raise ValidationError(f"El costo de «{product.name}» no puede ser negativo")
                lines.append(
                    PurchaseLine(
                        product_id=product.id,
                        sku=product.sku,
                        description=product.name,
                        quantity=product.check_quantity(item.quantity),
                        unit_cost=item.unit_cost,
                    )
                )
            purchase = Purchase.register(
                number=uow.sequences.next_value(PURCHASE_SEQUENCE),
                user_id=actor.user_id,
                at=now,
                payment_mode=command.payment_mode,
                lines=lines,
                supplier_id=command.supplier_id,
                invoice_number=command.invoice_number,
                due_date=command.due_date,
                note=command.note,
            )
            reference = f"Compra #{purchase.number}"

            for line in purchase.lines:
                product = products[line.product_id]
                product.add_stock(line.quantity, at=now, unit_cost=line.unit_cost)
                uow.products.save(product)
                if product.track_stock:
                    uow.stock_movements.add(
                        StockMovement(
                            product_id=product.id,
                            type=MovementType.PURCHASE,
                            quantity=line.quantity,
                            stock_after=product.stock,
                            unit_cost=line.unit_cost,
                            reference=reference,
                            user_id=actor.user_id,
                            created_at=now,
                            note=supplier.name if supplier else "",
                        )
                    )

            if purchase.payment_mode is PurchasePaymentMode.CASH_DRAWER and purchase.total.is_positive:
                session = require_open_session(uow, actor)
                to_whom = f" a {supplier.name}" if supplier else ""
                session.pay_supplier(
                    amount=purchase.total, reference=f"{reference}{to_whom}", user_id=actor.user_id, at=now
                )
                uow.cash_sessions.save(session)
            elif purchase.payment_mode is PurchasePaymentMode.CREDIT:
                assert supplier is not None  # Purchase lo exige para compras a crédito
                if not purchase.total.is_positive:
                    raise ValidationError("Una compra a crédito debe tener un valor mayor que cero")
                supplier.add_debt(purchase.total)
                uow.suppliers.save(supplier)
                invoice = f" (factura {purchase.invoice_number})" if purchase.invoice_number else ""
                uow.supplier_ledger.add(
                    SupplierLedgerEntry(
                        supplier_id=supplier.id,
                        type=SupplierEntryType.PURCHASE,
                        amount=purchase.total,
                        balance_after=supplier.balance,
                        purchase_id=purchase.id,
                        user_id=actor.user_id,
                        created_at=now,
                        note=f"{reference}{invoice}",
                    )
                )
            uow.purchases.add(purchase)
            uow.commit()
        return PurchaseDetails(purchase=purchase, supplier_name=supplier.name if supplier else None)


@dataclass(frozen=True)
class ListPurchasesQuery:
    supplier_id: UUID | None = None
    pending_only: bool = False
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 50
    offset: int = 0


class ListPurchases:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, query: ListPurchasesQuery) -> list[PurchaseDetails]:
        actor.require_any(Permission.MANAGE_INVENTORY, Permission.MANAGE_SUPPLIERS)
        with self._uow(read_only=True) as uow:
            start = end = None
            if query.date_from is not None or query.date_to is not None:
                today = query.date_to or query.date_from
                assert today is not None
                start, end = local_day_range(
                    query.date_from or today, query.date_to or today, require_settings(uow).tzinfo
                )
            where = PurchaseFilter(
                supplier_id=query.supplier_id, pending_only=query.pending_only, start=start, end=end
            )
            purchases = uow.purchases.find(where, limit=page_size(query.limit), offset=max(0, query.offset))
            names = _supplier_names(uow, purchases)
        return [PurchaseDetails(p, names.get(p.supplier_id) if p.supplier_id else None) for p in purchases]


class GetPurchase:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, purchase_id: UUID) -> PurchaseDetails:
        actor.require_any(Permission.MANAGE_INVENTORY, Permission.MANAGE_SUPPLIERS)
        with self._uow(read_only=True) as uow:
            purchase = get_or_404(uow.purchases.get(purchase_id), "Compra no encontrada")
            names = _supplier_names(uow, [purchase])
        return PurchaseDetails(purchase, names.get(purchase.supplier_id) if purchase.supplier_id else None)


# --- pagos y cuentas por pagar ------------------------------------------------------------


@dataclass(frozen=True)
class PaySupplierCommand:
    supplier_id: UUID
    amount: Money
    from_cash_drawer: bool = False  # True: sale del efectivo de la caja abierta
    method: str = ""  # cómo se pagó si no es de la caja (transferencia, Nequi...)
    note: str = ""


@dataclass(frozen=True)
class SupplierPaymentResult:
    entry: SupplierLedgerEntry
    applied: list[tuple[Purchase, Money]]  # a qué facturas se aplicó y cuánto


class PaySupplier:
    """Abono a la deuda con un proveedor; se aplica a las facturas que vencen primero."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, command: PaySupplierCommand) -> SupplierPaymentResult:
        actor.require(Permission.MANAGE_SUPPLIERS)
        now = self._clock.now()
        if command.from_cash_drawer:
            method = PAYMENT_MODE_LABELS[PurchasePaymentMode.CASH_DRAWER]
        else:
            method = (command.method or "").strip() or PAYMENT_MODE_LABELS[PurchasePaymentMode.EXTERNAL]
        with self._uow() as uow:
            supplier = get_or_404(uow.suppliers.get(command.supplier_id), "Proveedor no encontrado")
            supplier.pay(command.amount)
            applied = allocate_payment(uow.purchases.list_pending_for_supplier(supplier.id), command.amount)
            for purchase, _ in applied:
                uow.purchases.save(purchase)
            if command.from_cash_drawer:
                session = require_open_session(uow, actor)
                session.pay_supplier(
                    amount=command.amount, reference=f"Pago a {supplier.name}", user_id=actor.user_id, at=now
                )
                uow.cash_sessions.save(session)
            numbers = ", ".join(f"#{purchase.number}" for purchase, _ in applied)
            entry = SupplierLedgerEntry(
                supplier_id=supplier.id,
                type=SupplierEntryType.PAYMENT,
                amount=command.amount,
                balance_after=supplier.balance,
                user_id=actor.user_id,
                created_at=now,
                method=method,
                note=(command.note or "").strip() or (f"Abono a compras {numbers}" if numbers else "Abono"),
            )
            uow.suppliers.save(supplier)
            uow.supplier_ledger.add(entry)
            uow.commit()
        return SupplierPaymentResult(entry=entry, applied=applied)


@dataclass(frozen=True)
class SupplierDebt:
    supplier: Supplier
    overdue: Money
    next_due_date: date | None


@dataclass(frozen=True)
class PayablesSummary:
    today: date
    total: Money
    overdue: Money
    due_soon: Money  # vence en los próximos DUE_SOON_DAYS días
    suppliers: list[SupplierDebt]  # los que tienen deuda, el más vencido primero


class GetPayablesSummary:
    """Cuánto se debe, cuánto está vencido y a quién pagarle primero."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor) -> PayablesSummary:
        actor.require(Permission.MANAGE_SUPPLIERS)
        with self._uow(read_only=True) as uow:
            today = _business_today(uow, self._clock)
            pending = uow.purchases.find(PurchaseFilter(pending_only=True), limit=MAX_PENDING_FOR_SUMMARY)
            debtors = uow.suppliers.search(include_inactive=True, with_balance_only=True, limit=MAX_PENDING_FOR_SUMMARY)

        soon = today + timedelta(days=DUE_SOON_DAYS)
        overdue: dict[UUID, Money] = {}
        next_due: dict[UUID, date] = {}
        due_soon = Money.zero()
        for purchase in pending:
            if purchase.supplier_id is None:
                continue
            if purchase.is_overdue(today):
                overdue[purchase.supplier_id] = overdue.get(purchase.supplier_id, Money.zero()) + purchase.outstanding
            elif purchase.due_date is not None:
                if purchase.due_date <= soon:
                    due_soon += purchase.outstanding
                current = next_due.get(purchase.supplier_id)
                if current is None or purchase.due_date < current:
                    next_due[purchase.supplier_id] = purchase.due_date
        rows = [
            SupplierDebt(supplier=s, overdue=overdue.get(s.id, Money.zero()), next_due_date=next_due.get(s.id))
            for s in debtors
        ]
        rows.sort(key=lambda r: (-r.overdue.amount, r.next_due_date or date.max, r.supplier.name.casefold()))
        return PayablesSummary(
            today=today,
            total=Money.sum(s.balance for s in debtors),
            overdue=Money.sum(overdue.values()),
            due_soon=due_soon,
            suppliers=rows,
        )
