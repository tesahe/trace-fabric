"""Coverage for PSI + Mozilla Observatory wrappers + RemoteProviders bundle.

We mock httpx so tests run offline. Verifies:
  * 200 happy path returns parsed payload
  * 4xx/5xx returns None (not raise)
  * Network exception returns None (not raise)
  * Missing API key returns None for PSI
  * RemoteProviders.collect produces expected Detections
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signals.detection import MatchSource
from signals.remote_apis import (
    RemoteProviders,
    fetch_observatory_grade,
    fetch_psi_signals,
)
from signals.remote_apis import observatory as observatory_mod
from signals.remote_apis import psi as psi_mod


@pytest.fixture(autouse=True)
def _clear_caches():
    psi_mod.clear_cache()
    observatory_mod.clear_cache()
    yield
    psi_mod.clear_cache()
    observatory_mod.clear_cache()


def _mk_response(status: int = 200, json_payload: dict | None = None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.json = MagicMock(return_value=json_payload or {})
    return resp


def _mk_async_client(response):
    """Return an AsyncMock context manager that yields a client whose get/post
    return ``response``."""
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


# ---- PSI -------------------------------------------------------------------


def test_psi_returns_none_without_api_key():
    result = asyncio.run(fetch_psi_signals("https://example.com", api_key=None))
    assert result is None


def test_psi_happy_path_extracts_score():
    payload = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.42}},
            "audits": {
                "first-contentful-paint": {"score": 0.5, "displayValue": "2.1 s"},
                "largest-contentful-paint": {"score": 0.4, "displayValue": "3.2 s"},
            },
        }
    }
    response = _mk_response(200, payload)
    with patch("httpx.AsyncClient", return_value=_mk_async_client(response)):
        result = asyncio.run(
            fetch_psi_signals("https://example.com", api_key="fake-key")
        )
    assert result is not None
    assert result["score"] == 42
    assert result["strategy"] == "mobile"
    assert "first-contentful-paint" in result["audits"]


def test_psi_non_200_returns_none():
    response = _mk_response(403, {"error": "forbidden"}, text="forbidden")
    with patch("httpx.AsyncClient", return_value=_mk_async_client(response)):
        result = asyncio.run(
            fetch_psi_signals("https://example.com", api_key="fake-key")
        )
    assert result is None


def test_psi_network_exception_returns_none():
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=RuntimeError("boom"))
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=cm):
        result = asyncio.run(
            fetch_psi_signals("https://example.com", api_key="fake-key")
        )
    assert result is None


def test_psi_caches_result():
    payload = {"lighthouseResult": {"categories": {"performance": {"score": 0.9}}}}
    response = _mk_response(200, payload)
    client_cm = _mk_async_client(response)
    with patch("httpx.AsyncClient", return_value=client_cm) as mock_client:
        asyncio.run(fetch_psi_signals("https://x.com", api_key="k"))
        asyncio.run(fetch_psi_signals("https://x.com", api_key="k"))
    # Second call should hit the cache, not re-instantiate the client.
    assert mock_client.call_count == 1


# ---- Observatory -----------------------------------------------------------


def test_observatory_happy_path():
    payload = {"grade": "B+", "score": 75}
    response = _mk_response(200, payload)
    with patch("httpx.AsyncClient", return_value=_mk_async_client(response)):
        result = asyncio.run(fetch_observatory_grade("example.com"))
    assert result == {"grade": "B+", "score": 75}


def test_observatory_normalizes_url_input_to_host():
    payload = {"grade": "A", "score": 90}
    response = _mk_response(200, payload)
    with patch("httpx.AsyncClient", return_value=_mk_async_client(response)):
        result = asyncio.run(fetch_observatory_grade("https://example.com/foo/"))
    assert result == {"grade": "A", "score": 90}


def test_observatory_non_200_returns_none():
    response = _mk_response(500, {}, text="server error")
    with patch("httpx.AsyncClient", return_value=_mk_async_client(response)):
        result = asyncio.run(fetch_observatory_grade("example.com"))
    assert result is None


def test_observatory_timeout_returns_none():
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=TimeoutError("timeout"))
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=cm):
        result = asyncio.run(fetch_observatory_grade("example.com"))
    assert result is None


def test_observatory_handles_nested_scan_field():
    payload = {"scan": {"grade": "C", "score": 60}}
    response = _mk_response(200, payload)
    with patch("httpx.AsyncClient", return_value=_mk_async_client(response)):
        result = asyncio.run(fetch_observatory_grade("nested.example"))
    assert result == {"grade": "C", "score": 60}


# ---- RemoteProviders bundle ------------------------------------------------


def test_remote_providers_disabled_by_default_returns_empty():
    providers = RemoteProviders(psi_enabled=False, observatory_enabled=False)
    assert providers.is_enabled() is False
    detections = asyncio.run(providers.collect({"final_url": "https://example.com"}))
    assert detections == []


def test_remote_providers_psi_only_emits_score_detection():
    payload = {"lighthouseResult": {"categories": {"performance": {"score": 0.30}}}}
    response = _mk_response(200, payload)
    with patch("httpx.AsyncClient", return_value=_mk_async_client(response)):
        providers = RemoteProviders(
            psi_enabled=True,
            observatory_enabled=False,
            psi_api_key="fake-key",
        )
        detections = asyncio.run(
            providers.collect({"final_url": "https://example.com"})
        )
    names = [d.name for d in detections]
    assert any("PSI mobile score" in n for n in names)
    # score 30 < 50 -> the below_50 signal Detection also fires
    assert "psi_mobile_score_below_50" in names
    assert all(d.source == MatchSource.REMOTE_PSI for d in detections)


def test_remote_providers_observatory_emits_grade_detection():
    payload = {"grade": "F", "score": 0}
    response = _mk_response(200, payload)
    with patch("httpx.AsyncClient", return_value=_mk_async_client(response)):
        providers = RemoteProviders(
            psi_enabled=False,
            observatory_enabled=True,
        )
        detections = asyncio.run(
            providers.collect({"final_url": "https://example.com"})
        )
    names = [d.name for d in detections]
    assert any("Observatory grade" in n for n in names)
    assert "observatory_grade_F" in names
    assert all(d.source == MatchSource.REMOTE_OBSERVATORY for d in detections)


def test_remote_providers_collect_safe_when_psi_raises():
    """If PSI errors, Observatory still runs."""
    obs_payload = {"grade": "A", "score": 95}
    obs_response = _mk_response(200, obs_payload)

    # PSI will raise via psi.fetch_psi_signals being patched
    async def fake_psi(*args, **kwargs):
        raise RuntimeError("boom")

    with patch("signals.remote_apis.providers.fetch_psi_signals", side_effect=fake_psi):
        with patch("httpx.AsyncClient", return_value=_mk_async_client(obs_response)):
            providers = RemoteProviders(
                psi_enabled=True,
                observatory_enabled=True,
                psi_api_key="fake-key",
            )
            detections = asyncio.run(
                providers.collect({"final_url": "https://example.com"})
            )
    names = [d.name for d in detections]
    # Observatory still landed.
    assert any("Observatory grade: A" in n for n in names)
    # PSI did not.
    assert not any("PSI" in n for n in names)
