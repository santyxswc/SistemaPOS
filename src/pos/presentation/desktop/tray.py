"""Ícono junto al reloj de Windows con el menú del punto de venta.

El menú se describe con objetos simples (probables sin pantalla); pystray solo se
importa al mostrarlo, así el resto del sistema no depende de esa librería.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("pos.tray")


@dataclass(frozen=True)
class TrayActions:
    open_app: Callable[[], None]
    backup_now: Callable[[], str]  # devuelve el mensaje para mostrar al terminar
    open_data_folder: Callable[[], None]
    quit: Callable[[], None]
    update_message: Callable[[], str | None] = lambda: None  # "Hay una versión nueva: 0.4.0" (consulta internet)


@dataclass(frozen=True)
class MenuEntry:
    label: str
    action: Callable[[], None] | None = None  # None = separador
    default: bool = False  # doble clic en el ícono


def menu_entries(actions: TrayActions, notify: Callable[[str], None]) -> list[MenuEntry]:
    def backup() -> None:
        # En otro hilo: el menú no se congela mientras se copia la base de datos.
        def run() -> None:
            try:
                notify(actions.backup_now())
            except Exception as error:  # noqa: BLE001 - el aviso explica el problema al usuario
                logger.exception("Falló el respaldo desde el ícono")
                notify(f"No se pudo hacer el respaldo: {error}")

        threading.Thread(target=run, name="respaldo", daemon=True).start()

    return [
        MenuEntry("Abrir el punto de venta", actions.open_app, default=True),
        MenuEntry("Respaldar ahora", backup),
        MenuEntry("Abrir la carpeta de datos", actions.open_data_folder),
        MenuEntry("-"),
        MenuEntry("Apagar el punto de venta", actions.quit),
    ]


def announce_update(actions: TrayActions, notify: Callable[[str], None]) -> None:
    """Pregunta por versiones nuevas sin frenar el arranque y avisa con un globo si hay una."""
    try:
        message = actions.update_message()
    except Exception:  # noqa: BLE001 - sin internet no hay nada que avisar
        logger.info("No se pudo consultar si hay una versión nueva", exc_info=True)
        return
    if message:
        notify(message)


class TrayIcon:
    """Muestra el ícono y bloquea hasta que el usuario elige "Apagar"."""

    def __init__(self, title: str, actions: TrayActions) -> None:
        self._title = title
        self._actions = actions
        self._icon = None

    def notify(self, message: str) -> None:
        if self._icon is not None:
            try:
                self._icon.notify(message, self._title)
            except Exception:  # noqa: BLE001 - un globo que no sale no es grave
                logger.info("No se pudo mostrar el aviso: %s", message)

    def run(self, on_ready: Callable[[], None] | None = None) -> None:
        import pystray

        from .icon import draw_icon

        def item(entry: MenuEntry):  # noqa: ANN202
            if entry.action is None:
                return pystray.Menu.SEPARATOR
            action = entry.action
            return pystray.MenuItem(entry.label, lambda _icon, _item: action(), default=entry.default)

        def quit_app() -> None:
            self._actions.quit()
            self.stop()

        actions = TrayActions(
            open_app=self._actions.open_app,
            backup_now=self._actions.backup_now,
            open_data_folder=self._actions.open_data_folder,
            quit=quit_app,
            update_message=self._actions.update_message,
        )
        menu = pystray.Menu(*(item(entry) for entry in menu_entries(actions, self.notify)))
        self._icon = pystray.Icon("PuntoDeVenta", draw_icon(64), self._title, menu)

        def setup(icon) -> None:  # noqa: ANN001
            icon.visible = True
            threading.Thread(target=announce_update, args=(actions, self.notify), daemon=True).start()
            if on_ready:
                on_ready()

        self._icon.run(setup=setup)

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
