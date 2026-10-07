"""Licencia de uso: consultar el estado, instalar un código y hacer cumplir el plan."""

from __future__ import annotations

import logging

from ...domain.licensing import License, LicenseStatus, evaluate_license
from ...domain.shared.errors import BusinessRuleViolation, ValidationError
from ...domain.users import Permission
from ..actor import Actor
from ..common import require_settings
from ..ports import Clock, LicenseVerifier, UnitOfWork, UnitOfWorkFactory

logger = logging.getLogger("pos.licensing")


class LicensePolicy:
    """Servicio de aplicación: lee la licencia guardada y decide qué permite hoy.

    Es el `UserQuota` de la instalación cuando el módulo de licencias está encendido.
    """

    def __init__(self, verifier: LicenseVerifier, clock: Clock) -> None:
        self._verifier = verifier
        self._clock = clock

    def status(self, uow: UnitOfWork) -> LicenseStatus:
        tz = require_settings(uow).tzinfo
        now = self._clock.now()
        installed_at = uow.licensing.get_installed_at() or now
        return evaluate_license(
            self._stored_license(uow),
            installed_on=installed_at.astimezone(tz).date(),
            today=now.astimezone(tz).date(),
        )

    def ensure_can_activate(self, uow: UnitOfWork) -> None:
        """Lanza BusinessRuleViolation si activar un usuario más excede lo que permite la licencia."""
        status = self.status(uow)
        limit = status.max_users
        if limit is None or uow.users.count(active_only=True) < limit:
            return
        users = f"{limit} usuario{'s' if limit != 1 else ''} activo{'s' if limit != 1 else ''}"
        if not status.is_valid:
            raise BusinessRuleViolation(f"{status.message} Mientras tanto se permite {users}.")
        raise BusinessRuleViolation(f"Su plan permite {users}: desactive uno o amplíe el plan con su proveedor")

    def _stored_license(self, uow: UnitOfWork) -> License | None:
        code = uow.licensing.get_code()
        if not code:
            return None
        try:
            return self._verifier.verify(code)
        except ValidationError:
            # Un código alterado a mano en la base de datos cuenta como si no hubiera licencia.
            logger.warning("La licencia guardada no tiene una firma válida; se ignora")
            return None


class GetLicenseStatus:
    def __init__(self, uow: UnitOfWorkFactory, policy: LicensePolicy) -> None:
        self._uow = uow
        self._policy = policy

    def execute(self) -> LicenseStatus:
        with self._uow(read_only=True) as uow:
            return self._policy.status(uow)


class InstallLicense:
    """Activa un código de licencia enviado por el proveedor."""

    def __init__(
        self, uow: UnitOfWorkFactory, verifier: LicenseVerifier, policy: LicensePolicy, clock: Clock
    ) -> None:
        self._uow = uow
        self._verifier = verifier
        self._policy = policy
        self._clock = clock

    def execute(self, actor: Actor, code: str) -> LicenseStatus:
        actor.require(Permission.MANAGE_SETTINGS)
        return self._install(code)

    def execute_from_console(self, code: str) -> LicenseStatus:
        """Para soporte en el computador del negocio (quien tiene la consola ya tiene los datos)."""
        return self._install(code)

    def _install(self, code: str) -> LicenseStatus:
        license = self._verifier.verify(code)
        with self._uow() as uow:
            today = self._clock.now().astimezone(require_settings(uow).tzinfo).date()
            if license.expires_on is not None and license.expires_on < today:
                raise BusinessRuleViolation(
                    f"Esta licencia venció el {license.expires_on:%d/%m/%Y}: pida a su proveedor una vigente"
                )
            uow.licensing.save_code("".join(code.split()))
            status = self._policy.status(uow)
            uow.commit()
        logger.info("Licencia %s instalada: plan %s para %s", license.license_id, license.plan, license.business_name)
        return status
