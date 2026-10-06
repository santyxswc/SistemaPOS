"""Comandos del POS. Son los mismos para `python manage.py ...` y para `PuntoDeVenta.exe ...`.

    start            (por defecto) inicia el sistema y abre el navegador; la primera vez lo prepara solo
    init             instalación desde la consola: configuración, base de datos y administrador
    create-admin     crea el primer administrador
    reset-password   asigna una contraseña nueva a un usuario (soporte: el dueño la olvidó)
    license          muestra el estado de la licencia o instala un código
    runserver        inicia solo el servidor (POS_ENV=development para modo desarrollo)
    backup           copia de seguridad de la base de datos
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
import threading
import urllib.request
import webbrowser
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__
from .bootstrap import Container, build_container
from .config import AppConfig, ensure_env_file, load_config
from .domain.shared.errors import DomainError
from .infrastructure.persistence.sqlite.backup import backup_database
from .paths import data_root, is_frozen, resource_root

logger = logging.getLogger("pos")

_FALLBACK_ENV = (
    "POS_ENV=production\nPOS_SECRET_KEY=\nPOS_DATABASE_PATH=data/pos.sqlite3\nPOS_HOST=127.0.0.1\nPOS_PORT=8000\n"
)


def _env_template() -> str:
    example = resource_root() / ".env.example"
    return example.read_text(encoding="utf-8") if example.is_file() else _FALLBACK_ENV


def _config() -> AppConfig:
    return load_config(data_root())


def _container() -> Container:
    return build_container(_config())


def _local_url(config: AppConfig, host: str | None = None, port: int | None = None) -> str:
    host = host or config.host
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{browser_host}:{port or config.port}"


def _already_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
            return json.load(response).get("status") == "ok"
    except (OSError, ValueError):
        return False


def _log_to_file(folder: Path) -> Path:
    """Registro en archivo para soporte: rota a 1 MB y guarda los últimos 5."""
    log_file = folder / "logs" / "pos.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    return log_file


def _serve(container: Container, host: str, port: int) -> None:
    from waitress import serve

    from .presentation.http.app import create_app

    for worker in container.background_workers:
        worker.start()
    try:
        serve(create_app(container), host=host, port=port, threads=8)
    except OSError as error:
        logger.error("No se pudo usar el puerto %s: %s", port, error)
        sys.exit(f"El puerto {port} está ocupado por otro programa. Cambie POS_PORT en {data_root() / '.env'}")
    finally:
        for worker in container.background_workers:
            worker.stop()


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


def start(args: argparse.Namespace) -> None:
    """Doble clic: prepara una instalación nueva sin preguntas y abre el navegador.

    El nombre del negocio y el administrador se piden después, en el navegador.
    """
    folder = data_root()
    log_file = _log_to_file(folder)
    if ensure_env_file(folder / ".env", _env_template()):
        logger.info("Instalación nueva preparada en %s", folder)
    config = _config()
    url = _local_url(config)
    if _already_running(url):
        print(f"El punto de venta ya está abierto. Abriendo {url}")
        webbrowser.open(url)
        return

    container = build_container(config)
    print(f"Punto de venta {__version__}")
    print(f"  Dirección:  {url}")
    print(f"  Datos:      {folder}")
    print(f"  Registro:   {log_file}")
    print("\nNo cierre esta ventana mientras use el sistema.\n")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    _serve(container, config.host, config.port)


def init(args: argparse.Namespace) -> None:
    env_file = data_root() / ".env"
    business = None
    if env_file.exists():
        print(f"Se conserva la configuración existente en {env_file}")
    else:
        business = args.business or input("Nombre del negocio: ").strip() or "Mi negocio"
        ensure_env_file(env_file, _env_template(), POS_BUSINESS_NAME=business)
        print(f"Configuración creada en {env_file} con una clave secreta nueva.")

    container = _container()
    print(f"Base de datos lista en {container.config.database_path}")
    with container.uow_factory(read_only=True) as uow:
        has_users = uow.users.count() > 0
    if has_users:
        print("Ya hay usuarios registrados.")
    else:
        _ask_admin(container, args.username, args.name)
    print("\nListo. Inicie el sistema con:  python manage.py start")


def create_admin(args: argparse.Namespace) -> None:
    _ask_admin(_container(), args.username, args.name)
    print("Ya puede iniciar sesión.")


def _ask_new_password() -> str:
    password = os.environ.get("POS_NEW_PASSWORD")  # soporte remoto sin teclado interactivo
    if password:
        return password
    password = getpass.getpass("Contraseña nueva (mínimo 8 caracteres): ")
    if password != getpass.getpass("Repita la contraseña: "):
        sys.exit("Las contraseñas no coinciden")
    return password


def reset_password(args: argparse.Namespace) -> None:
    username = args.username or input("Usuario al que se le cambia la contraseña: ").strip()
    user = _container().reset_password_from_console.execute(username, _ask_new_password())
    print(f"Listo: «{user.username}» ya puede entrar con la contraseña nueva.")
    print("Si el sistema estaba bloqueado por intentos fallidos, ciérrelo y ábralo de nuevo.")


def license_command(args: argparse.Namespace) -> None:
    container = _container()
    if args.code:
        status = container.install_license.execute_from_console(args.code)
        print("Licencia instalada.")
    else:
        status = container.get_license_status.execute()
    print(status.message)
    if status.license is not None:
        print(f"  Negocio:  {status.license.business_name}")
        print(f"  Plan:     {status.license.plan}")
    print(f"  Usuarios: {status.max_users or 'sin límite'}")
    if status.expires_on is not None:
        print(f"  Vence:    {status.expires_on:%d/%m/%Y}")


def runserver(args: argparse.Namespace) -> None:
    container = _container()
    host = args.host or container.config.host
    port = args.port or container.config.port
    url = _local_url(container.config, host, port)
    if container.config.is_development:
        from .presentation.http.app import create_app

        # Con recarga automática, Flask corre el código en un proceso hijo: las tareas van solo allí.
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            for worker in container.background_workers:
                worker.start()
        create_app(container).run(host=host, port=port, debug=True)
        return
    logger.info("POS escuchando en %s", url)
    if args.open:
        webbrowser.open(url)
    _serve(container, host, port)


def backup(args: argparse.Namespace) -> None:
    config = _config()
    if not Path(config.database_path).exists():
        sys.exit(f"No existe la base de datos {config.database_path}: inicie el sistema al menos una vez")
    if args.dir:  # copia puntual a otra carpeta, sin tocar las de siempre
        target = backup_database(config.database_path, args.dir, now=datetime.now(), keep=args.keep)
        print(f"Respaldo creado: {target}")
        return
    _log_to_file(data_root())  # la tarea programada no tiene consola: el registro dice si funcionó
    result = build_container(config).run_backup.execute_unattended()
    print(f"Respaldo creado: {result.file.name}")
    if result.extra_copy:
        print(f"Copia adicional: {result.extra_copy}")
    if result.extra_error:
        print(f"Aviso: {result.extra_error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="PuntoDeVenta", description="Sistema POS para negocios pequeños")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")

    launch = commands.add_parser("start", help="Inicia el sistema y abre el navegador (por defecto)")
    launch.add_argument("--no-browser", action="store_true", help="No abrir el navegador")
    launch.set_defaults(handler=start)

    setup = commands.add_parser("init", help="Instalación desde la consola")
    setup.add_argument("--business", help="Nombre del negocio")
    setup.add_argument("--username")
    setup.add_argument("--name", help="Nombre completo del administrador")
    setup.set_defaults(handler=init)

    admin = commands.add_parser("create-admin", help="Crea el primer administrador")
    admin.add_argument("--username")
    admin.add_argument("--name", help="Nombre completo")
    admin.set_defaults(handler=create_admin)

    reset = commands.add_parser("reset-password", help="Asigna una contraseña nueva (el dueño la olvidó)")
    reset.add_argument("--username", help="Usuario (si no lo sabe, el error lista los administradores)")
    reset.set_defaults(handler=reset_password)

    lic = commands.add_parser("license", help="Estado de la licencia o instalación de un código")
    lic.add_argument("code", nargs="?", help="Código de licencia enviado por el proveedor")
    lic.set_defaults(handler=license_command)

    server = commands.add_parser("runserver", help="Inicia solo el servidor")
    server.add_argument("--host")
    server.add_argument("--port", type=int)
    server.add_argument("--open", action="store_true", help="Abre el navegador al iniciar")
    server.set_defaults(handler=runserver)

    copy = commands.add_parser("backup", help="Copia de seguridad de la base de datos")
    copy.add_argument("--dir", help="Carpeta destino para una copia puntual (por defecto data/backups y la carpeta "
                      "adicional de Ajustes)")
    copy.add_argument("--keep", type=int, default=30, help="Con --dir: cuántos respaldos conservar (por defecto 30)")
    copy.set_defaults(handler=backup)
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:  # doble clic en el .exe
        args = parser.parse_args(["start", *(argv or [])])
    try:
        args.handler(args)
    except DomainError as error:
        sys.exit(f"Error: {error.message}")
    except Exception:
        if not is_frozen():
            raise
        # Empaquetado, la ventana se cerraría sin dejar ver el error.
        logger.exception("Error al iniciar el punto de venta")
        input("\nOcurrió un error al iniciar. Revise el registro y presione Enter para cerrar...")
        sys.exit(1)
