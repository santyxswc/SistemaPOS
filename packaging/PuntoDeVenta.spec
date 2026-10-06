# Receta de PyInstaller para PuntoDeVenta.exe. Se usa desde packaging/build.py.
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
STATIC = ROOT / "src" / "pos" / "presentation" / "web" / "static"

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
    hiddenimports=["waitress", *tz_hidden],
    excludes=["tkinter", "unittest", "pydoc", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PuntoDeVenta",
    console=True,  # la ventana muestra la dirección y se cierra para apagar el sistema
    version=str(ROOT / "build" / "version_info.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PuntoDeVenta", upx=False)
