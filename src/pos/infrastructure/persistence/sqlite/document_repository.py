"""Repositorio SQLite de la bandeja de salida de documentos electrónicos."""

from __future__ import annotations

import sqlite3
from collections.abc import Collection
from datetime import datetime
from typing import Any
from uuid import UUID

from ....domain.invoicing import DocumentKind, DocumentStatus, ElectronicDocument
from .repositories import Track, _dt, _placeholders, _ts


class SqliteElectronicDocumentRepository:
    def __init__(self, conn: sqlite3.Connection, track: Track) -> None:
        self._conn = conn
        self._track = track

    def add(self, document: ElectronicDocument) -> None:
        self._conn.execute(
            "INSERT INTO electronic_documents (id, sale_id, sale_number, kind, status, attempts, next_attempt_at, "
            "last_error, cufe, qr_data, provider_reference, accepted_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(document.id), str(document.sale_id), document.sale_number, document.kind.value,
             *self._mutable(document), _ts(document.created_at)),
        )
        self._track(document)

    def save(self, document: ElectronicDocument) -> None:
        self._conn.execute(
            "UPDATE electronic_documents SET status = ?, attempts = ?, next_attempt_at = ?, last_error = ?, "
            "cufe = ?, qr_data = ?, provider_reference = ?, accepted_at = ? WHERE id = ?",
            (*self._mutable(document), str(document.id)),
        )
        self._track(document)

    def get(self, document_id: UUID) -> ElectronicDocument | None:
        row = self._conn.execute("SELECT * FROM electronic_documents WHERE id = ?", (str(document_id),)).fetchone()
        return self._to_document(row) if row else None

    def list_for_sale(self, sale_id: UUID) -> list[ElectronicDocument]:
        rows = self._conn.execute(
            "SELECT * FROM electronic_documents WHERE sale_id = ? ORDER BY created_at", (str(sale_id),)
        ).fetchall()
        return [self._to_document(row) for row in rows]

    def list_due(self, now: datetime, *, limit: int) -> list[ElectronicDocument]:
        rows = self._conn.execute(
            "SELECT * FROM electronic_documents WHERE status = 'pending' AND next_attempt_at <= ? "
            "ORDER BY created_at, sale_number LIMIT ?",
            (_ts(now), limit),
        ).fetchall()
        return [self._to_document(row) for row in rows]

    def find(
        self, *, statuses: Collection[DocumentStatus] | None = None, limit: int = 50, offset: int = 0
    ) -> list[ElectronicDocument]:
        params: list[Any] = []
        where = ""
        if statuses:
            where = f"WHERE status IN ({_placeholders(len(statuses))})"
            params.extend(status.value for status in statuses)
        rows = self._conn.execute(
            f"SELECT * FROM electronic_documents {where} ORDER BY created_at DESC, sale_number DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._to_document(row) for row in rows]

    def count_by_status(self) -> dict[DocumentStatus, int]:
        counts = {status: 0 for status in DocumentStatus}
        for row in self._conn.execute("SELECT status, COUNT(*) AS n FROM electronic_documents GROUP BY status"):
            counts[DocumentStatus(row["status"])] = int(row["n"])
        return counts

    @staticmethod
    def _mutable(document: ElectronicDocument) -> tuple[Any, ...]:
        return (
            document.status.value,
            document.attempts,
            _ts(document.next_attempt_at),
            document.last_error,
            document.cufe,
            document.qr_data,
            document.provider_reference,
            _ts(document.accepted_at),
        )

    @staticmethod
    def _to_document(row: sqlite3.Row) -> ElectronicDocument:
        return ElectronicDocument(
            id=UUID(row["id"]),
            sale_id=UUID(row["sale_id"]),
            sale_number=row["sale_number"],
            kind=DocumentKind(row["kind"]),
            status=DocumentStatus(row["status"]),
            attempts=row["attempts"],
            next_attempt_at=_dt(row["next_attempt_at"]),
            last_error=row["last_error"],
            cufe=row["cufe"],
            qr_data=row["qr_data"],
            provider_reference=row["provider_reference"],
            accepted_at=_dt(row["accepted_at"]),
            created_at=_dt(row["created_at"]),
        )
