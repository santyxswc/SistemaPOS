#!/usr/bin/env python3
"""Comandos de administración del POS desde el código fuente (ver src/pos/cli.py).

    python manage.py start            inicia el sistema y abre el navegador
    python manage.py init             instalación desde la consola
    python manage.py runserver        inicia solo el servidor (POS_ENV=development para desarrollo)
    python manage.py backup           copia de seguridad de la base de datos
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from pos.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
