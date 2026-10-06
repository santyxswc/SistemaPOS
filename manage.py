#!/usr/bin/env python3
"""Comandos de administración del POS.

    python manage.py create-admin     crea el primer administrador
    python manage.py runserver        inicia la API (POS_ENV=development para modo desarrollo)
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from pos.bootstrap import Container, build_container  # noqa: E402
from pos.config import AppConfig, load_dotenv  # noqa: E402
from pos.domain.shared.errors import DomainError  # noqa: E402


def _container() -> Container:
    load_dotenv(ROOT / ".env")
    return build_container(AppConfig.from_env())


def create_admin(args: argparse.Namespace) -> None:
    container = _container()
    username = args.username or input("Usuario: ")
    full_name = args.name or input("Nombre completo: ")
    password = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
    if password != getpass.getpass("Repita la contraseña: "):
        sys.exit("Las contraseñas no coinciden")
    user = container.bootstrap_admin.execute(username=username, full_name=full_name, password=password)
    print(f"Administrador «{user.username}» creado. Ya puede iniciar sesión.")


def runserver(args: argparse.Namespace) -> None:
    from pos.presentation.http.app import create_app

    container = _container()
    app = create_app(container)
    host = args.host or container.config.host
    port = args.port or container.config.port
    if container.config.is_development:
        app.run(host=host, port=port, debug=True)
        return
    try:
        from waitress import serve
    except ImportError:
        sys.exit("Instale las dependencias (pip install -r requirements.txt) o use POS_ENV=development")
    logging.getLogger("pos").info("POS escuchando en http://%s:%s", host, port)
    serve(app, host=host, port=port, threads=8)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Sistema POS para negocios pequeños")
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("create-admin", help="Crea el primer administrador")
    admin.add_argument("--username")
    admin.add_argument("--name", help="Nombre completo")
    admin.set_defaults(handler=create_admin)

    server = commands.add_parser("runserver", help="Inicia la API HTTP")
    server.add_argument("--host")
    server.add_argument("--port", type=int)
    server.set_defaults(handler=runserver)

    args = parser.parse_args()
    try:
        args.handler(args)
    except DomainError as error:
        sys.exit(f"Error: {error.message}")


if __name__ == "__main__":
    main()
