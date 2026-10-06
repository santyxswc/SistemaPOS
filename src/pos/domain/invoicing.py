"""Documentos electrónicos (DIAN) en una bandeja de salida.

Cada venta deja su documento pendiente en la misma transacción de la venta (patrón
*outbox*): si el proveedor tecnológico no responde, se cae internet o se apaga el
computador, el documento no se pierde. Un proceso en segundo plano lo envía y, si
falla, lo reintenta cada vez más espaciado. Lo que el proveedor rechaza por un error
en los datos se queda quieto hasta que una persona lo revise: reintentarlo igual
solo lo volvería a rechazar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from .shared.entity import AggregateRoot
from .shared.errors import BusinessRuleViolation, DomainError
from .shared.events import DomainEvent

# Espera antes de cada reintento automático. Después del último, el documento queda
# como "falló" y el administrador lo ve en Ajustes para reintentarlo a mano.
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=3),
    timedelta(hours=6),
    timedelta(hours=12),
)
MAX_ERROR_LENGTH = 500


class InvoiceRejected(DomainError):
    """El proveedor o la DIAN rechazó el documento por sus datos: reintentarlo no sirve."""

    code = "invoice_rejected"


class DocumentKind(StrEnum):
    INVOICE = "invoice"  # documento equivalente electrónico del tiquete POS
    CREDIT_NOTE = "credit_note"  # anula el documento de una venta anulada


class DocumentStatus(StrEnum):
    PENDING = "pending"  # en la bandeja: se enviará o reintentará solo
    ACCEPTED = "accepted"
    REJECTED = "rejected"  # requiere revisar los datos
    FAILED = "failed"  # se agotaron los reintentos automáticos


@dataclass(frozen=True, kw_only=True)
class DocumentQueued(DomainEvent):
    """Hay un documento listo para enviar: despierta al proceso de envío sin esperar su próxima vuelta."""

    document_id: UUID


@dataclass(frozen=True, kw_only=True)
class IssuedDocument:
    """Lo que devuelve el proveedor cuando acepta el documento."""

    cufe: str  # código único que identifica el documento ante la DIAN
    qr_data: str = ""  # contenido del código QR que va impreso en el tiquete
    reference: str = ""  # identificador del documento en el sistema del proveedor


@dataclass(kw_only=True, eq=False)
class ElectronicDocument(AggregateRoot):
    sale_id: UUID
    sale_number: int
    kind: DocumentKind
    created_at: datetime
    status: DocumentStatus = DocumentStatus.PENDING
    attempts: int = 0
    next_attempt_at: datetime | None = None
    last_error: str = ""
    cufe: str | None = None
    qr_data: str = ""
    provider_reference: str = ""
    accepted_at: datetime | None = None

    @classmethod
    def enqueue(cls, *, sale_id: UUID, sale_number: int, kind: DocumentKind, at: datetime) -> ElectronicDocument:
        document = cls(sale_id=sale_id, sale_number=sale_number, kind=kind, created_at=at, next_attempt_at=at)
        document.record(DocumentQueued(occurred_at=at, document_id=document.id))
        return document

    def is_due(self, now: datetime) -> bool:
        pending = self.status is DocumentStatus.PENDING
        return pending and self.next_attempt_at is not None and self.next_attempt_at <= now

    def mark_accepted(self, issued: IssuedDocument, *, at: datetime) -> None:
        self._ensure_pending()
        self.status = DocumentStatus.ACCEPTED
        self.attempts += 1
        self.cufe = issued.cufe
        self.qr_data = issued.qr_data
        self.provider_reference = issued.reference
        self.accepted_at = at
        self.next_attempt_at = None
        self.last_error = ""

    def mark_failed(self, error: str, *, at: datetime) -> None:
        """Falla temporal (sin conexión, proveedor caído): se programa otro intento."""
        self._ensure_pending()
        self.last_error = (error or "Error desconocido")[:MAX_ERROR_LENGTH]
        self.attempts += 1
        if self.attempts > len(RETRY_DELAYS):
            self.status = DocumentStatus.FAILED
            self.next_attempt_at = None
        else:
            self.next_attempt_at = at + RETRY_DELAYS[self.attempts - 1]

    def mark_rejected(self, reason: str, *, at: datetime) -> None:
        self._ensure_pending()
        self.status = DocumentStatus.REJECTED
        self.attempts += 1
        self.last_error = (reason or "Rechazado sin motivo")[:MAX_ERROR_LENGTH]
        self.next_attempt_at = None

    def postpone(self, *, until: datetime, reason: str) -> None:
        """Espera sin gastar un intento (p. ej. la nota crédito espera a que se acepte el documento de la venta)."""
        self._ensure_pending()
        self.next_attempt_at = until
        self.last_error = reason

    def retry(self, *, at: datetime) -> None:
        """Reintento manual después de revisar el problema: vuelve a la bandeja con intentos nuevos."""
        if self.status not in (DocumentStatus.FAILED, DocumentStatus.REJECTED):
            raise BusinessRuleViolation("Solo se reintentan documentos rechazados o que fallaron")
        self.status = DocumentStatus.PENDING
        self.attempts = 0
        self.next_attempt_at = at
        self.record(DocumentQueued(occurred_at=at, document_id=self.id))

    def _ensure_pending(self) -> None:
        if self.status is not DocumentStatus.PENDING:
            raise BusinessRuleViolation("El documento ya no está en la bandeja de salida")
