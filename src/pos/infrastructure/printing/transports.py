"""Cómo llegan los bytes a la impresora: cola de impresión de Windows, red o un archivo.

La cola de Windows se usa en modo RAW con las funciones de winspool.drv (ctypes), sin
instalar nada adicional: los bytes ESC/POS pasan intactos por el controlador.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Protocol

from ...domain.shared.errors import BusinessRuleViolation

NETWORK_TIMEOUT_SECONDS = 5


class PrinterUnavailable(BusinessRuleViolation):
    code = "printer_unavailable"


class Transport(Protocol):
    def send(self, data: bytes, *, job_name: str) -> None: ...


class NetworkTransport:
    """Impresoras con puerto de red (RAW / JetDirect, normalmente el 9100)."""

    def __init__(self, host: str, port: int) -> None:
        self._address = (host, port)

    def send(self, data: bytes, *, job_name: str) -> None:
        host, port = self._address
        try:
            with socket.create_connection(self._address, timeout=NETWORK_TIMEOUT_SECONDS) as connection:
                connection.sendall(data)
        except OSError as error:
            raise PrinterUnavailable(
                f"No se pudo conectar con la impresora en {host}:{port}. Revise que esté encendida y en la red."
            ) from error


class FileTransport:
    """Escribe los bytes en un archivo o dispositivo (pruebas, o /dev/usb/lp0 en Linux)."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def send(self, data: bytes, *, job_name: str) -> None:
        try:
            with self._path.open("ab") as file:
                file.write(data)
        except OSError as error:
            raise PrinterUnavailable(f"No se pudo escribir en {self._path}: {error}") from error


class WindowsSpoolerTransport:
    """Envía un trabajo RAW a una impresora instalada en Windows."""

    def __init__(self, printer_name: str) -> None:
        self._printer = printer_name

    def send(self, data: bytes, *, job_name: str) -> None:
        if sys.platform != "win32":
            raise PrinterUnavailable("La impresión por la cola de Windows solo funciona en Windows")
        _windows_raw_print(self._printer, data, job_name)


def list_windows_printers() -> list[str]:
    """Impresoras instaladas en este equipo (locales y conectadas), por nombre."""
    if sys.platform != "win32":
        return []
    return _windows_enum_printers()


# --- Windows (ctypes) --------------------------------------------------------------------

if sys.platform == "win32":  # pragma: no cover - depende del sistema operativo
    import ctypes
    from ctypes import wintypes

    _winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)

    class _DocInfo1(ctypes.Structure):
        _fields_ = [("pDocName", wintypes.LPWSTR), ("pOutputFile", wintypes.LPWSTR), ("pDatatype", wintypes.LPWSTR)]

    class _PrinterInfo4(ctypes.Structure):
        _fields_ = [("pPrinterName", wintypes.LPWSTR), ("pServerName", wintypes.LPWSTR), ("Attributes", wintypes.DWORD)]

    _winspool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    _winspool.OpenPrinterW.restype = wintypes.BOOL
    _winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    _winspool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(_DocInfo1)]
    _winspool.StartDocPrinterW.restype = wintypes.DWORD
    _winspool.StartPagePrinter.argtypes = [wintypes.HANDLE]
    _winspool.EndPagePrinter.argtypes = [wintypes.HANDLE]
    _winspool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    _winspool.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _winspool.WritePrinter.restype = wintypes.BOOL
    _winspool.EnumPrintersW.argtypes = [
        wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
    ]
    _winspool.EnumPrintersW.restype = wintypes.BOOL

    _PRINTER_ENUM_LOCAL = 0x2
    _PRINTER_ENUM_CONNECTIONS = 0x4

    def _fail(message: str) -> PrinterUnavailable:
        error = ctypes.WinError(ctypes.get_last_error())
        return PrinterUnavailable(f"{message} ({error.strerror})")

    def _windows_raw_print(printer: str, data: bytes, job_name: str) -> None:
        handle = wintypes.HANDLE()
        if not _winspool.OpenPrinterW(printer, ctypes.byref(handle), None):
            raise _fail(f"No se encontró la impresora «{printer}» en Windows")
        try:
            info = _DocInfo1(job_name, None, "RAW")
            if not _winspool.StartDocPrinterW(handle, 1, ctypes.byref(info)):
                raise _fail(f"La impresora «{printer}» no aceptó el trabajo")
            try:
                _winspool.StartPagePrinter(handle)
                written = wintypes.DWORD(0)
                buffer = ctypes.create_string_buffer(data, len(data))
                ok = _winspool.WritePrinter(handle, buffer, len(data), ctypes.byref(written))
                _winspool.EndPagePrinter(handle)
                if not ok or written.value != len(data):
                    raise _fail(f"No se pudo enviar el tiquete a «{printer}»")
            finally:
                _winspool.EndDocPrinter(handle)
        finally:
            _winspool.ClosePrinter(handle)

    def _windows_enum_printers() -> list[str]:
        flags = _PRINTER_ENUM_LOCAL | _PRINTER_ENUM_CONNECTIONS
        needed, returned = wintypes.DWORD(0), wintypes.DWORD(0)
        _winspool.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(needed), ctypes.byref(returned))
        if not needed.value:
            return []
        buffer = ctypes.create_string_buffer(needed.value)
        if not _winspool.EnumPrintersW(
            flags, None, 4, buffer, needed.value, ctypes.byref(needed), ctypes.byref(returned)
        ):
            return []
        infos = ctypes.cast(buffer, ctypes.POINTER(_PrinterInfo4))
        return sorted({infos[i].pPrinterName for i in range(returned.value) if infos[i].pPrinterName})

else:

    def _windows_raw_print(printer: str, data: bytes, job_name: str) -> None:
        raise PrinterUnavailable("La impresión por la cola de Windows solo funciona en Windows")

    def _windows_enum_printers() -> list[str]:
        return []
