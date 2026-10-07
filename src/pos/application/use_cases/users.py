"""Usuarios y autenticación."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.shared.errors import AuthenticationError, BusinessRuleViolation, ConflictError, NotFoundError
from ...domain.users import (
    EDITABLE_ROLES,
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    RolePermissions,
    User,
    normalize_username,
    validate_password,
)
from ..actor import Actor
from ..common import get_or_404, require_settings
from ..modules import Module, ModuleSet
from ..ports import Clock, LoginThrottle, PasswordHasher, TokenService, UnitOfWork, UnitOfWorkFactory, UserQuota

_INVALID_CREDENTIALS = "Usuario o contraseña incorrectos"


class NoUserLimit:
    """Objeto nulo de `UserQuota`: sin el módulo de licencias, el negocio crea los usuarios que quiera."""

    def ensure_can_activate(self, uow: UnitOfWork) -> None:
        return None


@dataclass(frozen=True)
class LoginResult:
    token: str
    expires_in: int
    user: User


class Login:
    def __init__(
        self, uow: UnitOfWorkFactory, hasher: PasswordHasher, tokens: TokenService, throttle: LoginThrottle
    ) -> None:
        self._uow = uow
        self._hasher = hasher
        self._tokens = tokens
        self._throttle = throttle
        self._dummy_hash: str | None = None

    def execute(self, username: str, password: str) -> LoginResult:
        key = normalize_username(username)
        self._throttle.check(key)
        with self._uow(read_only=True) as uow:
            user = uow.users.get_by_username(key)
        if user is None or not user.active:
            # Mismo trabajo exista o no el usuario: no se puede adivinar quién existe por el tiempo.
            self._hasher.verify(password, self._dummy())
            self._throttle.failed(key)
            raise AuthenticationError(_INVALID_CREDENTIALS)
        if not self._hasher.verify(password, user.password_hash):
            self._throttle.failed(key)
            raise AuthenticationError(_INVALID_CREDENTIALS)
        self._throttle.succeeded(key)
        return LoginResult(token=self._tokens.issue(user), expires_in=self._tokens.expires_in_seconds, user=user)

    def _dummy(self) -> str:
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash("contraseña-de-relleno")
        return self._dummy_hash


class ResolveActor:
    """Convierte un token en el usuario actual, verificando que siga activo.

    Sus permisos son los de su rol menos los de los módulos apagados: así ningún caso
    de uso de un módulo apagado se puede ejecutar, aunque alguien llame a la API a mano.
    """

    def __init__(self, uow: UnitOfWorkFactory, tokens: TokenService, modules: ModuleSet) -> None:
        self._uow = uow
        self._tokens = tokens
        self._modules = modules

    def execute(self, token: str) -> Actor:
        user_id = self._tokens.decode(token)
        with self._uow(read_only=True) as uow:
            user = uow.users.get(user_id)
            # Sin el módulo de permisos por rol rigen los de fábrica, aunque se hayan personalizado antes.
            policy = uow.roles.get() if self._modules.is_enabled(Module.ROLE_PERMISSIONS) else RolePermissions()
        if user is None or not user.active:
            raise AuthenticationError("Sesión no válida: inicie sesión de nuevo")
        return Actor.from_user(user, policy).limited_to(self._modules.available_permissions)


class BootstrapAdmin:
    """Crea el primer administrador. Solo funciona mientras no exista ningún usuario."""

    def __init__(self, uow: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock) -> None:
        self._uow = uow
        self._hasher = hasher
        self._clock = clock

    def execute(self, *, username: str, full_name: str, password: str) -> User:
        validate_password(password)
        password_hash = self._hasher.hash(password)  # fuera de la transacción: es lento a propósito
        with self._uow() as uow:
            if uow.users.count() > 0:
                raise ConflictError("Ya existen usuarios: cree los demás desde la cuenta de administrador")
            user = User(
                username=username,
                full_name=full_name,
                password_hash=password_hash,
                role=Role.ADMIN,
                created_at=self._clock.now(),
            )
            uow.users.add(user)
            uow.commit()
        return user


@dataclass(frozen=True)
class CreateUserCommand:
    username: str
    full_name: str
    password: str
    role: Role = Role.CASHIER


class CreateUser:
    def __init__(
        self, uow: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock, quota: UserQuota
    ) -> None:
        self._uow = uow
        self._hasher = hasher
        self._clock = clock
        self._quota = quota

    def execute(self, actor: Actor, command: CreateUserCommand) -> User:
        actor.require(Permission.MANAGE_USERS)
        validate_password(command.password)
        password_hash = self._hasher.hash(command.password)
        with self._uow() as uow:
            user = User(
                username=command.username,
                full_name=command.full_name,
                password_hash=password_hash,
                role=command.role,
                created_at=self._clock.now(),
            )
            if uow.users.get_by_username(user.username) is not None:
                raise ConflictError(f"El usuario «{user.username}» ya existe")
            self._quota.ensure_can_activate(uow)
            uow.users.add(user)
            uow.commit()
        return user


@dataclass(frozen=True)
class UpdateUserCommand:
    full_name: str | None = None
    role: Role | None = None
    active: bool | None = None
    password: str | None = None


class UpdateUser:
    def __init__(self, uow: UnitOfWorkFactory, hasher: PasswordHasher, quota: UserQuota) -> None:
        self._uow = uow
        self._hasher = hasher
        self._quota = quota

    def execute(self, actor: Actor, user_id: UUID, command: UpdateUserCommand) -> User:
        actor.require(Permission.MANAGE_USERS)
        password_hash = None
        if command.password is not None:
            validate_password(command.password)
            password_hash = self._hasher.hash(command.password)
        with self._uow() as uow:
            user = get_or_404(uow.users.get(user_id), "Usuario no encontrado")
            demoting_self = command.role is not None and command.role is not Role.ADMIN
            if user.id == actor.user_id and (command.active is False or demoting_self):
                raise BusinessRuleViolation("No puede desactivarse ni quitarse el rol de administrador a sí mismo")
            if command.active and not user.active:
                self._quota.ensure_can_activate(uow)
            user.update(
                full_name=command.full_name,
                role=command.role,
                active=command.active,
                password_hash=password_hash,
            )
            uow.users.save(user)
            uow.commit()
        return user


class ChangeOwnPassword:
    def __init__(self, uow: UnitOfWorkFactory, hasher: PasswordHasher) -> None:
        self._uow = uow
        self._hasher = hasher

    def execute(self, actor: Actor, current_password: str, new_password: str) -> None:
        validate_password(new_password)
        with self._uow(read_only=True) as uow:
            user = get_or_404(uow.users.get(actor.user_id), "Usuario no encontrado")
        if not self._hasher.verify(current_password, user.password_hash):
            raise AuthenticationError("La contraseña actual no es correcta")
        new_hash = self._hasher.hash(new_password)
        with self._uow() as uow:
            user = get_or_404(uow.users.get(actor.user_id), "Usuario no encontrado")
            user.update(password_hash=new_hash)
            uow.users.save(user)
            uow.commit()


class ResetPasswordFromConsole:
    """Recupera el acceso cuando el dueño olvida su contraseña.

    Solo se ofrece en la consola del computador del negocio, nunca por la API: quien
    puede ejecutar comandos en ese equipo ya tiene la base de datos en sus manos, así
    que no hay un permiso adicional que pedir. Reactiva la cuenta si estaba inactiva.
    """

    def __init__(self, uow: UnitOfWorkFactory, hasher: PasswordHasher, quota: UserQuota) -> None:
        self._uow = uow
        self._hasher = hasher
        self._quota = quota

    def execute(self, username: str, new_password: str) -> User:
        validate_password(new_password)
        password_hash = self._hasher.hash(new_password)
        with self._uow() as uow:
            user = uow.users.get_by_username(normalize_username(username))
            if user is None:
                admins = ", ".join(u.username for u in uow.users.list_all() if u.role is Role.ADMIN) or "ninguno"
                raise NotFoundError(f"No existe el usuario «{username}». Administradores registrados: {admins}")
            if not user.active:
                self._quota.ensure_can_activate(uow)
            user.update(password_hash=password_hash, active=True)
            uow.users.save(user)
            uow.commit()
        return user


class ListUsers:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor) -> list[User]:
        actor.require(Permission.MANAGE_USERS)
        with self._uow(read_only=True) as uow:
            return uow.users.list_all()


class GetSetupStatus:
    """Indica si falta la configuración inicial (todavía no hay ningún usuario)."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self) -> bool:
        with self._uow(read_only=True) as uow:
            return uow.users.count() == 0


@dataclass(frozen=True)
class InitialSetupCommand:
    business_name: str
    username: str
    full_name: str
    password: str


class CompleteInitialSetup:
    """Asistente de la primera vez: nombre del negocio y primer administrador, juntos o nada.

    Solo funciona mientras no exista ningún usuario; después, cualquier intento es un conflicto.
    """

    def __init__(self, uow: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock) -> None:
        self._uow = uow
        self._hasher = hasher
        self._clock = clock

    def execute(self, command: InitialSetupCommand) -> User:
        validate_password(command.password)
        password_hash = self._hasher.hash(command.password)
        with self._uow() as uow:
            if uow.users.count() > 0:
                raise ConflictError("El sistema ya está configurado: inicie sesión")
            settings = require_settings(uow).updated(business_name=command.business_name.strip())
            user = User(
                username=command.username,
                full_name=command.full_name,
                password_hash=password_hash,
                role=Role.ADMIN,
                created_at=self._clock.now(),
            )
            uow.settings.save(settings)
            uow.users.add(user)
            uow.commit()
        return user


class GetRolePermissions:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor) -> RolePermissions:
        actor.require(Permission.MANAGE_USERS)
        with self._uow(read_only=True) as uow:
            return uow.roles.get()


class UpdateRolePermissions:
    """Cambia lo que puede hacer un rol. Rige desde la siguiente acción de cada usuario."""

    def __init__(self, uow: UnitOfWorkFactory, modules: ModuleSet) -> None:
        self._uow = uow
        self._modules = modules

    def execute(self, actor: Actor, role: Role, permissions: set[Permission] | None) -> RolePermissions:
        """Con `permissions=None` el rol vuelve a los permisos de fábrica."""
        actor.require(Permission.MANAGE_USERS)
        self._modules.require(Module.ROLE_PERMISSIONS)
        if role not in EDITABLE_ROLES:
            raise BusinessRuleViolation(f"Los permisos del rol {ROLE_LABELS[role]} no se pueden cambiar")
        with self._uow() as uow:
            current = uow.roles.get()
            if permissions is None:
                granted = ROLE_PERMISSIONS[role]
            else:
                # La pantalla solo muestra los permisos de los módulos encendidos; los demás se conservan
                # como estaban, para que encender de nuevo un módulo no le quite nada a nadie.
                hidden = frozenset(Permission) - self._modules.available_permissions
                granted = (frozenset(permissions) - hidden) | (current.for_role(role) & hidden)
            policy = current.with_role(role, granted)
            uow.roles.save(policy)
            uow.commit()
        return policy
