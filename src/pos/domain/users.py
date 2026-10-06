"""Usuarios, roles y permisos."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .shared.entity import AggregateRoot
from .shared.errors import ValidationError
from .shared.values import parse_enum

_USERNAME = re.compile(r"[a-z0-9._-]{3,32}")
MIN_PASSWORD_LENGTH = 8


class Role(StrEnum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    CASHIER = "cashier"


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

# Único lugar donde se decide qué puede hacer cada rol.
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

    @property
    def permissions(self) -> frozenset[Permission]:
        return ROLE_PERMISSIONS[self.role] if self.active else frozenset()

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

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
