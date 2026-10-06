"""Usuarios, roles y permisos."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from .shared.entity import AggregateRoot
from .shared.errors import ValidationError
from .shared.values import parse_enum

_USERNAME = re.compile(r"[a-z0-9._-]{3,32}")
MIN_PASSWORD_LENGTH = 8


class Role(StrEnum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    CASHIER = "cashier"


ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Administrador",
    Role.SUPERVISOR: "Supervisor",
    Role.CASHIER: "Cajero",
}


class Permission(StrEnum):
    MANAGE_USERS = "manage_users"
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_CATALOG = "manage_catalog"
    MANAGE_INVENTORY = "manage_inventory"
    MANAGE_SUPPLIERS = "manage_suppliers"
    SELL = "sell"
    APPLY_DISCOUNTS = "apply_discounts"
    VOID_SALES = "void_sales"
    OPERATE_CASH = "operate_cash"
    SUPERVISE_CASH = "supervise_cash"
    MANAGE_CUSTOMERS = "manage_customers"
    GRANT_CREDIT = "grant_credit"
    COLLECT_PAYMENTS = "collect_payments"
    VIEW_REPORTS = "view_reports"


PERMISSION_LABELS: dict[Permission, str] = {
    Permission.MANAGE_USERS: "administrar usuarios",
    Permission.MANAGE_SETTINGS: "cambiar la configuración del negocio",
    Permission.MANAGE_CATALOG: "administrar productos",
    Permission.MANAGE_INVENTORY: "administrar el inventario",
    Permission.MANAGE_SUPPLIERS: "administrar proveedores y pagarles",
    Permission.SELL: "vender",
    Permission.APPLY_DISCOUNTS: "aplicar descuentos",
    Permission.VOID_SALES: "anular ventas",
    Permission.OPERATE_CASH: "operar la caja",
    Permission.SUPERVISE_CASH: "supervisar las cajas de otros usuarios",
    Permission.MANAGE_CUSTOMERS: "administrar clientes",
    Permission.GRANT_CREDIT: "asignar cupos de crédito (fiado)",
    Permission.COLLECT_PAYMENTS: "recibir abonos de clientes",
    Permission.VIEW_REPORTS: "ver reportes",
}

_CASHIER = frozenset(
    {
        Permission.SELL,
        Permission.OPERATE_CASH,
        Permission.MANAGE_CUSTOMERS,
        Permission.COLLECT_PAYMENTS,
    }
)

# Permisos de fábrica de cada rol (el negocio puede cambiarlos en Usuarios → Permisos por rol).
# El supervisor (encargado del turno) corrige y controla, pero no cambia precios,
# usuarios ni la configuración del negocio.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.SUPERVISOR: _CASHIER
    | {
        Permission.APPLY_DISCOUNTS,
        Permission.VOID_SALES,
        Permission.SUPERVISE_CASH,
        Permission.GRANT_CREDIT,
        Permission.MANAGE_INVENTORY,
        Permission.VIEW_REPORTS,
    },
    Role.CASHIER: _CASHIER,
}


# Solo el administrador los tiene: con ellos cualquiera podría darse más permisos o crear otro administrador.
ADMIN_ONLY_PERMISSIONS = frozenset({Permission.MANAGE_USERS, Permission.MANAGE_SETTINGS})
EDITABLE_ROLES = (Role.SUPERVISOR, Role.CASHIER)
GRANTABLE_PERMISSIONS = tuple(p for p in Permission if p not in ADMIN_ONLY_PERMISSIONS)


@dataclass(frozen=True)
class RolePermissions:
    """Qué puede hacer cada rol en este negocio.

    El administrador siempre lo puede todo (así nadie queda por fuera del sistema).
    Los roles que el negocio no ha personalizado usan los permisos de fábrica.
    """

    granted: Mapping[Role, frozenset[Permission]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cleaned: dict[Role, frozenset[Permission]] = {}
        for role, permissions in self.granted.items():
            role = parse_enum(Role, role, "rol")
            if role not in EDITABLE_ROLES:
                raise ValidationError(f"Los permisos del rol {ROLE_LABELS[role]} no se pueden cambiar")
            perms = frozenset(parse_enum(Permission, p, "permiso") for p in permissions)
            reserved = perms & ADMIN_ONLY_PERMISSIONS
            if reserved:
                labels = ", ".join(sorted(PERMISSION_LABELS[p] for p in reserved))
                raise ValidationError(f"Solo el administrador puede {labels}")
            cleaned[role] = perms
        object.__setattr__(self, "granted", MappingProxyType(cleaned))

    def for_role(self, role: Role) -> frozenset[Permission]:
        if role is Role.ADMIN:
            return frozenset(Permission)
        return self.granted.get(role, ROLE_PERMISSIONS[role])

    def is_customized(self, role: Role) -> bool:
        return role in self.granted and self.granted[role] != ROLE_PERMISSIONS[role]

    def with_role(self, role: Role, permissions: Iterable[Permission | str]) -> RolePermissions:
        return RolePermissions({**self.granted, role: frozenset(permissions)})  # type: ignore[arg-type]


DEFAULT_ROLE_PERMISSIONS = RolePermissions()


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres")
    if len(password) > 128:
        raise ValidationError("La contraseña es demasiado larga")


@dataclass(kw_only=True, eq=False)
class User(AggregateRoot):
    username: str
    full_name: str
    password_hash: str
    created_at: datetime
    role: Role = Role.CASHIER
    active: bool = True

    def __post_init__(self) -> None:
        self.username = normalize_username(self.username)
        if not _USERNAME.fullmatch(self.username):
            raise ValidationError(
                "El usuario debe tener de 3 a 32 caracteres: letras minúsculas, "
                "números, punto, guion o guion bajo"
            )
        self.full_name = (self.full_name or "").strip()
        if not self.full_name:
            raise ValidationError("El nombre completo es obligatorio")
        self.role = parse_enum(Role, self.role, "rol")

    def permissions(self, policy: RolePermissions = DEFAULT_ROLE_PERMISSIONS) -> frozenset[Permission]:
        return policy.for_role(self.role) if self.active else frozenset()

    def update(
        self,
        *,
        full_name: str | None = None,
        role: Role | None = None,
        active: bool | None = None,
        password_hash: str | None = None,
    ) -> None:
        if full_name is not None:
            cleaned = full_name.strip()
            if not cleaned:
                raise ValidationError("El nombre completo es obligatorio")
            self.full_name = cleaned
        if role is not None:
            self.role = parse_enum(Role, role, "rol")
        if active is not None:
            self.active = active
        if password_hash is not None:
            self.password_hash = password_hash
