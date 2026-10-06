"""Contraseñas con PBKDF2 (biblioteca estándar), sesiones con JWT firmados (HS256) y freno a la fuerza bruta."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import jwt

from ..application.ports import Clock
from ..domain.shared.errors import AuthenticationError, TooManyAttempts
from ..domain.users import User


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


class Pbkdf2PasswordHasher:
    """Formato guardado: pbkdf2_sha256$iteraciones$sal$hash (recomendación OWASP: 600.000)."""

    algorithm = "pbkdf2_sha256"

    def __init__(self, iterations: int = 600_000) -> None:
        if iterations < 1:
            raise ValueError("iterations debe ser positivo")
        self._iterations = iterations

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self._iterations)
        return f"{self.algorithm}${self._iterations}${_b64encode(salt)}${_b64encode(digest)}"

    def verify(self, password: str, hashed: str) -> bool:
        try:
            algorithm, iterations, salt, digest = hashed.split("$")
            expected = _b64decode(digest)
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _b64decode(salt), int(iterations))
        except (ValueError, TypeError):
            return False
        return algorithm == self.algorithm and hmac.compare_digest(candidate, expected)


class JwtTokenService:
    def __init__(self, secret: str, ttl_minutes: int, clock: Clock, issuer: str = "pos") -> None:
        self._secret = secret
        self._ttl = timedelta(minutes=ttl_minutes)
        self._clock = clock
        self._issuer = issuer

    @property
    def expires_in_seconds(self) -> int:
        return int(self._ttl.total_seconds())

    def issue(self, user: User) -> str:
        now = self._clock.now()
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
            "iss": self._issuer,
            "iat": now,
            "exp": now + self._ttl,
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def decode(self, token: str) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
            return UUID(payload["sub"])
        except (jwt.PyJWTError, ValueError, KeyError):
            raise AuthenticationError("Sesión no válida o vencida: inicie sesión de nuevo") from None


@dataclass
class _Attempts:
    failures: int
    first_failure: datetime
    locked_until: datetime | None = None


class InMemoryLoginThrottle:
    """Tras `max_failures` intentos fallidos seguidos, bloquea ese usuario por `lockout`.

    Vive en la memoria del proceso: suficiente para un servidor por negocio. Con
    varios servidores se reemplaza por una implementación compartida (p. ej. Redis).
    """

    def __init__(
        self,
        clock: Clock,
        *,
        max_failures: int = 5,
        window: timedelta = timedelta(minutes=15),
        lockout: timedelta = timedelta(minutes=5),
    ) -> None:
        self._clock = clock
        self._max_failures = max_failures
        self._window = window
        self._lockout = lockout
        self._attempts: dict[str, _Attempts] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = self._clock.now()
        with self._lock:
            attempts = self._attempts.get(key)
            if attempts is None or attempts.locked_until is None:
                return
            if now >= attempts.locked_until:
                del self._attempts[key]
                return
            minutes = max(1, -(-int((attempts.locked_until - now).total_seconds()) // 60))
        raise TooManyAttempts(f"Demasiados intentos fallidos: espere {minutes} min e intente de nuevo")

    def failed(self, key: str) -> None:
        now = self._clock.now()
        with self._lock:
            attempts = self._attempts.get(key)
            if attempts is None or now - attempts.first_failure > self._window:
                attempts = self._attempts[key] = _Attempts(failures=0, first_failure=now)
            attempts.failures += 1
            if attempts.failures >= self._max_failures:
                attempts.locked_until = now + self._lockout

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)
