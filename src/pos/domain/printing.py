"""Impresora de tiquetes del negocio (impresión directa, sin el diálogo del navegador)."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum

from .shared.errors import ValidationError
from .shared.values import parse_enum


class PrinterKind(StrEnum):
    BROWSER = "browser"  # el diálogo de impresión del navegador (sin configurar nada)
    WINDOWS = "windows"  # impresora instalada en el computador donde corre el sistema
    NETWORK = "network"  # impresora con cable de red o Wi-Fi (puerto 9100)


# Caracteres por línea con la fuente normal: 80 mm = 48, 58 mm = 32 (algunas de 80 mm usan 42).
PAPER_WIDTHS = (32, 42, 48)
DEFAULT_NETWORK_PORT = 9100
_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


@dataclass(frozen=True, kw_only=True)
class PrinterConfig:
    kind: PrinterKind = PrinterKind.BROWSER
    target: str = ""  # nombre de la impresora de Windows, o "IP" / "IP:puerto" de la impresora de red
    width: int = 48
    auto_print: bool = False  # imprime solo al terminar cada venta
    open_drawer: bool = True  # abre el cajón monedero cuando la venta lleva efectivo

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", parse_enum(PrinterKind, self.kind, "tipo de impresora"))
        object.__setattr__(self, "target", (self.target or "").strip())
        if self.width not in PAPER_WIDTHS:
            raise ValidationError(f"El ancho del papel debe ser uno de {', '.join(map(str, PAPER_WIDTHS))} caracteres")
        if self.kind is PrinterKind.WINDOWS and not self.target:
            raise ValidationError("Elija la impresora de Windows")
        if self.kind is PrinterKind.NETWORK:
            self.network_address()  # valida

    @property
    def is_direct(self) -> bool:
        return self.kind is not PrinterKind.BROWSER

    def network_address(self) -> tuple[str, int]:
        host, _, port_text = self.target.partition(":")
        host = host.strip()
        if not host or not _HOST.fullmatch(host):
            raise ValidationError("Escriba la dirección IP de la impresora, p. ej. 192.168.1.50")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if host.replace(".", "").isdigit():
                raise ValidationError(f"«{host}» no es una dirección IP válida") from None
        try:
            port = int(port_text) if port_text.strip() else DEFAULT_NETWORK_PORT
        except ValueError:
            raise ValidationError("El puerto de la impresora debe ser un número") from None
        if not 1 <= port <= 65535:
            raise ValidationError("El puerto de la impresora debe estar entre 1 y 65535")
        return host, port
