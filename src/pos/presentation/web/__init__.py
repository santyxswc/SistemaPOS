"""Interfaz web: sirve la aplicación compilada desde frontend/ en el mismo puerto que la API.

Así el computador del negocio solo necesita Python; Node solo se usa para compilar.
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, abort, send_from_directory

STATIC_DIR = Path(__file__).resolve().parent / "static"

_NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Punto de venta</title>
<body style="font-family:system-ui;max-width:640px;margin:10vh auto;padding:0 16px">
<h1>Falta compilar la interfaz</h1>
<p>Ejecute <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code> y recargue esta página.</p>
<p>La API sigue disponible en <code>/api/v1</code>.</p></body>"""


def register_web(app: Flask, static_dir: Path = STATIC_DIR) -> None:
    @app.get("/")
    @app.get("/<path:path>")
    def web(path: str = "") -> Response:
        if path.startswith("api/"):
            abort(404)
        if not (static_dir / "index.html").is_file():
            return Response(_NOT_BUILT, status=503, mimetype="text/html")
        if path and (static_dir / path).is_file():
            response = send_from_directory(static_dir, path)
            if path.startswith("assets/"):  # nombres con hash: se pueden guardar en caché para siempre
                response.cache_control.public = True
                response.cache_control.max_age = 31_536_000
            return response
        response = send_from_directory(static_dir, "index.html")
        response.cache_control.no_cache = True  # siempre la última versión después de actualizar
        return response
