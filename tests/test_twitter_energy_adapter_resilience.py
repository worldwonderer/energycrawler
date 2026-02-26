# -*- coding: utf-8 -*-
"""Resilience tests for TwitterEnergyAdapter transaction-id bootstrap flow."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest
import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENERGY_ADAPTER_PATH = PROJECT_ROOT / "media_platform" / "twitter" / "energy_adapter.py"
MODULE_NAME = "test_twitter_energy_adapter_module"

module_spec = importlib.util.spec_from_file_location(MODULE_NAME, ENERGY_ADAPTER_PATH)
if module_spec is None or module_spec.loader is None:  # pragma: no cover - defensive
    raise RuntimeError("Failed to load twitter energy_adapter module for tests")
energy_adapter_module = importlib.util.module_from_spec(module_spec)
sys.modules[MODULE_NAME] = energy_adapter_module
module_spec.loader.exec_module(energy_adapter_module)

TwitterEnergyAdapter = energy_adapter_module.TwitterEnergyAdapter


class _DummyBrowserBackend:
    """Minimal BrowserInterface-compatible stub for adapter tests."""

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def create_browser(self, _browser_id: str, headless: bool = True) -> bool:
        _ = headless
        return True

    def close_browser(self, _browser_id: str) -> bool:
        return True

    def navigate(self, _browser_id: str, _url: str, timeout_ms: int = 30000) -> int:
        _ = timeout_ms
        return 200

    def get_cookies(self, _browser_id: str, _url: str):
        return []

    def set_cookies(self, _browser_id: str, _cookies) -> bool:
        return True

    def execute_js(self, _browser_id: str, _script: str):
        return ""

    def set_proxy(self, _browser_id: str, _proxy_url: str, username: str = "", password: str = "") -> bool:
        _ = (username, password)
        return True

    def execute_signature(self, _browser_id: str, _platform: str, _url: str):
        return {}


class _FakeResponse:
    def __init__(self, text: str = "<html></html>", status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://x.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("status error", request=request, response=response)


@pytest.mark.asyncio
async def test_get_page_html_retries_connect_timeout_then_succeeds(monkeypatch):
    adapter = TwitterEnergyAdapter(_DummyBrowserBackend(), "test-browser")
    state = {"calls": 0, "urls": []}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            _ = (exc_type, exc_val, exc_tb)
            return False

        async def get(self, url: str, headers):
            _ = headers
            state["calls"] += 1
            state["urls"].append(url)
            if state["calls"] == 1:
                raise httpx.ConnectTimeout("initial connect timeout")
            return _FakeResponse("<html>ok</html>")

    async def _fast_sleep(_seconds: float):
        return None

    monkeypatch.setattr(energy_adapter_module.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(energy_adapter_module.asyncio, "sleep", _fast_sleep)

    html = await adapter._get_page_html("https://x.com/tesla")

    assert html == "<html>ok</html>"
    assert state["calls"] == 2
    assert state["urls"][0] == "https://x.com/tesla"
    # degraded retry target: base URL after first connect timeout
    assert state["urls"][1] == "https://x.com"


@pytest.mark.asyncio
async def test_get_page_html_exhausted_connect_timeout_has_diagnostic_error(monkeypatch):
    adapter = TwitterEnergyAdapter(_DummyBrowserBackend(), "test-browser")
    adapter.set_retry_config(max_retries=2, retry_delay_ms=1, backoff_factor=1.0)

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            _ = (exc_type, exc_val, exc_tb)
            return False

        async def get(self, _url: str, headers):
            _ = headers
            raise httpx.ConnectTimeout("")

    async def _fast_sleep(_seconds: float):
        return None

    monkeypatch.setattr(energy_adapter_module.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(energy_adapter_module.asyncio, "sleep", _fast_sleep)

    with pytest.raises(RuntimeError) as exc_info:
        await adapter._get_page_html("https://x.com/tesla")

    message = str(exc_info.value)
    assert "_get_page_html connect timeout after 2 attempt(s)" in message
    assert "https://x.com/tesla" in message
    assert "ConnectTimeout" in message


@pytest.mark.asyncio
async def test_init_xclid_gen_wraps_empty_inner_error_with_stage_details(monkeypatch):
    adapter = TwitterEnergyAdapter(_DummyBrowserBackend(), "test-browser")

    async def _fail_get_page_html(_url: str = "https://x.com/tesla") -> str:
        raise RuntimeError("")

    monkeypatch.setattr(adapter, "_get_page_html", _fail_get_page_html)

    with pytest.raises(RuntimeError) as exc_info:
        await adapter._init_xclid_gen()

    message = str(exc_info.value)
    assert "_init_xclid_gen failed while fetching x page html" in message
    assert "RuntimeError" in message


@pytest.mark.asyncio
async def test_verify_login_via_page_skips_navigation_when_current_page_is_logged_in(monkeypatch):
    adapter = TwitterEnergyAdapter(_DummyBrowserBackend(), "test-browser")
    calls = {"navigate": 0}

    def _fake_navigate(_browser_id: str, _url: str, timeout_ms: int = 15000) -> int:
        _ = timeout_ms
        calls["navigate"] += 1
        return 200

    monkeypatch.setattr(adapter.browser, "navigate", _fake_navigate)
    monkeypatch.setattr(adapter, "_check_login_signal_in_current_page", lambda: True)

    ok = await adapter.verify_login_via_page()

    assert ok is True
    assert calls["navigate"] == 0


@pytest.mark.asyncio
async def test_verify_login_via_page_no_navigation_when_flag_disabled(monkeypatch):
    adapter = TwitterEnergyAdapter(_DummyBrowserBackend(), "test-browser")
    calls = {"navigate": 0}

    def _fake_navigate(_browser_id: str, _url: str, timeout_ms: int = 15000) -> int:
        _ = timeout_ms
        calls["navigate"] += 1
        return 200

    monkeypatch.setattr(adapter.browser, "navigate", _fake_navigate)
    monkeypatch.setattr(adapter, "_check_login_signal_in_current_page", lambda: False)

    ok = await adapter.verify_login_via_page(navigate_if_needed=False)

    assert ok is False
    assert calls["navigate"] == 0


@pytest.mark.asyncio
async def test_verify_login_via_page_navigates_once_when_fallback_needed(monkeypatch):
    adapter = TwitterEnergyAdapter(_DummyBrowserBackend(), "test-browser")
    calls = {"navigate": 0, "check": 0}

    def _fake_navigate(_browser_id: str, _url: str, timeout_ms: int = 15000) -> int:
        _ = timeout_ms
        calls["navigate"] += 1
        return 200

    def _fake_check() -> bool:
        calls["check"] += 1
        return calls["check"] >= 2

    async def _fast_sleep(_seconds: float):
        return None

    monkeypatch.setattr(adapter.browser, "navigate", _fake_navigate)
    monkeypatch.setattr(adapter, "_check_login_signal_in_current_page", _fake_check)
    monkeypatch.setattr(energy_adapter_module.asyncio, "sleep", _fast_sleep)

    ok = await adapter.verify_login_via_page(navigate_if_needed=True)

    assert ok is True
    assert calls["navigate"] == 1
    assert calls["check"] == 2
