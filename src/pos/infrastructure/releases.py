"""Última versión publicada en GitHub Releases (repositorio público, sin credenciales)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime

from ..application.ports import ReleaseInfo

logger = logging.getLogger("pos.updates")

DEFAULT_REPOSITORY = "santyxswc/SistemaPOS"
TIMEOUT_SECONDS = 4
MAX_NOTES = 2000


class GitHubReleaseSource:
    def __init__(self, repository: str = DEFAULT_REPOSITORY, user_agent: str = "PuntoDeVenta") -> None:
        self._url = f"https://api.github.com/repos/{repository}/releases/latest"
        self._user_agent = user_agent

    def latest(self) -> ReleaseInfo | None:
        request = urllib.request.Request(
            self._url, headers={"Accept": "application/vnd.github+json", "User-Agent": self._user_agent}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return parse_release(json.load(response))
        except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
            # Sin internet, sin versiones publicadas (404) o límite de consultas: no es un error del negocio.
            logger.info("No se pudo consultar la última versión: %s", error)
            return None


def parse_release(data: dict) -> ReleaseInfo | None:
    if data.get("draft") or data.get("prerelease"):
        return None
    installer = next(
        (asset["browser_download_url"] for asset in data.get("assets", []) if asset["name"].endswith("-setup.exe")),
        None,
    )
    published = data.get("published_at")
    return ReleaseInfo(
        version=str(data["tag_name"]).lstrip("v"),
        url=data["html_url"],
        download_url=installer,
        published_at=datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None,
        notes=(data.get("body") or "")[:MAX_NOTES],
    )


class NoReleaseSource:
    """Objeto nulo: el aviso de versiones está apagado (POS_UPDATE_CHECK=0 o pruebas)."""

    def latest(self) -> ReleaseInfo | None:
        return None
