"""Tareas en segundo plano dentro del mismo proceso del servidor.

Un hilo por tarea que se ejecuta cada cierto tiempo o apenas alguien lo despierta
(p. ej. al quedar un documento en la bandeja). Un error en la tarea se registra y el
hilo sigue vivo: nunca tumba el servidor ni las ventas.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger("pos.background")


class PeriodicWorker:
    def __init__(self, name: str, job: Callable[[], object], interval_seconds: float = 60.0) -> None:
        self.name = name
        self._job = job
        self._interval = interval_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=self.name, daemon=True)
        self._thread.start()
        logger.info("Tarea en segundo plano iniciada: %s", self.name)

    def wake(self) -> None:
        """Pide una ejecución inmediata (si el hilo no está corriendo no pasa nada)."""
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def run_once(self) -> None:
        try:
            self._job()
        except Exception:  # noqa: BLE001 - se registra y se intenta en la siguiente vuelta
            logger.exception("Falló la tarea en segundo plano %s", self.name)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._wake.wait(self._interval)
            self._wake.clear()
