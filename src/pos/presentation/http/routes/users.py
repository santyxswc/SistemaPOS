from __future__ import annotations

from uuid import UUID

from flask import Blueprint

from ....application.use_cases.users import CreateUserCommand, UpdateUserCommand
from ....domain.shared.values import parse_enum
from ....domain.users import Permission, Role
from .. import presenters
from ..context import authenticated, container, current_actor
from ..request import Body

bp = Blueprint("users", __name__)


@bp.get("/users")
@authenticated
def list_users():
    return {"items": [presenters.user(u) for u in container().list_users.execute(current_actor())]}


@bp.post("/users")
@authenticated
def create_user():
    body = Body.from_request()
    command = CreateUserCommand(
        username=body.text("username"),
        full_name=body.text("full_name"),
        password=body.text("password"),
        role=parse_enum(Role, body.text("role", required=False, default="cashier"), "rol"),
    )
    return presenters.user(container().create_user.execute(current_actor(), command)), 201


@bp.patch("/users/<uuid:user_id>")
@authenticated
def update_user(user_id: UUID):
    body = Body.from_request()
    body.reject_unknown({"full_name", "role", "active", "password"})
    role = body.text("role", required=False)
    command = UpdateUserCommand(
        full_name=body.text("full_name", required=False),
        role=parse_enum(Role, role, "rol") if role is not None else None,
        active=body.boolean("active"),
        password=body.text("password", required=False),
    )
    return presenters.user(container().update_user.execute(current_actor(), user_id, command))


@bp.get("/roles")
@authenticated
def get_roles():
    policy = container().get_role_permissions.execute(current_actor())
    return presenters.role_permissions(policy, container().modules.available_permissions)


@bp.put("/roles/<role>")
@authenticated
def update_role(role: str):
    """Cuerpo: {"permissions": [...]} o {"reset": true} para volver a los permisos de fábrica."""
    body = Body.from_request()
    body.reject_unknown({"permissions", "reset"})
    permissions = None
    if not body.boolean("reset", default=False):
        permissions = {parse_enum(Permission, code, "permiso") for code in body.strings("permissions")}
    policy = container().update_role_permissions.execute(current_actor(), parse_enum(Role, role, "rol"), permissions)
    return presenters.role_permissions(policy, container().modules.available_permissions)
