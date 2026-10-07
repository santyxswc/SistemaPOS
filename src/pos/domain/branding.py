"""Imagen del negocio: el logo que se muestra en el menú, al iniciar sesión y en el tiquete."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .shared.errors import ValidationError

MAX_LOGO_BYTES = 1024 * 1024

# Se reconoce el formato por los primeros bytes, no por el nombre del archivo. SVG no se
# acepta a propósito: puede llevar código que el navegador ejecutaría.
_SIGNATURES: tuple[tuple[str, bytes, int], ...] = (
    ("image/png", b"\x89PNG\r\n\x1a\n", 0),
    ("image/jpeg", b"\xff\xd8\xff", 0),
    ("image/webp", b"WEBP", 8),
)


def _detect_content_type(data: bytes) -> str | None:
    for content_type, signature, offset in _SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            if content_type == "image/webp" and not data.startswith(b"RIFF"):
                continue
            return content_type
    return None


@dataclass(frozen=True)
class Logo:
    content_type: str
    data: bytes
    updated_at: datetime

    @classmethod
    def from_upload(cls, data: bytes, now: datetime) -> Logo:
        if not data:
            raise ValidationError("El archivo del logo está vacío")
        if len(data) > MAX_LOGO_BYTES:
            raise ValidationError("El logo pesa más de 1 MB: guárdelo más pequeño (500 píxeles de ancho bastan)")
        content_type = _detect_content_type(data)
        if content_type is None:
            raise ValidationError("El logo debe ser una imagen PNG, JPG o WebP")
        return cls(content_type=content_type, data=data, updated_at=now)

    @property
    def version(self) -> str:
        """Cambia con cada logo nuevo: el navegador puede guardar la imagen sin preguntar de nuevo."""
        return str(int(self.updated_at.timestamp()))
