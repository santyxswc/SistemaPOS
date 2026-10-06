"""Dónde están los archivos del programa y dónde se guardan los datos del negocio.

Ejecutando desde el código fuente, todo vive en la carpeta del proyecto. Empaquetado
como .exe, el programa puede estar en una carpeta de solo lectura (Archivos de
programa), así que los datos van a %LOCALAPPDATA%\\PuntoDeVenta: actualizar el
programa reemplaza sus archivos sin tocar la base de datos. POS_HOME cambia la
carpeta de datos en ambos casos.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_FOLDER = "PuntoDeVenta"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    """True cuando corre empaquetado con PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Archivos que acompañan al programa (p. ej. .env.example)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return _PROJECT_ROOT


def data_root() -> Path:
    """Configuración (.env), base de datos, respaldos y registros."""
    custom = os.environ.get("POS_HOME", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_FOLDER
    return _PROJECT_ROOT
