"""Clases base para entidades (identidad propia) y raíces de agregado (registran eventos)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from .events import DomainEvent


def new_id() -> UUID:
    return uuid4()


@dataclass(kw_only=True, eq=False)
class Entity:
    """Dos entidades son iguales si tienen el mismo tipo e id, no los mismos datos."""

    id: UUID = field(default_factory=new_id)

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and other.id == self.id  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.id))


@dataclass(kw_only=True, eq=False)
class AggregateRoot(Entity):
    """Raíz de agregado: frontera de consistencia que se guarda completa y emite eventos."""

    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events
