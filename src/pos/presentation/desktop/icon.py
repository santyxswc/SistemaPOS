"""Ícono del programa dibujado con código: el mismo para el ícono del reloj, el .exe y el instalador."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

GREEN = (31, 111, 92, 255)  # el --primary de la interfaz
WHITE = (255, 255, 255, 255)
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def draw_icon(size: int = 256) -> Image:
    """Caja registradora blanca sobre un cuadro verde redondeado."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size / 64
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(12 * s), fill=GREEN)
    draw.rounded_rectangle((14 * s, 12 * s, 50 * s, 26 * s), radius=int(2 * s), fill=WHITE)  # pantalla
    draw.rectangle((18 * s, 16 * s, 46 * s, 22 * s), fill=GREEN)
    draw.rectangle((29 * s, 26 * s, 35 * s, 31 * s), fill=WHITE)  # cuello
    draw.rounded_rectangle((8 * s, 31 * s, 56 * s, 54 * s), radius=int(3 * s), fill=WHITE)  # cuerpo
    for row in range(2):  # teclas
        for col in range(4):
            x = 13 + col * 10
            y = 35 + row * 7
            draw.rectangle((x * s, y * s, (x + 6) * s, (y + 4) * s), fill=GREEN)
    draw.rectangle((13 * s, 49 * s, 51 * s, 51 * s), fill=GREEN)  # cajón
    return image


def write_ico(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    draw_icon(256).save(target, format="ICO", sizes=ICO_SIZES)
    return target
