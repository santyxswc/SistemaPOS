"""Ventas: el corazón del POS.

Una venta afecta en una sola transacción: el inventario, la caja y la cuenta del
cliente (si es fiada). Si algo falla, nada queda a medias.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from ...domain.customers import Customer, LedgerEntry, LedgerEntryType
from ...domain.inventory import MovementType, StockMovement
from ...domain.payments import PaymentKind
from ...domain.sales import Sale, SaleLine, SalePayment
from ...domain.settings import BusinessSettings
from ...domain.shared.errors import BusinessRuleViolation, ConflictError, NotFoundError, ValidationError
from ...domain.shared.values import Money
from ...domain.users import Permission
from ..actor import Actor
from ..common import get_or_404, local_day_range, page_size, require_settings
from ..ports import Clock, UnitOfWork, UnitOfWorkFactory
from .cash import require_open_session


@dataclass(frozen=True)
class SaleItemInput:
    product_id: UUID
    quantity: Decimal
    discount: Money | None = None


@dataclass(frozen=True)
class PaymentInput:
    method: str
    amount: Money


@dataclass(frozen=True)
class CreateSaleCommand:
    items: Sequence[SaleItemInput]
    payments: Sequence[PaymentInput]
    customer_id: UUID | None = None
    note: str = ""
    request_id: str | None = None  # misma clave = misma venta (reintentos seguros)


MAX_REQUEST_ID_LENGTH = 64


def _clean_request_id(request_id: str | None) -> str | None:
    if request_id is None:
        return None
    cleaned = request_id.strip()
    if not cleaned or len(cleaned) > MAX_REQUEST_ID_LENGTH:
        raise ValidationError(f"La clave de idempotencia debe tener entre 1 y {MAX_REQUEST_ID_LENGTH} caracteres")
    return cleaned


def _previous_attempt(uow: UnitOfWork, actor: Actor, request_id: str | None) -> Sale | None:
    """Si la caja reintenta una venta que ya quedó registrada, devuelve esa misma venta."""
    if request_id is None:
        return None
    sale = uow.sales.get_by_request_id(request_id)
    if sale is not None and sale.cashier_id != actor.user_id:
        raise ConflictError("La clave de idempotencia ya fue usada por otro usuario")
    return sale


def _resolve_payment(settings: BusinessSettings, payment: PaymentInput) -> SalePayment:
    method = settings.payment_method(payment.method)
    if method.kind is PaymentKind.CREDIT and not settings.credit_sales_enabled:
        raise BusinessRuleViolation("Las ventas fiadas están desactivadas en este negocio")
    return SalePayment(method_code=method.code, method_name=method.name, kind=method.kind, amount=payment.amount)


def _load_customer(uow: UnitOfWork, customer_id: UUID | None) -> Customer | None:
    if customer_id is None:
        return None
    return get_or_404(uow.customers.get(customer_id), "Cliente no encontrado")


class CreateSale:
    """Registra una venta. Con request_id, repetir la petición no duplica la venta."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, command: CreateSaleCommand) -> Sale:
        actor.require(Permission.SELL)
        if not command.items:
            raise ValidationError("La venta debe tener al menos un producto")
        request_id = _clean_request_id(command.request_id)
        now = self._clock.now()

        with self._uow() as uow:
            previous = _previous_attempt(uow, actor, request_id)
            if previous is not None:
                return previous
            settings = require_settings(uow)
            session = require_open_session(uow, actor)
            customer = _load_customer(uow, command.customer_id)
            products = uow.products.get_many({item.product_id for item in command.items})

            lines: list[SaleLine] = []
            for item in command.items:
                product = products.get(item.product_id)
                if product is None:
                    raise NotFoundError("Uno de los productos no existe")
                if not product.active:
                    raise BusinessRuleViolation(f"«{product.name}» está inactivo")
                discount = item.discount or Money.zero()
                if discount.is_positive:
                    actor.require(Permission.APPLY_DISCOUNTS)
                lines.append(
                    SaleLine.build(
                        product_id=product.id,
                        sku=product.sku,
                        description=product.name,
                        quantity=product.check_quantity(item.quantity),
                        unit_price=product.price,  # el precio sale del catálogo, nunca del cliente
                        discount=discount,
                        tax_rate=product.tax_rate,
                        tax_policy=settings.tax_policy,
                    )
                )

            sale = Sale.create(
                number=uow.sequences.next_value("sale"),
                cashier_id=actor.user_id,
                cash_session_id=session.id,
                customer_id=customer.id if customer else None,
                lines=lines,
                payments=[_resolve_payment(settings, payment) for payment in command.payments],
                at=now,
                note=command.note,
                request_id=request_id,
            )
            uow.sales.add(sale)

            # 1. Inventario
            for line in sale.lines:
                product = products[line.product_id]
                product.remove_stock(line.quantity, allow_negative=settings.allow_negative_stock, at=now)
                if product.track_stock:
                    uow.stock_movements.add(
                        StockMovement(
                            product_id=product.id,
                            type=MovementType.SALE,
                            quantity=-line.quantity,
                            stock_after=product.stock,
                            user_id=actor.user_id,
                            created_at=now,
                            reference=f"Venta #{sale.number}",
                        )
                    )
            for product in products.values():
                uow.products.save(product)

            # 2. Fiado
            if sale.credit_amount.is_positive and customer is not None:
                customer.charge(sale.credit_amount)
                uow.customers.save(customer)
                uow.ledger.add(
                    LedgerEntry(
                        customer_id=customer.id,
                        type=LedgerEntryType.CHARGE,
                        amount=sale.credit_amount,
                        balance_after=customer.balance,
                        user_id=actor.user_id,
                        created_at=now,
                        sale_id=sale.id,
                        note=f"Venta #{sale.number}",
                    )
                )

            # 3. Caja
            session.register_sale(
                sale_number=sale.number, cash_amount=sale.cash_in_drawer, user_id=actor.user_id, at=now
            )
            uow.cash_sessions.save(session)
            uow.commit()
        return sale


class VoidSale:
    """Anula una venta y revierte inventario, fiado y efectivo."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, sale_id: UUID, reason: str) -> Sale:
        actor.require(Permission.VOID_SALES)
        now = self._clock.now()
        with self._uow() as uow:
            sale = get_or_404(uow.sales.get(sale_id), "Venta no encontrada")
            sale.void(by=actor.user_id, reason=reason, at=now)
            reference = f"Anulación venta #{sale.number}"

            products = uow.products.get_many({line.product_id for line in sale.lines})
            for line in sale.lines:
                product = products.get(line.product_id)
                if product is None or not product.track_stock:
                    continue
                product.add_stock(line.quantity, at=now)
                uow.stock_movements.add(
                    StockMovement(
                        product_id=product.id,
                        type=MovementType.SALE_VOID,
                        quantity=line.quantity,
                        stock_after=product.stock,
                        user_id=actor.user_id,
                        created_at=now,
                        reference=reference,
                    )
                )
            for product in products.values():
                uow.products.save(product)

            if sale.credit_amount.is_positive and sale.customer_id is not None:
                customer = get_or_404(uow.customers.get(sale.customer_id), "Cliente no encontrado")
                customer.reverse_charge(sale.credit_amount)
                uow.customers.save(customer)
                uow.ledger.add(
                    LedgerEntry(
                        customer_id=customer.id,
                        type=LedgerEntryType.REVERSAL,
                        amount=sale.credit_amount,
                        balance_after=customer.balance,
                        user_id=actor.user_id,
                        created_at=now,
                        sale_id=sale.id,
                        note=reference,
                    )
                )

            if sale.cash_in_drawer.is_positive:
                # El efectivo sale de la caja original si sigue abierta; si no, de la de quien anula.
                session = uow.cash_sessions.get(sale.cash_session_id)
                if session is None or not session.is_open:
                    session = require_open_session(uow, actor)
                session.register_sale_void(
                    sale_number=sale.number, cash_amount=sale.cash_in_drawer, user_id=actor.user_id, at=now
                )
                uow.cash_sessions.save(session)

            uow.sales.save(sale)
            uow.commit()
        return sale


class GetSale:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, sale_id: UUID) -> Sale:
        with self._uow(read_only=True) as uow:
            sale = get_or_404(uow.sales.get(sale_id), "Venta no encontrada")
        if sale.cashier_id != actor.user_id:
            actor.require(Permission.VIEW_REPORTS)
        return sale


@dataclass(frozen=True)
class ListSalesQuery:
    date_from: date
    date_to: date
    cashier_id: UUID | None = None
    limit: int = 50
    offset: int = 0


class ListSales:
    """Quien ve reportes ve todas las ventas; un cajero solo las suyas."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, query: ListSalesQuery) -> list[Sale]:
        cashier_id = query.cashier_id
        if not actor.can(Permission.VIEW_REPORTS):
            actor.require(Permission.SELL)
            cashier_id = actor.user_id
        with self._uow(read_only=True) as uow:
            settings = require_settings(uow)
            start, end = local_day_range(query.date_from, query.date_to, settings.tzinfo)
            return uow.sales.find(
                start=start,
                end=end,
                cashier_id=cashier_id,
                limit=page_size(query.limit),
                offset=max(0, query.offset),
            )
