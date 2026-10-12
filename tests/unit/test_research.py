import httpx
import pytest

from forgex.config.schema import ForgexConfig, ResearchConfig
from forgex.research.engine import ResearchEngine


def make_engine(handler, config=None):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ResearchEngine(http_client=client, config=config)


def registry_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.startswith("https://pypi.org/pypi/fastapi/"):
        return httpx.Response(200, json={"info": {"version": "0.115.0",
                                                  "summary": "FastAPI framework"}})
    if url.startswith("https://registry.npmjs.org/express/"):
        return httpx.Response(200, json={"version": "4.21.2",
                                         "description": "web framework"}) if False else \
            httpx.Response(200, json={"version": "4.21.2", "description": "web framework"})
    if url.startswith("https://crates.io/api/v1/crates/serde"):
        return httpx.Response(200, json={"crate": {"max_version": "1.0.210",
                                                   "description": "serialization"}})
    if url.startswith("https://proxy.golang.org/"):
        return httpx.Response(200, json={"Version": "v1.9.0"})
    return httpx.Response(404, json={})


async def test_prefixed_pypi_lookup():
    engine = make_engine(registry_handler)
    notes = await engine.research(["pypi:fastapi"])
    assert notes[0].available and notes[0].source == "pypi"
    assert notes[0].version == "0.115.0"
    assert notes[0].confidence == "high"
    assert notes[0].checked_at is not None


async def test_plain_name_falls_through_to_npm():
    engine = make_engine(registry_handler)
    notes = await engine.research(["express"])
    assert notes[0].available and notes[0].source == "npm"
    assert notes[0].version == "4.21.2"


async def test_crates_and_go_sources():
    engine = make_engine(registry_handler)
    crates = await engine.research(["crates:serde"])
    assert crates[0].available and crates[0].version == "1.0.210"
    go = await engine.research(["go:github.com/gin-gonic/gin"])
    assert go[0].available and go[0].version == "v1.9.0"


async def test_not_found_is_explicitly_unavailable():
    engine = make_engine(registry_handler)
    notes = await engine.research(["pypi:no-such-package-xyz"])
    assert not notes[0].available
    assert "not found on pypi" in notes[0].detail
    assert notes[0].confidence == "low"


async def test_plain_name_missing_everywhere():
    engine = make_engine(registry_handler)
    notes = await engine.research(["does-not-exist-anywhere"])
    assert not notes[0].available
    assert "not found in any registry" in notes[0].detail


async def test_network_failure_never_raises():
    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    engine = make_engine(failing)
    notes = await engine.research(["pypi:fastapi"])
    assert not notes[0].available and "unreachable" in notes[0].detail


async def test_invalid_name_rejected():
    engine = make_engine(registry_handler)
    notes = await engine.research(["pypi:../etc/passwd"])
    assert not notes[0].available and "invalid" in notes[0].detail


async def test_disabled_config_offline_notes():
    config = ForgexConfig(research=ResearchConfig(enabled=False))
    engine = make_engine(registry_handler, config=config)
    notes = await engine.research(["pypi:fastapi"])
    assert not notes[0].available
    assert "disabled" in notes[0].detail

