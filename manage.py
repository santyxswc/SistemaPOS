#!/usr/bin/env python3
"""Comandos de administración del POS.

    python manage.py init             instalación en un paso: configuración, base de datos y administrador
    python manage.py create-admin     crea el primer administrador
    python manage.py runserver        inicia el sistema (POS_ENV=development para modo desarrollo)
    python manage.py backup           copia de seguridad de la base de datos
"""

from __future__ import annotations

import argparse
import dataclasses
import getpass
import logging
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
sys.path.insert(0, str(ROOT / "src"))

from pos.bootstrap import Container, build_container  # noqa: E402
from pos.config import AppConfig, load_dotenv, new_secret_key, render_env  # noqa: E402
from pos.domain.shared.errors import DomainError  # noqa: E402
from pos.infrastructure.persistence.sqlite.backup import backup_database  # noqa: E402


def _config() -> AppConfig:
    load_dotenv(ENV_FILE)
    config = AppConfig.from_env()
    database = Path(config.database_path)
    if not database.is_absolute():
        # Relativa a la carpeta del sistema, no a donde se ejecuta el comando (p. ej. un acceso directo).
        config = dataclasses.replace(config, database_path=str(ROOT / database))
    return config


def _container() -> Container:
    return build_container(_config())


def _ask_admin(container: Container, username: str | None, full_name: str | None) -> None:
    username = username or input("Usuario del administrador (p. ej. admin): ").strip()
    full_name = full_name or input("Nombre completo: ").strip()
    password = os.environ.get("POS_ADMIN_PASSWORD")  # instalaciones desatendidas
    if not password:
        password = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
        if password != getpass.getpass("Repita la contraseña: "):
            sys.exit("Las contraseñas no coinciden")
    user = container.bootstrap_admin.execute(username=username, full_name=full_name, password=password)
    print(f"Administrador «{user.username}» creado.")


def init(args: argparse.Namespace) -> None:
    if ENV_FILE.exists():
        print(f"Se conserva la configuración existente en {ENV_FILE.name}")
    else:
        business = args.business or input("Nombre del negocio: ").strip() or "Mi negocio"
        template = (ROOT / ".env.example").read_text(encoding="utf-8")
        values = {"POS_ENV": "production", "POS_SECRET_KEY": new_secret_key(), "POS_BUSINESS_NAME": business}
        ENV_FILE.write_text(render_env(template, values), encoding="utf-8")
        print(f"Configuración creada en {ENV_FILE.name} con una clave secreta nueva.")

    container = _container()
    print(f"Base de datos lista en {container.config.database_path}")
    with container.uow_factory(read_only=True) as uow:
        has_users = uow.users.count() > 0
    if has_users:
        print("Ya hay usuarios registrados.")
    else:
        _ask_admin(container, args.username, args.name)
    print("\nListo. Inicie el sistema con:  python manage.py runserver")


def create_admin(args: argparse.Namespace) -> None:
    _ask_admin(_container(), args.username, args.name)
    print("Ya puede iniciar sesión.")


def runserver(args: argparse.Namespace) -> None:
    from pos.presentation.http.app import create_app

    container = _container()
    app = create_app(container)
    host = args.host or container.config.host
    port = args.port or container.config.port
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"
    if container.config.is_development:
        app.run(host=host, port=port, debug=True)
        return
    try:
        from waitress import serve
    except ImportError:
        sys.exit("Instale las dependencias (pip install -r requirements.txt) o use POS_ENV=development")
    logging.getLogger("pos").info("POS escuchando en %s", url)
    if args.open:
        webbrowser.open(url)
    serve(app, host=host, port=port, threads=8)


def backup(args: argparse.Namespace) -> None:
    config = _config()
    target_dir = Path(args.dir) if args.dir else Path(config.database_path).parent / "backups"
    if not Path(config.database_path).exists():
        sys.exit(f"No existe la base de datos {config.database_path}: ejecute primero python manage.py init")
    target = backup_database(config.database_path, target_dir, now=datetime.now(), keep=args.keep)
    print(f"Respaldo creado: {target}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Sistema POS para negocios pequeños")
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("init", help="Instalación en un paso")
    setup.add_argument("--business", help="Nombre del negocio")
    setup.add_argument("--username")
    setup.add_argument("--name", help="Nombre completo del administrador")
    setup.set_defaults(handler=init)

    admin = commands.add_parser("create-admin", help="Crea el primer administrador")
    admin.add_argument("--username")
    admin.add_argument("--name", help="Nombre completo")
    admin.set_defaults(handler=create_admin)

    server = commands.add_parser("runserver", help="Inicia el sistema")
    server.add_argument("--host")
    server.add_argument("--port", type=int)
    server.add_argument("--open", action="store_true", help="Abre el navegador al iniciar")
    server.set_defaults(handler=runserver)

    copy = commands.add_parser("backup", help="Copia de seguridad de la base de datos")
    copy.add_argument("--dir", help="Carpeta destino (por defecto data/backups)")
    copy.add_argument("--keep", type=int, default=30, help="Cuántos respaldos conservar (por defecto 30)")
    copy.set_defaults(handler=backup)

    args = parser.parse_args()
    try:
        args.handler(args)
    except DomainError as error:
        sys.exit(f"Error: {error.message}")


if __name__ == "__main__":
    main()
