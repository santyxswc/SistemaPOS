"""Quién ejecuta un caso de uso. La autorización vive en la aplicación, no en la API."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from ..domain.shared.errors import PermissionDenied
from ..domain.users import DEFAULT_ROLE_PERMISSIONS, PERMISSION_LABELS, Permission, Role, RolePermissions, User


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    username: str
    full_name: str
    role: Role
    permissions: frozenset[Permission]

    @classmethod
    def from_user(cls, user: User, policy: RolePermissions = DEFAULT_ROLE_PERMISSIONS) -> Actor:
        return cls(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            permissions=user.permissions(policy),
        )

    def limited_to(self, available: frozenset[Permission]) -> Actor:
        """El mismo usuario sin los permisos de los módulos apagados en esta instalación."""
        return replace(self, permissions=self.permissions & available)

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise PermissionDenied(f"No tiene permiso para {PERMISSION_LABELS[permission]}")

    def require_any(self, *permissions: Permission) -> None:
        """Basta con uno de los permisos (p. ej. ver compras: quien recibe mercancía o quien paga)."""
        if not any(self.can(permission) for permission in permissions):
            self.require(permissions[0])
