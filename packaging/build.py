"""Construye la versión para clientes de Windows.

    python packaging/build.py                 interfaz + ejecutable + prueba + .zip (+ instalador)
    python packaging/build.py --skip-frontend usa la interfaz ya compilada

Resultado en dist/:
    PuntoDeVenta/                       carpeta lista para copiar (PuntoDeVenta.exe sin consola,
                                        PuntoDeVentaConsola.exe para soporte)
    PuntoDeVenta-<versión>-windows.zip  la misma carpeta comprimida
    PuntoDeVenta-<versión>-setup.exe    instalador, si Inno Setup (iscc) está instalado

POS_VENDOR cambia el nombre de la empresa que aparece en las propiedades del .exe.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_DIR = DIST / "PuntoDeVenta"
EXE = APP_DIR / "PuntoDeVenta.exe"
CONSOLE_EXE = APP_DIR / "PuntoDeVentaConsola.exe"
ICON = BUILD / "icono.ico"
STATIC_INDEX = ROOT / "src" / "pos" / "presentation" / "web" / "static" / "index.html"


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def version() -> str:
    text = (ROOT / "src" / "pos" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__ = "([^"]+)"', text)
    if not match:
        sys.exit("No se encontró __version__ en src/pos/__init__.py")
    return match.group(1)


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("   $", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def build_frontend() -> None:
    step("Compilando la interfaz")
    npm = shutil.which("npm") or sys.exit("Falta Node.js (npm) para compilar la interfaz; use --skip-frontend")
    frontend = ROOT / "frontend"
    run([npm, "ci", "--no-audit", "--no-fund"], cwd=frontend)
    run([npm, "test"], cwd=frontend)
    run([npm, "run", "build"], cwd=frontend)


def write_version_info(number: str) -> None:
    parts = [int(p) for p in re.findall(r"\d+", number)][:4]
    parts += [0] * (4 - len(parts))
    vendor = os.environ.get("POS_VENDOR", "Sistema POS")
    BUILD.mkdir(exist_ok=True)
    (BUILD / "version_info.txt").write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(parts)}, prodvers={tuple(parts)}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040A04B0', [
      StringStruct('CompanyName', {vendor!r}),
      StringStruct('FileDescription', 'Punto de venta'),
      StringStruct('FileVersion', {number!r}),
      StringStruct('InternalName', 'PuntoDeVenta'),
      StringStruct('OriginalFilename', 'PuntoDeVenta.exe'),
      StringStruct('ProductName', 'Punto de Venta'),
      StringStruct('ProductVersion', {number!r})])]),
    VarFileInfo([VarStruct('Translation', [0x040A, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


def write_icon() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from pos.presentation.desktop.icon import write_ico

    write_ico(ICON)


def build_executable(number: str) -> None:
    step("Empaquetando con PyInstaller")
    write_version_info(number)
    write_icon()
    run([
        sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "PuntoDeVenta.spec"),
        "--noconfirm", "--clean", "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"),
    ])


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.load(response)


def smoke_test(number: str) -> None:
    """Arranca el programa en una carpeta de datos temporal, como lo haría un cliente nuevo.

    Se prueba con el ejecutable de consola (el mismo código) porque el del cliente no tiene
    salida de texto que leer.
    """
    step("Probando el ejecutable")
    if not EXE.is_file():
        sys.exit(f"Falta {EXE.name}")
    output = subprocess.run([str(CONSOLE_EXE), "--version"], capture_output=True, text=True, timeout=60)
    if output.stdout.strip() != number:
        sys.exit(f"--version devolvió {output.stdout!r} {output.stderr!r}")

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as home:
        env = {**os.environ, "POS_HOME": home, "POS_PORT": str(port)}
        env.pop("POS_SECRET_KEY", None)
        process = subprocess.Popen(
            [str(CONSOLE_EXE), "start", "--no-browser", "--console"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            deadline = time.monotonic() + 60
            while True:
                try:
                    health = get_json(f"{base}/health")
                    break
                except OSError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        log = process.stdout.read() if process.stdout else ""
                        sys.exit(f"El ejecutable no arrancó:\n{log}")
                    time.sleep(0.5)
            assert health == {"status": "ok", "version": number}, health
            with urllib.request.urlopen(f"{base}/caja", timeout=5) as page:
                assert b'id="root"' in page.read(), "la interfaz no se sirvió"
            assert get_json(f"{base}/api/v1/setup") == {"needs_setup": True}
            assert (Path(home) / ".env").is_file(), "no se creó el .env"
            assert (Path(home) / "data" / "pos.sqlite3").is_file(), "no se creó la base de datos"
            assert (Path(home) / "logs" / "pos.log").is_file(), "no se creó el registro"
            print("   arranca, sirve la interfaz, crea .env, base de datos y registro: OK")
        finally:
            process.terminate()
            process.wait(timeout=30)


def package_zip(number: str) -> Path:
    step("Comprimiendo")
    archive = shutil.make_archive(str(DIST / f"PuntoDeVenta-{number}-windows"), "zip", DIST, "PuntoDeVenta")
    return Path(archive)


def find_iscc() -> str | None:
    candidates = [
        shutil.which("iscc"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"),
    ]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def build_installer(number: str) -> Path | None:
    iscc = find_iscc()
    if iscc is None:
        print("\n(Inno Setup no está instalado: se omite el instalador setup.exe)")
        return None
    step("Creando el instalador")
    run([iscc, f"/DAppVersion={number}", f"/O{DIST}", str(ROOT / "packaging" / "instalador.iss")])
    return DIST / f"PuntoDeVenta-{number}-setup.exe"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-frontend", action="store_true", help="No recompilar la interfaz")
    args = parser.parse_args()
    if sys.platform != "win32":
        sys.exit("El ejecutable de Windows se construye en Windows")

    number = version()
    print(f"Punto de venta {number}")
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and tag != f"v{number}":
        sys.exit(f"La etiqueta {tag} no coincide con la versión del código ({number}): actualice src/pos/__init__.py")
    if not args.skip_frontend:
        build_frontend()
    if not STATIC_INDEX.is_file():
        sys.exit("Falta la interfaz compilada: ejecute sin --skip-frontend")
    build_executable(number)
    smoke_test(number)
    results = [package_zip(number), build_installer(number)]

    step("Listo")
    print(f"   {APP_DIR}")
    for result in filter(None, results):
        print(f"   {result}  ({result.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
