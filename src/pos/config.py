"""Configuración técnica desde variables de entorno.

Lo técnico (base de datos, llaves, puertos, módulos contratados) vive aquí y lo cambia
el técnico; lo del negocio (impuestos, métodos de pago) vive en BusinessSettings y lo
cambia el dueño desde Ajustes.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .application.modules import Module, ModuleSet, parse_module_names
from .domain.shared.errors import ValidationError

logger = logging.getLogger("pos.config")


def load_dotenv(path: str | Path = ".env") -> None:
    """Carga líneas KEY=VALUE de un archivo .env sin pisar variables ya definidas."""
    for key, value in read_env_file(Path(path)).items():
        os.environ.setdefault(key, value)


def read_env_file(path: Path) -> dict[str, str]:
    """Las variables de un .env (sin tocar las del proceso)."""
    values: dict[str, str] = {}
    if path.is_file():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def set_env_values(path: Path, values: Mapping[str, str]) -> None:
    """Cambia o agrega variables en un .env existente, conservando comentarios y el resto."""
    path.write_text(render_env(path.read_text(encoding="utf-8"), values), encoding="utf-8")


def render_env(template: str, values: Mapping[str, str]) -> str:
    """Rellena las líneas KEY= de una plantilla .env; las claves que no están se agregan al final."""
    pending = dict(values)
    lines = []
    for line in template.splitlines():
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in pending:
            line = f"{key}={pending.pop(key)}"
        lines.append(line)
    lines.extend(f"{key}={value}" for key, value in pending.items())
    return "\n".join(lines) + "\n"


def new_secret_key() -> str:
    return secrets.token_urlsafe(48)


def ensure_env_file(path: Path, template: str, **values: str) -> bool:
    """Crea el .env de una instalación nueva con una clave secreta propia. Devuelve True si lo creó."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    defaults = {"POS_ENV": "production", "POS_SECRET_KEY": new_secret_key()}
    path.write_text(render_env(template, {**defaults, **values}), encoding="utf-8")
    return True


def load_config(data_dir: Path) -> AppConfig:
    """Lee el .env de la carpeta de datos; una base de datos con ruta relativa queda dentro de ella."""
    load_dotenv(data_dir / ".env")
    config = AppConfig.from_env()
    database = Path(config.database_path)
    if not database.is_absolute():
        # Relativa a la carpeta de datos, no a donde se ejecuta el comando (p. ej. un acceso directo).
        config = dataclasses.replace(config, database_path=str(data_dir / database))
    return config


@dataclass(frozen=True)
class AppConfig:
    database_path: str
    secret_key: str
    environment: str = "production"
    token_ttl_minutes: int = 720  # un turno de 12 horas
    password_iterations: int = 600_000
    cors_origins: tuple[str, ...] = ()
    business_name: str = "Mi negocio"
    host: str = "127.0.0.1"
    port: int = 8000
    invoice_provider: str = ""  # facturación electrónica: vacío = desactivada (ver infrastructure/invoicing.py)
    update_repository: str = ""  # "usuario/repo" de GitHub donde se publican las versiones; vacío = no avisar
    modules: ModuleSet = dataclasses.field(default_factory=ModuleSet.defaults)

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AppConfig:
        env = os.environ if env is None else env
        environment = env.get("POS_ENV", "production").strip().lower()
        secret = env.get("POS_SECRET_KEY", "").strip()
        if not secret:
            if environment != "development":
                raise RuntimeError("Defina POS_SECRET_KEY (mínimo 32 caracteres) antes de iniciar en producción")
            secret = new_secret_key()
            logger.warning("POS_SECRET_KEY no definida: se usa una temporal (las sesiones se pierden al reiniciar)")
        elif len(secret) < 32:
            raise RuntimeError("POS_SECRET_KEY debe tener al menos 32 caracteres")
        return cls(
            database_path=env.get("POS_DATABASE_PATH", "data/pos.sqlite3"),
            secret_key=secret,
            environment=environment,
            token_ttl_minutes=int(env.get("POS_TOKEN_TTL_MINUTES", "720")),
            password_iterations=int(env.get("POS_PASSWORD_ITERATIONS", "600000")),
            cors_origins=tuple(o.strip() for o in env.get("POS_CORS_ORIGINS", "").split(",") if o.strip()),
            business_name=env.get("POS_BUSINESS_NAME", "Mi negocio"),
            host=env.get("POS_HOST", "127.0.0.1"),
            port=int(env.get("POS_PORT", "8000")),
            invoice_provider=env.get("POS_INVOICE_PROVIDER", "").strip(),
            update_repository=_update_repository(env),
            modules=modules_from_env(env),
        )


def modules_from_env(env: Mapping[str, str]) -> ModuleSet:
    """POS_MODULES_DISABLED apaga módulos de fábrica; POS_MODULES_ENABLED enciende los que vienen apagados."""
    try:
        disable = parse_module_names(env.get("POS_MODULES_DISABLED", ""))
        enable = parse_module_names(env.get("POS_MODULES_ENABLED", ""))
    except ValidationError as error:
        # Error de dominio: al abrir el programa sin consola, el mensaje se muestra tal cual en una ventana.
        message = f"Revise POS_MODULES_DISABLED / POS_MODULES_ENABLED en el .env: {error.message}"
        raise ValidationError(message) from None
    if env.get("POS_UPDATE_CHECK", "1").strip().lower() in ("0", "false", "no"):  # nombre anterior, se respeta
        disable.add(Module.UPDATES)
    modules = ModuleSet.configure(disable=disable, enable=enable)
    for module in enable - modules.enabled - disable:
        logger.warning("El módulo «%s» queda apagado porque necesita «%s»", module, modules.blocked_by(module))
    return modules


def _update_repository(env: Mapping[str, str]) -> str:
    """POS_UPDATE_REPO cambia el repositorio donde se buscan versiones nuevas (p. ej. una copia propia)."""
    return env.get("POS_UPDATE_REPO", "santyxswc/SistemaPOS").strip()
