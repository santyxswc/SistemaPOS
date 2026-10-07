"""Aviso de versiones nuevas publicadas en GitHub Releases."""

import unittest

from pos import __version__
from pos.application.modules import Module
from pos.application.ports import ReleaseInfo
from pos.application.use_cases.updates import CheckForUpdates, UpdateStatus, parse_version
from pos.config import AppConfig
from pos.domain.shared.errors import PermissionDenied
from pos.infrastructure.releases import parse_release

from ..support import ApiTestCase, FixedClock, PosTestCase


class FakeSource:
    def __init__(self, *versions):
        self.answers = list(versions)
        self.calls = 0

    def latest(self):
        self.calls += 1
        version = self.answers.pop(0) if self.answers else None
        return ReleaseInfo(version=version, url=f"https://x/v{version}") if version else None


class VersionTests(unittest.TestCase):
    def test_compares_numbers_not_text(self):
        self.assertEqual(parse_version("v0.10.2"), (0, 10, 2))
        self.assertIsNone(parse_version("0.4.0-beta"))
        newer = UpdateStatus(current="0.9.0", latest=ReleaseInfo(version="0.10.0", url=""), checked_at=None)
        same = UpdateStatus(current="0.10.0", latest=ReleaseInfo(version="0.10.0", url=""), checked_at=None)
        self.assertTrue(newer.available)
        self.assertFalse(same.available)
        self.assertFalse(UpdateStatus(current="0.1.0", latest=None, checked_at=None).available)

    def test_parses_github_release_and_ignores_drafts(self):
        release = parse_release({
            "tag_name": "v0.4.0", "html_url": "https://github.com/a/b/releases/tag/v0.4.0",
            "published_at": "2026-11-01T12:00:00Z", "body": "Novedades",
            "assets": [{"name": "PuntoDeVenta-0.4.0-windows.zip", "browser_download_url": "z"},
                       {"name": "PuntoDeVenta-0.4.0-setup.exe", "browser_download_url": "https://dl/setup.exe"}],
        })
        self.assertEqual((release.version, release.download_url), ("0.4.0", "https://dl/setup.exe"))
        self.assertEqual(release.published_at.year, 2026)
        self.assertIsNone(parse_release({"tag_name": "v9.0.0", "html_url": "u", "prerelease": True}))

    def test_config_can_turn_it_off_or_point_elsewhere(self):
        base = {"POS_ENV": "development"}
        self.assertEqual(AppConfig.from_env(base).update_repository, "santyxswc/SistemaPOS")
        self.assertFalse(AppConfig.from_env({**base, "POS_UPDATE_CHECK": "0"}).modules.is_enabled(Module.UPDATES))
        self.assertEqual(AppConfig.from_env({**base, "POS_UPDATE_REPO": "otro/pos"}).update_repository, "otro/pos")


class CheckForUpdatesTests(PosTestCase):
    def test_asks_at_most_every_six_hours_and_remembers_when_offline(self):
        clock = FixedClock()
        source = FakeSource("99.0.0", None)
        check = CheckForUpdates(source, "0.3.0", clock)

        first = check.execute(self.admin)
        check.execute(self.admin)
        self.assertEqual((first.available, source.calls), (True, 1))

        clock.advance(hours=7)
        offline = check.execute(self.admin)
        self.assertEqual((source.calls, offline.latest.version), (2, "99.0.0"))  # sin internet conserva el dato

    def test_only_the_administrator_sees_it(self):
        with self.assertRaises(PermissionDenied):
            self.c.check_for_updates.execute(self.make_cashier())


class UpdatesApiTests(ApiTestCase):
    def test_endpoint_without_source_reports_current_version(self):
        body = self.api("GET", "/api/v1/updates").get_json()
        self.assertEqual((body["current"], body["available"], body["latest"]), (__version__, False, None))
