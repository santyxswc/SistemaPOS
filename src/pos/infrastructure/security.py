"""Contraseñas con PBKDF2 (biblioteca estándar) y sesiones con JWT firmados (HS256)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from uuid import UUID

import jwt

from ..application.ports import Clock
from ..domain.shared.errors import AuthenticationError
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
