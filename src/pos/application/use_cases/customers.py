"""Clientes, estado de cuenta y abonos a fiados."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from ...domain.customers import Customer, LedgerEntry, LedgerEntryType
from ...domain.payments import PaymentKind
from ...domain.shared.errors import ConflictError, ValidationError
from ...domain.shared.values import Money
from ...domain.users import Permission
from ..actor import Actor
from ..common import get_or_404, page_size, require_settings
from ..ports import Clock, UnitOfWork, UnitOfWorkFactory
from .cash import require_open_session


def _ensure_unique_document(uow: UnitOfWork, customer: Customer) -> None:
    if customer.document is None:
        return
    other = uow.customers.get_by_document(customer.document)
    if other is not None and other.id != customer.id:
        raise ConflictError(f"Ya existe un cliente con el documento {customer.document}")


@dataclass(frozen=True)
class CreateCustomerCommand:
    name: str
    document: str | None = None
    phone: str = ""
    email: str = ""
    address: str = ""
    credit_limit: Money | None = None


class CreateCustomer:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, command: CreateCustomerCommand) -> Customer:
        actor.require(Permission.MANAGE_CUSTOMERS)
        credit_limit = command.credit_limit or Money.zero()
        if credit_limit.is_positive:
            actor.require(Permission.GRANT_CREDIT)
        customer = Customer(
            name=command.name,
            document=command.document,
            phone=command.phone,
            email=command.email,
            address=command.address,
            credit_limit=credit_limit,
            created_at=self._clock.now(),
        )
        with self._uow() as uow:
            _ensure_unique_document(uow, customer)
            uow.customers.add(customer)
            uow.commit()
        return customer


class UpdateCustomer:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, customer_id: UUID, changes: Mapping[str, object]) -> Customer:
        actor.require(Permission.MANAGE_CUSTOMERS)
        if "credit_limit" in changes:
            actor.require(Permission.GRANT_CREDIT)
        with self._uow() as uow:
            customer = get_or_404(uow.customers.get(customer_id), "Cliente no encontrado")
            customer.update(**changes)
            _ensure_unique_document(uow, customer)
            uow.customers.save(customer)
            uow.commit()
        return customer


class GetCustomer:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, customer_id: UUID) -> Customer:
        with self._uow(read_only=True) as uow:
            return get_or_404(uow.customers.get(customer_id), "Cliente no encontrado")


class SearchCustomers:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(
        self, *, text: str | None = None, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> list[Customer]:
        with self._uow(read_only=True) as uow:
            return uow.customers.search(
                text=text, include_inactive=include_inactive, limit=page_size(limit), offset=max(0, offset)
            )


@dataclass(frozen=True)
class CustomerStatement:
    customer: Customer
    entries: list[LedgerEntry]


class GetCustomerStatement:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, customer_id: UUID, limit: int = 50) -> CustomerStatement:
        actor.require(Permission.COLLECT_PAYMENTS)
        with self._uow(read_only=True) as uow:
            customer = get_or_404(uow.customers.get(customer_id), "Cliente no encontrado")
            entries = uow.ledger.list_for_customer(customer_id, limit=page_size(limit))
        return CustomerStatement(customer=customer, entries=entries)


class RegisterCustomerPayment:
    """Abono a la deuda de un cliente. Si es en efectivo, entra a la caja de quien lo recibe."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: Actor, *, customer_id: UUID, amount: Money, method: str, note: str = ""
    ) -> LedgerEntry:
        actor.require(Permission.COLLECT_PAYMENTS)
        now = self._clock.now()
        with self._uow() as uow:
            settings = require_settings(uow)
            payment_method = settings.payment_method(method)
            if payment_method.kind is PaymentKind.CREDIT:
                raise ValidationError("Un abono no se puede pagar con fiado")
            customer = get_or_404(uow.customers.get(customer_id), "Cliente no encontrado")
            customer.receive_payment(amount)
            entry = LedgerEntry(
                customer_id=customer.id,
                type=LedgerEntryType.PAYMENT,
                amount=amount,
                balance_after=customer.balance,
                user_id=actor.user_id,
                created_at=now,
                note=(note or "").strip() or f"Abono ({payment_method.name})",
            )
            if payment_method.behavior.goes_to_cash_drawer:
                session = require_open_session(uow, actor)
                session.register_credit_collection(
                    amount=amount, customer_name=customer.name, user_id=actor.user_id, at=now
                )
                uow.cash_sessions.save(session)
            uow.customers.save(customer)
            uow.ledger.add(entry)
            uow.commit()
        return entry
