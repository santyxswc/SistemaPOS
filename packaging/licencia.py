#!/usr/bin/env python3
"""Herramienta del proveedor para emitir licencias. NO se entrega a los clientes.

    python packaging/licencia.py claves
        Crea el par de claves (una sola vez). La privada queda fuera del proyecto;
        la pública se escribe en src/pos/infrastructure/license_key.py.

    python packaging/licencia.py emitir --negocio "Tienda Doña Rosa" --plan Mediano --usuarios 3 --meses 12
        Imprime el código de licencia para enviarlo al cliente. Él lo pega en
        Ajustes → Licencia (o se instala con: PuntoDeVenta.exe licencia CODIGO).

    python packaging/licencia.py ver CODIGO
        Muestra lo que dice un código (y si la firma corresponde a su clave).

La clave privada es la que permite fabricar licencias: guárdela con copia de
seguridad (por ejemplo en una USB en un lugar seguro) y no la suba a GitHub.
Si la pierde, tendrá que generar otra y reemplazar la licencia de todos los clientes.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import (  # noqa: E402
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

from pos.domain.licensing import License  # noqa: E402
from pos.infrastructure.licensing import Ed25519LicenseVerifier, public_key_text, sign_license  # noqa: E402

PUBLIC_KEY_FILE = ROOT / "src" / "pos" / "infrastructure" / "license_key.py"
DEFAULT_PRIVATE_KEY = Path(os.environ.get("POS_LICENSE_KEY", Path.home() / ".punto-de-venta" / "clave-licencias.pem"))


def _add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    for day in (start.day, 30, 29, 28):  # 31 de enero + 1 mes = 28 o 29 de febrero
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError("fecha inválida")


def _passphrase() -> bytes | None:
    value = os.environ.get("POS_LICENSE_PASSPHRASE")
    return value.encode("utf-8") if value else None


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    if not path.is_file():
        sys.exit(f"No se encontró la clave privada en {path}. Créela con: python packaging/licencia.py claves")
    key = load_pem_private_key(path.read_bytes(), password=_passphrase())
    if not isinstance(key, Ed25519PrivateKey):
        sys.exit("La clave privada no es Ed25519")
    return key


def keys(args: argparse.Namespace) -> None:
    path = Path(args.clave)
    if path.exists() and not args.reemplazar:
        sys.exit(
            f"Ya existe una clave en {path}. Si la reemplaza, las licencias emitidas dejan de servir.\n"
            "Si está seguro, repita con --reemplazar."
        )
    key = Ed25519PrivateKey.generate()
    passphrase = _passphrase()
    encryption = BestAvailableEncryption(passphrase) if passphrase else NoEncryption()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, encryption))
    with contextlib.suppress(OSError):  # en Windows chmod no aplica
        path.chmod(0o600)
    PUBLIC_KEY_FILE.write_text(
        '"""Clave pública para comprobar licencias. Se genera con packaging/licencia.py; no la edite a mano."""\n\n'
        f'PUBLIC_KEY = "{public_key_text(key)}"\n',
        encoding="utf-8",
    )
    print(f"Clave privada: {path}  (haga una copia de seguridad; no la comparta)")
    print(f"Clave pública escrita en {PUBLIC_KEY_FILE.relative_to(ROOT)}: compile una versión nueva del programa.")


def issue(args: argparse.Namespace) -> None:
    key = _load_private_key(Path(args.clave))
    issued = date.today()
    expires = None
    if args.vence:
        expires = date.fromisoformat(args.vence)
    elif args.meses:
        expires = _add_months(issued, args.meses)
    license = License(
        license_id=uuid.uuid4().hex[:12],
        business_name=args.negocio,
        plan=args.plan,
        max_users=None if args.usuarios == 0 else args.usuarios,
        issued_on=issued,
        expires_on=expires,
    )
    code = sign_license(license, key)
    print(f"Negocio:  {license.business_name}")
    print(f"Plan:     {license.plan} ({license.max_users or 'sin límite de'} usuarios)")
    print(f"Vence:    {license.expires_on or 'no vence'}")
    print(f"Id:       {license.license_id}\n")
    print(code)


def show(args: argparse.Namespace) -> None:
    key = _load_private_key(Path(args.clave))
    license = Ed25519LicenseVerifier(public_key_text(key)).verify(args.codigo)
    print("Firma válida (emitida con su clave).")
    for label, value in (
        ("Id", license.license_id),
        ("Negocio", license.business_name),
        ("Plan", license.plan),
        ("Usuarios", license.max_users or "sin límite"),
        ("Emitida", license.issued_on),
        ("Vence", license.expires_on or "no vence"),
    ):
        print(f"{label + ':':10}{value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Licencias del punto de venta (uso exclusivo del proveedor)")
    parser.add_argument(
        "--clave", default=str(DEFAULT_PRIVATE_KEY), help=f"Clave privada (por defecto {DEFAULT_PRIVATE_KEY})"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("claves", help="Crea el par de claves (una sola vez)")
    generate.add_argument("--reemplazar", action="store_true", help="Reemplaza una clave existente")
    generate.set_defaults(handler=keys)

    emit = commands.add_parser("emitir", help="Emite el código de licencia de un cliente")
    emit.add_argument("--negocio", required=True, help="Nombre del negocio del cliente")
    emit.add_argument("--plan", required=True, help="Nombre del plan, p. ej. Básico o Mediano")
    emit.add_argument("--usuarios", type=int, required=True, help="Usuarios activos permitidos (0 = sin límite)")
    when = emit.add_mutually_exclusive_group()
    when.add_argument("--meses", type=int, help="Vence en N meses a partir de hoy")
    when.add_argument("--vence", help="Fecha de vencimiento AAAA-MM-DD (sin --meses ni --vence, no vence)")
    emit.set_defaults(handler=issue)

    check = commands.add_parser("ver", help="Muestra el contenido de un código")
    check.add_argument("codigo")
    check.set_defaults(handler=show)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
