# -*- coding: utf-8 -*-
"""Unit tests for XHS signature session state behavior."""

from __future__ import annotations

import pytest

import media_platform.xhs.energy_client_adapter as adapter_module
import media_platform.xhs.signature_state as state_module
from media_platform.xhs.energy_client_adapter import XHSEnergyAdapter
from media_platform.xhs.signature_state import SignatureSessionStore


class _FakeBrowserBackend:
    def __init__(self) -> None:
        self.mnsv2_mode = "success"

    def execute_js(self, browser_id: str, script: str):
        if script == "JSON.stringify(window.localStorage)":
            return '{"b1":"b1_from_storage"}'
        if script.startswith("window.mnsv2("):
            if self.mnsv2_mode == "success":
                return '"signed_value"'
            if self.mnsv2_mode == "empty":
                return ""
            raise RuntimeError("mnsv2 crashed")
        return ""


def test_signature_session_store_cleanup():
    store = SignatureSessionStore(ttl_sec=60)
    store.begin_request("browser_a")
    assert store.snapshot("browser_a") is not None

    # Force expiry without waiting for wall-clock time.
    with store._lock:  # noqa: SLF001 - test helper
        store._states["browser_a"].last_updated_at = 0.0  # noqa: SLF001 - test helper

    assert store.cleanup_expired() == 1
    assert store.snapshot("browser_a") is None


@pytest.mark.asyncio
async def test_x_t_is_monotonic_with_same_clock(monkeypatch):
    backend = _FakeBrowserBackend()
    adapter = XHSEnergyAdapter(backend, browser_id="b1", enable_cache=False)
    adapter.set_retry_config(max_retries=1, retry_delay_ms=1, backoff_factor=1.0)

    monkeypatch.setattr(adapter_module.time, "time", lambda: 1000.0)
    monkeypatch.setattr(state_module.time, "time", lambda: 1000.0)

    result1 = await adapter.sign_with_energy("/api/sns/web/v1/search/notes", {"keyword": "k"}, a1="a1", method="POST")
    result2 = await adapter.sign_with_energy("/api/sns/web/v1/search/notes", {"keyword": "k"}, a1="a1", method="POST")

    assert int(result2["x-t"]) == int(result1["x-t"]) + 1
    state = adapter.get_signature_session_state()
    assert state is not None
    assert state.request_seq == 2
    assert state.consecutive_failures == 0
    assert state.last_x_t == int(result2["x-t"])


@pytest.mark.asyncio
async def test_failure_counter_increments_and_resets():
    backend = _FakeBrowserBackend()
    backend.mnsv2_mode = "empty"
    adapter = XHSEnergyAdapter(backend, browser_id="b2", enable_cache=False)
    adapter.set_retry_config(max_retries=1, retry_delay_ms=1, backoff_factor=1.0)

    await adapter.sign_with_energy("/api/sns/web/v1/search/notes", {"keyword": "k"}, a1="a1", method="POST")
    await adapter.sign_with_energy("/api/sns/web/v1/search/notes", {"keyword": "k"}, a1="a1", method="POST")

    state = adapter.get_signature_session_state()
    assert state is not None
    assert state.request_seq == 2
    assert state.consecutive_failures == 2

    backend.mnsv2_mode = "success"
    await adapter.sign_with_energy("/api/sns/web/v1/search/notes", {"keyword": "k"}, a1="a1", method="POST")
    state = adapter.get_signature_session_state()
    assert state is not None
    assert state.request_seq == 3
    assert state.consecutive_failures == 0
