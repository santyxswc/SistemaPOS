"""Quién ejecuta un caso de uso. La autorización vive en la aplicación, no en la API."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ..domain.shared.errors import PermissionDenied
from ..domain.users import PERMISSION_LABELS, Permission, Role, User


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    username: str
    full_name: str
    role: Role
    permissions: frozenset[Permission]

    @classmethod
    def from_user(cls, user: User) -> Actor:
        return cls(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            permissions=user.permissions,
        )

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise PermissionDenied(f"No tiene permiso para {PERMISSION_LABELS[permission]}")
