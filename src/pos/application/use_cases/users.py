"""Usuarios y autenticación."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.shared.errors import AuthenticationError, BusinessRuleViolation, ConflictError
from ...domain.users import Permission, Role, User, normalize_username, validate_password
from ..actor import Actor
from ..common import get_or_404, require_settings
from ..ports import Clock, LoginThrottle, PasswordHasher, TokenService, UnitOfWork, UnitOfWorkFactory

_INVALID_CREDENTIALS = "Usuario o contraseña incorrectos"


def _ensure_user_quota(uow: UnitOfWork, max_users: int | None) -> None:
    if max_users is not None and uow.users.count(active_only=True) >= max_users:
        raise BusinessRuleViolation(
            f"El plan permite hasta {max_users} usuarios activos: desactive uno o amplíe el plan"
        )


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
    """Convierte un token en el usuario actual, verificando que siga activo."""

    def __init__(self, uow: UnitOfWorkFactory, tokens: TokenService) -> None:
        self._uow = uow
        self._tokens = tokens

    def execute(self, token: str) -> Actor:
        user_id = self._tokens.decode(token)
        with self._uow(read_only=True) as uow:
            user = uow.users.get(user_id)
        if user is None or not user.active:
            raise AuthenticationError("Sesión no válida: inicie sesión de nuevo")
        return Actor.from_user(user)


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
    def __init__(self, uow: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock) -> None:
        self._uow = uow
        self._hasher = hasher
        self._clock = clock

    def execute(self, actor: Actor, command: CreateUserCommand) -> User:
        actor.require(Permission.MANAGE_USERS)
        validate_password(command.password)
        password_hash = self._hasher.hash(command.password)
        with self._uow() as uow:
            settings = require_settings(uow)
            user = User(
                username=command.username,
                full_name=command.full_name,
                password_hash=password_hash,
                role=command.role,
                created_at=self._clock.now(),
            )
            if uow.users.get_by_username(user.username) is not None:
                raise ConflictError(f"El usuario «{user.username}» ya existe")
            _ensure_user_quota(uow, settings.max_users)
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
    def __init__(self, uow: UnitOfWorkFactory, hasher: PasswordHasher) -> None:
        self._uow = uow
        self._hasher = hasher

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
                _ensure_user_quota(uow, require_settings(uow).max_users)
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


class ListUsers:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, actor: Actor) -> list[User]:
        actor.require(Permission.MANAGE_USERS)
        with self._uow(read_only=True) as uow:
            return uow.users.list_all()
