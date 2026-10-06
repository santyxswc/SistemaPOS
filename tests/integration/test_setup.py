"""Configuración inicial desde el navegador y arranque de una instalación nueva."""

import os
import tempfile
import unittest
from pathlib import Path

from pos.bootstrap import build_container
from pos.config import AppConfig, ensure_env_file, load_config
from pos.presentation.http.app import create_app

SETUP = {
    "business_name": "Panadería La Espiga",
    "username": "dueno",
    "full_name": "Ana Ruiz",
    "password": "clave-segura-1",
}


class InitialSetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = AppConfig(database_path=os.path.join(tmp.name, "pos.sqlite3"), secret_key="s" * 48,
                           password_iterations=1_000)
        self.client = create_app(build_container(config)).test_client()

    def test_first_run_creates_the_business_and_the_admin_and_logs_in(self):
        self.assertTrue(self.client.get("/api/v1/setup").get_json()["needs_setup"])

        response = self.client.post("/api/v1/setup", json=SETUP)

        self.assertEqual(response.status_code, 201, response.get_json())
        token = response.get_json()["access_token"]
        me = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).get_json()
        self.assertEqual((me["username"], me["role"]), ("dueno", "admin"))
        settings = self.client.get("/api/v1/settings", headers={"Authorization": f"Bearer {token}"}).get_json()
        self.assertEqual(settings["business_name"], "Panadería La Espiga")
        self.assertFalse(self.client.get("/api/v1/setup").get_json()["needs_setup"])

    def test_cannot_be_used_once_configured(self):
        self.client.post("/api/v1/setup", json=SETUP)
        intruder = self.client.post("/api/v1/setup", json={**SETUP, "username": "intruso"})
        self.assertEqual(intruder.status_code, 409)

    def test_invalid_data_leaves_nothing_half_done(self):
        response = self.client.post("/api/v1/setup", json={**SETUP, "username": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.client.get("/api/v1/setup").get_json()["needs_setup"])


class NewInstallationTests(unittest.TestCase):
    def test_creates_env_with_its_own_secret_and_keeps_data_inside_the_data_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            template = "POS_ENV=development\nPOS_SECRET_KEY=\nPOS_DATABASE_PATH=data/pos.sqlite3\n"
            self.assertTrue(ensure_env_file(data / ".env", template))
            self.assertFalse(ensure_env_file(data / ".env", template))  # nunca pisa una instalación existente

            saved = {key: os.environ.pop(key, None) for key in ("POS_ENV", "POS_SECRET_KEY", "POS_DATABASE_PATH")}
            try:
                config = load_config(data)
            finally:
                for key, value in saved.items():
                    os.environ.pop(key, None)
                    if value is not None:
                        os.environ[key] = value
            self.assertEqual(config.environment, "production")
            self.assertGreaterEqual(len(config.secret_key), 32)
            self.assertEqual(Path(config.database_path), data / "data" / "pos.sqlite3")
