"""Bus de eventos síncrono. Un fallo en una reacción nunca tumba la venta que ya se guardó."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from ..domain.shared.events import DomainEvent

logger = logging.getLogger("pos.events")

Handler = Callable[[Any], None]


class SyncEventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            for event_type, handlers in self._handlers.items():
                if not isinstance(event, event_type):
                    continue
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:  # noqa: BLE001 - se registra y se sigue
                        logger.exception("Falló el manejador %r con el evento %r", handler, event)
