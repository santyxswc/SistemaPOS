# Receta de PyInstaller para PuntoDeVenta.exe. Se usa desde packaging/build.py.
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
STATIC = ROOT / "src" / "pos" / "presentation" / "web" / "static"
ICON = ROOT / "build" / "icono.ico"  # lo genera build.py con el mismo dibujo del ícono del reloj
VERSION = ROOT / "build" / "version_info.txt"

# tzdata trae las zonas horarias (America/Bogota) que Windows no tiene.
tz_datas, tz_binaries, tz_hidden = collect_all("tzdata")

a = Analysis(
    [str(ROOT / "packaging" / "punto_de_venta.py")],
    pathex=[str(ROOT / "src")],
    binaries=tz_binaries,
    datas=[
        (str(STATIC), "pos/presentation/web/static"),
        (str(ROOT / ".env.example"), "."),
        *tz_datas,
    ],
    hiddenimports=["waitress", "pystray._win32", *tz_hidden],
    excludes=["tkinter", "unittest", "pydoc", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)


def executable(name, console):
    return EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=name,
        console=console,
        icon=str(ICON),
        version=str(VERSION),
        upx=False,
    )


# Dos ejecutables con los mismos archivos: el del cliente no abre ventana negra (ícono junto al
# reloj); el de consola es para soporte (reset-password, license) y lo usa la prueba del build.
gui = executable("PuntoDeVenta", console=False)
console = executable("PuntoDeVentaConsola", console=True)
coll = COLLECT(gui, console, a.binaries, a.datas, name="PuntoDeVenta", upx=False)
