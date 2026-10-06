"""Impresión directa de tiquetes en impresoras térmicas ESC/POS."""

from __future__ import annotations

from collections.abc import Callable

from ...application.receipts import ReceiptDocument
from ...domain.printing import PrinterConfig, PrinterKind
from ...domain.shared.errors import BusinessRuleViolation
from .escpos import EscPosEncoder
from .transports import (
    FileTransport,
    NetworkTransport,
    PrinterUnavailable,
    Transport,
    WindowsSpoolerTransport,
    list_windows_printers,
)

__all__ = ["EscPosReceiptPrinter", "FileTransport", "PrinterUnavailable"]

TransportFactory = Callable[[PrinterConfig], Transport]


def default_transport(config: PrinterConfig) -> Transport:
    """Estrategia de envío según el tipo de impresora configurada."""
    if config.kind is PrinterKind.WINDOWS:
        return WindowsSpoolerTransport(config.target)
    if config.kind is PrinterKind.NETWORK:
        return NetworkTransport(*config.network_address())
    raise BusinessRuleViolation("No hay una impresora directa configurada: el tiquete se imprime desde el navegador")


class EscPosReceiptPrinter:
    def __init__(self, transport_for: TransportFactory = default_transport) -> None:
        self._transport_for = transport_for

    def print(self, config: PrinterConfig, document: ReceiptDocument, *, open_drawer: bool = False) -> None:
        data = EscPosEncoder(config.width).encode(document, open_drawer=open_drawer)
        self._transport_for(config).send(data, job_name="Tiquete")

    def open_drawer(self, config: PrinterConfig) -> None:
        self._transport_for(config).send(EscPosEncoder(config.width).drawer_pulse(), job_name="Abrir cajón")

    def available_printers(self) -> list[str]:
        return list_windows_printers()
