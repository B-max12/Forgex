"""Official registry sources for dependency research (spec section 8)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from forgex.schemas.research import ResearchNote

_VALID_NAME = re.compile(r"^[A-Za-z0-9_.\-/@]+$")


def _unavailable(topic: str, detail: str) -> ResearchNote:
    return ResearchNote(
        topic=topic,
        source="none",
        summary="lookup unavailable",
        confidence="low",
        available=False,
        detail=detail,
    )


class RegistrySource(ABC):
    ecosystem: str
    host: str

    @abstractmethod
    def build_url(self, name: str) -> str:
        pass

    @abstractmethod
    def parse(self, data: dict) -> tuple[str | None, str]:
        pass

    def validate_name(self, name: str) -> bool:
        return bool(_VALID_NAME.match(name)) and ".." not in name

    async def lookup(self, name: str, client: httpx.AsyncClient) -> ResearchNote:
        if not self.validate_name(name):
            return ResearchNote(
                topic=name,
                source=self.ecosystem,
                summary="invalid package name",
                confidence="low",
                available=False,
                detail=f"invalid package name for {self.ecosystem}",
            )

        url = self.build_url(name)
        try:
            resp = await client.get(url)
        except (httpx.TimeoutException, httpx.NetworkError, OSError) as exc:
            return ResearchNote(
                topic=name,
                source=self.ecosystem,
                summary="registry unreachable",
                confidence="low",
                available=False,
                detail=f"{self.ecosystem} unreachable: {exc}",
            )

        if resp.status_code == 404:
            return ResearchNote(
                topic=name,
                source=self.ecosystem,
                summary="not found in registry",
                confidence="low",
                available=False,
                detail=f"not found on {self.ecosystem}",
            )

        if resp.status_code != 200:
            return ResearchNote(
                topic=name,
                source=self.ecosystem,
                summary=f"registry returned HTTP {resp.status_code}",
                confidence="low",
                available=False,
                detail=f"HTTP {resp.status_code} from {self.ecosystem}",
            )

        try:
            data = resp.json()
            version, summary = self.parse(data)
        except Exception as exc:  # noqa: BLE001
            return ResearchNote(
                topic=name,
                source=self.ecosystem,
                summary="failed to parse registry response",
                confidence="low",
                available=False,
                detail=str(exc),
            )

        return ResearchNote(
            topic=name,
            source=self.ecosystem,
            summary=(summary or "no description available")[:200],
            version=version,
            checked_at=datetime.now(UTC),
            confidence="high",
            available=True,
            detail=url,
        )


class PyPISource(RegistrySource):
    ecosystem, host = "pypi", "pypi.org"

    def build_url(self, name: str) -> str:
        return f"https://pypi.org/pypi/{quote(name, safe='')}/json"

    def parse(self, data: dict) -> tuple[str | None, str]:
        info = data.get("info") or {}
        return info.get("version"), info.get("summary", "")


class NpmSource(RegistrySource):
    ecosystem, host = "npm", "registry.npmjs.org"

    def build_url(self, name: str) -> str:
        return f"https://registry.npmjs.org/{quote(name, safe='@/')}/latest"

    def parse(self, data: dict) -> tuple[str | None, str]:
        return data.get("version"), data.get("description", "")


class CratesSource(RegistrySource):
    ecosystem, host = "crates", "crates.io"

    def build_url(self, name: str) -> str:
        return f"https://crates.io/api/v1/crates/{quote(name, safe='')}"

    def parse(self, data: dict) -> tuple[str | None, str]:
        crate = data.get("crate") or {}
        return crate.get("max_version"), crate.get("description", "")


class GoSource(RegistrySource):
    ecosystem, host = "go", "proxy.golang.org"

    def validate_name(self, name: str) -> bool:
        return super().validate_name(name) and ("/" in name or "." in name)

    def build_url(self, name: str) -> str:
        return f"https://proxy.golang.org/{quote(name, safe='/')}/@latest"

    def parse(self, data: dict) -> tuple[str | None, str]:
        return data.get("Version"), "Go module (latest version)"
