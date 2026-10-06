"""Caja: apertura, ingresos y retiros, cierre con arqueo y reporte por método de pago."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.cash import CashMovement, CashSession
from ...domain.shared.errors import BusinessRuleViolation, ConflictError, NotFoundError, ValidationError
from ...domain.shared.values import Money
from ...domain.users import Permission
from ..actor import Actor
from ..common import get_or_404, page_size
from ..ports import Clock, UnitOfWork, UnitOfWorkFactory
from .reports import PaymentTotal, summarize_payments


@dataclass(frozen=True)
class CashSessionReport:
    session: CashSession
    sales_count: int
    voided_count: int
    sales_total: Money
    totals_by_method: list[PaymentTotal]


def build_cash_report(uow: UnitOfWork, session: CashSession) -> CashSessionReport:
    sales = uow.sales.find(cash_session_id=session.id)
    completed = [sale for sale in sales if not sale.is_voided]
    return CashSessionReport(
        session=session,
        sales_count=len(completed),
        voided_count=len(sales) - len(completed),
        sales_total=Money.sum(sale.total for sale in completed),
        totals_by_method=summarize_payments(completed),
    )


def require_open_session(uow: UnitOfWork, actor: Actor) -> CashSession:
    session = uow.cash_sessions.get_open_for_cashier(actor.user_id)
    if session is None:
        raise BusinessRuleViolation("Primero abra la caja")
    return session


class OpenCashSession:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, opening_amount: Money) -> CashSession:
        actor.require(Permission.OPERATE_CASH)
        with self._uow() as uow:
            if uow.cash_sessions.get_open_for_cashier(actor.user_id) is not None:
                raise ConflictError("Ya tiene una caja abierta")
            session = CashSession.open(cashier_id=actor.user_id, opening_amount=opening_amount, at=self._clock.now())
            uow.cash_sessions.add(session)
            uow.commit()
        return session


class GetCurrentCashSession:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor) -> CashSessionReport:
        with self._uow() as uow:
            session = uow.cash_sessions.get_open_for_cashier(actor.user_id)
            if session is None:
                raise NotFoundError("No tiene una caja abierta")
            return build_cash_report(uow, session)


class RegisterCashMovement:
    """Ingresos (p. ej. más sencillo) y retiros (p. ej. pago a un proveedor) con su motivo."""

    KINDS = ("deposit", "withdrawal")

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, *, kind: str, amount: Money, note: str) -> CashMovement:
        actor.require(Permission.OPERATE_CASH)
        if kind not in self.KINDS:
            raise ValidationError("El tipo de movimiento debe ser 'deposit' (ingreso) o 'withdrawal' (retiro)")
        with self._uow() as uow:
            session = require_open_session(uow, actor)
            operation = session.deposit if kind == "deposit" else session.withdraw
            movement = operation(amount=amount, note=note, user_id=actor.user_id, at=self._clock.now())
            uow.cash_sessions.save(session)
            uow.commit()
        return movement


class CloseCashSession:
    """Cierra la caja propia, o la de otro usuario si se tiene permiso de supervisión."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: Actor, *, counted_amount: Money, note: str = "", session_id: UUID | None = None
    ) -> CashSessionReport:
        actor.require(Permission.OPERATE_CASH)
        with self._uow() as uow:
            if session_id is None:
                session = require_open_session(uow, actor)
            else:
                session = get_or_404(uow.cash_sessions.get(session_id), "Caja no encontrada")
                if session.cashier_id != actor.user_id:
                    actor.require(Permission.SUPERVISE_CASH)
            session.close(counted_amount=counted_amount, at=self._clock.now(), note=note)
            uow.cash_sessions.save(session)
            report = build_cash_report(uow, session)
            uow.commit()
        return report


class GetCashSessionReport:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, session_id: UUID) -> CashSessionReport:
        with self._uow() as uow:
            session = get_or_404(uow.cash_sessions.get(session_id), "Caja no encontrada")
            if session.cashier_id != actor.user_id:
                actor.require(Permission.SUPERVISE_CASH)
            return build_cash_report(uow, session)


class ListCashSessions:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor, limit: int = 30, offset: int = 0) -> list[CashSession]:
        actor.require(Permission.SUPERVISE_CASH)
        with self._uow() as uow:
            return uow.cash_sessions.list_recent(limit=page_size(limit), offset=max(0, offset))
