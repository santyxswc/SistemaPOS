"""Facturación electrónica: bandeja de salida, envío al proveedor, reintentos y revisión.

La venta nunca espera al proveedor: queda registrada con su documento pendiente y un
proceso en segundo plano lo envía. Las llamadas al proveedor se hacen fuera de las
transacciones de escritura para no frenar a las cajas mientras responde.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from ...domain.invoicing import (
    DocumentKind,
    DocumentStatus,
    ElectronicDocument,
    InvoiceRejected,
    IssuedDocument,
)
from ...domain.sales import Sale
from ...domain.settings import BusinessSettings
from ...domain.users import Permission
from ..actor import Actor
from ..common import get_or_404, page_size, require_settings
from ..ports import Clock, InvoiceProvider, UnitOfWork, UnitOfWorkFactory

logger = logging.getLogger("pos.invoicing")

WAIT_FOR_INVOICE = timedelta(minutes=2)


class InvoiceOutbox(Protocol):
    """Deja los documentos de una venta en la bandeja, dentro de la transacción de la venta."""

    def enqueue_sale(self, uow: UnitOfWork, sale: Sale) -> None: ...

    def enqueue_void(self, uow: UnitOfWork, sale: Sale) -> None: ...


class DisabledInvoiceOutbox:
    """Objeto nulo: el negocio no emite documentos electrónicos y las ventas no cambian."""

    def enqueue_sale(self, uow: UnitOfWork, sale: Sale) -> None:
        return None

    def enqueue_void(self, uow: UnitOfWork, sale: Sale) -> None:
        return None


class TransactionalInvoiceOutbox:
    def enqueue_sale(self, uow: UnitOfWork, sale: Sale) -> None:
        uow.documents.add(
            ElectronicDocument.enqueue(
                sale_id=sale.id, sale_number=sale.number, kind=DocumentKind.INVOICE, at=sale.created_at
            )
        )

    def enqueue_void(self, uow: UnitOfWork, sale: Sale) -> None:
        # Solo las ventas que tienen documento necesitan la nota crédito que lo anula
        # (las de antes de activar la facturación no tienen nada que anular).
        if not any(doc.kind is DocumentKind.INVOICE for doc in uow.documents.list_for_sale(sale.id)):
            return
        assert sale.voided_at is not None
        uow.documents.add(
            ElectronicDocument.enqueue(
                sale_id=sale.id, sale_number=sale.number, kind=DocumentKind.CREDIT_NOTE, at=sale.voided_at
            )
        )


@dataclass(frozen=True)
class OutboxRun:
    accepted: int = 0
    failed: int = 0
    rejected: int = 0
    postponed: int = 0


class ProcessInvoiceOutbox:
    """Envía los documentos pendientes cuyo turno llegó. Lo ejecuta el proceso en segundo plano."""

    def __init__(self, uow: UnitOfWorkFactory, provider: InvoiceProvider, clock: Clock) -> None:
        self._uow = uow
        self._provider = provider
        self._clock = clock

    def execute(self, limit: int = 20) -> OutboxRun:
        with self._uow(read_only=True) as uow:
            due = uow.documents.list_due(self._clock.now(), limit=limit)
            settings = require_settings(uow) if due else None
        totals = {"accepted": 0, "failed": 0, "rejected": 0, "postponed": 0}
        for document in due:
            assert settings is not None
            totals[self._process(document, settings)] += 1
        return OutboxRun(**totals)

    def _process(self, document: ElectronicDocument, settings: BusinessSettings) -> str:
        with self._uow(read_only=True) as uow:
            sale = uow.sales.get(document.sale_id)
            siblings = uow.documents.list_for_sale(document.sale_id)
        if document.kind is DocumentKind.CREDIT_NOTE:
            invoice = next((d for d in siblings if d.kind is DocumentKind.INVOICE), None)
            if invoice is None or invoice.status is not DocumentStatus.ACCEPTED:
                return self._record(document.id, "postponed", "Esperando que se acepte el documento de la venta")

        issued: IssuedDocument | None = None
        outcome, message = "accepted", ""
        try:
            if sale is None:
                raise InvoiceRejected("La venta del documento no existe")
            issued = self._provider.issue(document, sale, settings)
        except InvoiceRejected as error:
            outcome, message = "rejected", error.message
            logger.warning("Documento de la venta #%s rechazado: %s", document.sale_number, message)
        except Exception as error:  # noqa: BLE001 - toda otra falla se reintenta
            outcome, message = "failed", str(error) or type(error).__name__
            logger.warning("No se pudo enviar el documento de la venta #%s: %s", document.sale_number, message)
        return self._record(document.id, outcome, message, issued)

    def _record(self, document_id: UUID, outcome: str, message: str, issued: IssuedDocument | None = None) -> str:
        now = self._clock.now()
        with self._uow() as uow:
            document = uow.documents.get(document_id)
            if document is None or document.status is not DocumentStatus.PENDING:
                return outcome  # alguien lo atendió mientras se enviaba
            if outcome == "accepted":
                assert issued is not None
                document.mark_accepted(issued, at=now)
            elif outcome == "rejected":
                document.mark_rejected(message, at=now)
            elif outcome == "postponed":
                document.postpone(until=now + WAIT_FOR_INVOICE, reason=message)
            else:
                document.mark_failed(message, at=now)
            uow.documents.save(document)
            uow.commit()
        return outcome


@dataclass(frozen=True)
class InvoicingStatus:
    enabled: bool
    provider: str | None
    counts: dict[DocumentStatus, int]

    @property
    def needs_attention(self) -> int:
        return self.counts[DocumentStatus.FAILED] + self.counts[DocumentStatus.REJECTED]


class GetInvoicingStatus:
    def __init__(self, uow: UnitOfWorkFactory, provider: InvoiceProvider | None) -> None:
        self._uow = uow
        self._provider = provider

    def execute(self, actor: Actor) -> InvoicingStatus:
        actor.require(Permission.VIEW_REPORTS)
        with self._uow(read_only=True) as uow:
            counts = uow.documents.count_by_status()
        return InvoicingStatus(
            enabled=self._provider is not None,
            provider=self._provider.name if self._provider else None,
            counts=counts,
        )


class ListElectronicDocuments:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(
        self, actor: Actor, *, statuses: Collection[DocumentStatus] | None = None, limit: int = 50, offset: int = 0
    ) -> list[ElectronicDocument]:
        actor.require(Permission.VIEW_REPORTS)
        with self._uow(read_only=True) as uow:
            return uow.documents.find(statuses=statuses, limit=page_size(limit), offset=max(0, offset))


class RetryElectronicDocument:
    """Vuelve a poner en la bandeja un documento rechazado o que agotó sus reintentos."""

    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: Actor, document_id: UUID) -> ElectronicDocument:
        actor.require(Permission.MANAGE_SETTINGS)
        with self._uow() as uow:
            document = get_or_404(uow.documents.get(document_id), "Documento no encontrado")
            document.retry(at=self._clock.now())
            uow.documents.save(document)
            uow.commit()
        return document
