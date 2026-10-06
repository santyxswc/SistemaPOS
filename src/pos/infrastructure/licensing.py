"""Códigos de licencia firmados con Ed25519.

Formato: ``POS1.<datos>.<firma>`` (base64 URL, sin relleno). Es texto corto que el
proveedor puede enviar por correo o WhatsApp y el negocio pega en Ajustes.

- El proveedor firma con su clave privada, que nunca sale de su computador
  (ver packaging/licencia.py).
- El programa solo trae la clave pública: puede comprobar una licencia, pero no
  fabricarla. Cambiar un número del código invalida la firma.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import date
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..domain.licensing import License
from ..domain.shared.errors import ValidationError

PREFIX = "POS1"
_INVALID = "El código de licencia no es válido. Cópielo completo, tal como se lo enviaron."


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _payload(license: License) -> dict[str, Any]:
    return {
        "id": license.license_id,
        "business": license.business_name,
        "plan": license.plan,
        "max_users": license.max_users,
        "issued": license.issued_on.isoformat(),
        "expires": license.expires_on.isoformat() if license.expires_on else None,
    }


def _from_payload(data: dict[str, Any]) -> License:
    expires = data.get("expires")
    return License(
        license_id=str(data["id"]),
        business_name=str(data["business"]),
        plan=str(data["plan"]),
        max_users=None if data.get("max_users") is None else int(data["max_users"]),
        issued_on=date.fromisoformat(data["issued"]),
        expires_on=date.fromisoformat(expires) if expires else None,
    )


def sign_license(license: License, private_key: Ed25519PrivateKey) -> str:
    """Emite el código de una licencia. Solo lo usa el proveedor, nunca el programa del negocio."""
    data = json.dumps(_payload(license), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"{PREFIX}.{_b64encode(data)}.{_b64encode(private_key.sign(data))}"


def public_key_text(private_key: Ed25519PrivateKey) -> str:
    """La clave pública en el formato que espera Ed25519LicenseVerifier."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    return _b64encode(private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


class Ed25519LicenseVerifier:
    def __init__(self, public_key: str) -> None:
        self._key = Ed25519PublicKey.from_public_bytes(_b64decode(public_key))

    def verify(self, code: str) -> License:
        compact = re.sub(r"\s+", "", code or "")  # los chats a veces parten el código en varias líneas
        parts = compact.split(".")
        if len(parts) != 3 or parts[0] != PREFIX:
            raise ValidationError(_INVALID)
        try:
            data = _b64decode(parts[1])
            self._key.verify(_b64decode(parts[2]), data)
            return _from_payload(json.loads(data))
        except (InvalidSignature, binascii.Error, ValueError, KeyError, TypeError):
            raise ValidationError(_INVALID) from None
