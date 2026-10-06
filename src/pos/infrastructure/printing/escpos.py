"""Traduce un tiquete a comandos ESC/POS, el idioma de casi todas las impresoras térmicas
(Epson, Bixolon, Star en modo ESC/POS, 3nStar, Digital POS y las genéricas chinas)."""

from __future__ import annotations

import textwrap

from ...application.receipts import Align, Columns, QrCode, ReceiptDocument, Separator, Text

ESC = b"\x1b"
GS = b"\x1d"

INIT = ESC + b"@"
CODEPAGE_PC850 = ESC + b"t\x02"  # tabla de caracteres con tildes, ñ, ¿ y ¡ del español
ALIGN = {Align.LEFT: ESC + b"a\x00", Align.CENTER: ESC + b"a\x01", Align.RIGHT: ESC + b"a\x02"}
BOLD_ON, BOLD_OFF = ESC + b"E\x01", ESC + b"E\x00"
LARGE_ON, LARGE_OFF = GS + b"!\x11", GS + b"!\x00"  # doble ancho y doble alto
FEED_AND_CUT = ESC + b"d\x04" + GS + b"V\x42\x00"  # avanza el papel y hace un corte parcial
# Pulso al conector del cajón (pin 2): 25 × 2 ms encendido, 250 × 2 ms apagado.
OPEN_DRAWER = ESC + b"p\x00\x19\xfa"
ENCODING = "cp850"


def _qr(data: str) -> bytes:
    payload = data.encode(ENCODING, errors="replace")[:7000]
    store_length = len(payload) + 3

    def function(fn: bytes, body: bytes) -> bytes:
        size = len(body) + 2
        return GS + b"(k" + bytes([size % 256, size // 256]) + b"1" + fn + body

    return b"".join(
        [
            function(b"A", b"2\x00"),  # modelo 2
            function(b"C", b"\x05"),  # tamaño del módulo
            function(b"E", b"0"),  # corrección de errores L
            GS + b"(k" + bytes([store_length % 256, store_length // 256]) + b"1P0" + payload,
            function(b"Q", b"0"),  # imprimir
        ]
    )


class EscPosEncoder:
    def __init__(self, width: int = 48) -> None:
        self.width = width

    def encode(self, document: ReceiptDocument, *, cut: bool = True, open_drawer: bool = False) -> bytes:
        out = bytearray(INIT + CODEPAGE_PC850)
        if open_drawer:
            out += OPEN_DRAWER  # primero el cajón: el cajero da las vueltas mientras imprime
        for item in document.items:
            out += self._item(item)
        out += ALIGN[Align.LEFT]
        if cut:
            out += FEED_AND_CUT
        return bytes(out)

    def drawer_pulse(self) -> bytes:
        return INIT + OPEN_DRAWER

    def _item(self, item: object) -> bytes:
        if isinstance(item, Separator):
            return ALIGN[Align.LEFT] + self._line("-" * self.width)
        if isinstance(item, QrCode):
            return ALIGN[Align.CENTER] + _qr(item.data) + b"\n"
        if isinstance(item, Columns):
            width = self.width // 2 if item.large else self.width
            return self._styled(self._columns(item.left, item.right, width), Align.LEFT, item.bold, item.large)
        assert isinstance(item, Text)
        width = self.width // 2 if item.large else self.width
        lines = textwrap.wrap(item.text, width, break_long_words=True, break_on_hyphens=False) or [""]
        return self._styled(lines, item.align, item.bold, item.large)

    def _styled(self, lines: list[str], align: Align, bold: bool, large: bool) -> bytes:
        out = bytearray(ALIGN[align])
        if bold:
            out += BOLD_ON
        if large:
            out += LARGE_ON
        for line in lines:
            out += self._line(line)
        if large:
            out += LARGE_OFF
        if bold:
            out += BOLD_OFF
        return bytes(out)

    @staticmethod
    def _columns(left: str, right: str, width: int) -> list[str]:
        """Valor pegado al borde derecho; si el texto no cabe, sigue en la línea de abajo."""
        if len(left) + len(right) + 1 <= width:
            return [left + " " * (width - len(left) - len(right)) + right]
        wrapped = textwrap.wrap(left, width, break_long_words=True) or [""]
        last = wrapped[-1]
        if len(last) + len(right) + 1 <= width:
            wrapped[-1] = last + " " * (width - len(last) - len(right)) + right
            return wrapped
        return [*wrapped, right.rjust(width)]

    @staticmethod
    def _line(text: str) -> bytes:
        return text.encode(ENCODING, errors="replace") + b"\n"
