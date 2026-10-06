"""Impresión directa de tiquetes y apertura del cajón monedero."""

from __future__ import annotations

import logging
from uuid import UUID

from ...domain.invoicing import DocumentKind
from ...domain.printing import PrinterConfig
from ...domain.shared.errors import BusinessRuleViolation
from ...domain.users import Permission
from ..actor import Actor
from ..common import get_or_404, require_settings
from ..ports import Clock, ReceiptPrinter, UnitOfWorkFactory
from ..receipts import printer_test_receipt, sale_receipt

logger = logging.getLogger("pos.printing")


def _require_direct(config: PrinterConfig) -> PrinterConfig:
    if not config.is_direct:
        raise BusinessRuleViolation("No hay una impresora directa configurada (Ajustes → Impresora de tiquetes)")
    return config


class PrintSaleReceipt:
    """Imprime el tiquete de una venta. Una reimpresión dice COPIA y no abre el cajón."""

    def __init__(self, uow: UnitOfWorkFactory, printer: ReceiptPrinter) -> None:
        self._uow = uow
        self._printer = printer

    def execute(self, actor: Actor, sale_id: UUID, *, copy: bool = False) -> None:
        with self._uow(read_only=True) as uow:
            sale = get_or_404(uow.sales.get(sale_id), "Venta no encontrada")
            if sale.cashier_id != actor.user_id:
                actor.require(Permission.VIEW_REPORTS)
            else:
                actor.require(Permission.SELL)
            settings = require_settings(uow)
            cashier = uow.users.get(sale.cashier_id)
            customer = uow.customers.get(sale.customer_id) if sale.customer_id else None
            document = next(
                (d for d in uow.documents.list_for_sale(sale.id) if d.kind is DocumentKind.INVOICE), None
            )
        config = _require_direct(settings.printer)
        receipt = sale_receipt(
            sale,
            settings,
            cashier_name=cashier.full_name if cashier else "",
            customer_name=customer.name if customer else None,
            document=document,
            copy=copy,
        )
        drawer = config.open_drawer and not copy and not sale.is_voided and sale.cash_in_drawer.is_positive
        self._printer.print(config, receipt, open_drawer=drawer)


class OpenCashDrawer:
    """Abre el cajón sin venta (dar sencillo, guardar billetes). Queda en el registro con el usuario."""

    def __init__(self, uow: UnitOfWorkFactory, printer: ReceiptPrinter) -> None:
        self._uow = uow
        self._printer = printer

    def execute(self, actor: Actor) -> None:
        actor.require(Permission.OPERATE_CASH)
        with self._uow(read_only=True) as uow:
            config = _require_direct(require_settings(uow).printer)
        self._printer.open_drawer(config)
        logger.info("Cajón abierto sin venta por %s", actor.username)


class PrintTestReceipt:
    """Página de prueba. Acepta una configuración sin guardar para probarla antes."""

    def __init__(self, uow: UnitOfWorkFactory, printer: ReceiptPrinter, clock: Clock) -> None:
        self._uow = uow
        self._printer = printer
        self._clock = clock

    def execute(self, actor: Actor, config: PrinterConfig | None = None) -> None:
        actor.require(Permission.MANAGE_SETTINGS)
        with self._uow(read_only=True) as uow:
            settings = require_settings(uow)
        config = _require_direct(config or settings.printer)
        self._printer.print(config, printer_test_receipt(settings, at=self._clock.now(), width=config.width))


class ListPrinters:
    def __init__(self, printer: ReceiptPrinter) -> None:
        self._printer = printer

    def execute(self, actor: Actor) -> list[str]:
        actor.require(Permission.MANAGE_SETTINGS)
        return self._printer.available_printers()
