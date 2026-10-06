"""Configuración técnica desde variables de entorno.

Lo técnico (base de datos, llaves, puertos) vive aquí; lo del negocio (impuestos,
métodos de pago, usuarios del plan) vive en BusinessSettings y se cambia por la API.
"""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("pos.config")


def load_dotenv(path: str | Path = ".env") -> None:
    """Carga líneas KEY=VALUE de un archivo .env sin pisar variables ya definidas."""
    file = Path(path)
    if not file.is_file():
        return
    for raw_line in file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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
            secret = secrets.token_urlsafe(48)
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
        )
