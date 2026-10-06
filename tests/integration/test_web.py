"""La interfaz web se sirve desde Flask junto a la API."""

import tempfile
from pathlib import Path

from flask import Flask

from pos.presentation.http.app import create_app
from pos.presentation.web import register_web

from ..support import PosTestCase


class WebTests(PosTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.static = Path(tmp.name)
        (self.static / "assets").mkdir()
        (self.static / "index.html").write_text("<div id=root></div>", encoding="utf-8")
        (self.static / "assets" / "app-123.js").write_text("console.log(1)", encoding="utf-8")
        app = Flask("prueba")
        register_web(app, self.static)
        self.client = app.test_client()

    def test_serves_the_app_for_any_screen(self):
        for url in ("/", "/caja", "/productos/nuevo"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertIn(b"root", response.data)
            self.assertIn("no-cache", response.headers["Cache-Control"])

    def test_assets_are_cached(self):
        response = self.client.get("/assets/app-123.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("max-age=31536000", response.headers["Cache-Control"])

    def test_explains_when_the_interface_is_not_built(self):
        app = Flask("vacia")
        register_web(app, self.static / "no-existe")
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"npm run build", response.data)

    def test_unknown_api_routes_still_answer_json(self):
        client = create_app(self.c).test_client()
        response = client.get("/api/v1/no-existe")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "not_found")
        self.assertEqual(client.get("/health").headers["X-Frame-Options"], "DENY")
