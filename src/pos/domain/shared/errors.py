"""Errores de dominio.

Expresan reglas de negocio violadas con mensajes que el usuario final entiende.
No saben nada de HTTP: la capa de presentación decide qué código devolver.
"""


class DomainError(Exception):
    """Base de todos los errores esperados del sistema."""

    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(DomainError):
    """Un dato no tiene el formato o el rango esperado."""

    code = "validation_error"


class NotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    """La operación choca con el estado actual (duplicados, caja ya abierta...)."""

    code = "conflict"


class BusinessRuleViolation(DomainError):
    """Las reglas del negocio no permiten la operación."""

    code = "business_rule_violation"


class InsufficientStock(BusinessRuleViolation):
    code = "insufficient_stock"


class CreditLimitExceeded(BusinessRuleViolation):
    code = "credit_limit_exceeded"


class AuthenticationError(DomainError):
    code = "authentication_failed"


class TooManyAttempts(DomainError):
    code = "too_many_attempts"


class PermissionDenied(DomainError):
    code = "permission_denied"
