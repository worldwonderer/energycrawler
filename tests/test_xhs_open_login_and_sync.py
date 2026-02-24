# -*- coding: utf-8 -*-
"""Tests for scripts/xhs_open_login_and_sync.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import xhs_open_login_and_sync as wizard


def test_resolve_browser_id_uses_explicit_value():
    assert wizard._resolve_browser_id("manual_login_xhs") == "manual_login_xhs"


def test_resolve_browser_id_generates_isolated_id(monkeypatch):
    monkeypatch.setenv("ENERGY_BROWSER_ID_PREFIX", "energycrawler")
    monkeypatch.setattr(wizard.os, "getpid", lambda: 4321)
    monkeypatch.setattr(
        wizard.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890abcdef1234567890"),
    )

    browser_id = wizard._resolve_browser_id("")

    assert browser_id == "energycrawler_xhs_auth_4321_abcdef12"


def test_unwrap_success_payload_prefers_nested_data():
    payload = {
        "success": True,
        "message": "XHS energy session synced",
        "data": {
            "browser_id": "bid-1",
            "login_success": True,
            "cookie_count": 3,
            "message": "synced_from_energy_browser",
        },
    }

    flattened = wizard._unwrap_success_payload(payload)

    assert flattened["success"] is True
    assert flattened["browser_id"] == "bid-1"
    assert flattened["cookie_count"] == 3
    assert flattened["message"] == "synced_from_energy_browser"


def test_verify_sync_result_requires_a1_in_env(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("COOKIES=\"foo=bar; a1=abc123\"\n", encoding="utf-8")

    ok, message = wizard._verify_sync_result(
        {
            "success": True,
            "login_success": True,
            "cookie_count": 2,
        },
        env_path,
    )

    assert ok is True
    assert "contains a1" in message


def test_verify_sync_result_fails_when_env_missing_a1(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("COOKIES=\"foo=bar\"\n", encoding="utf-8")

    ok, message = wizard._verify_sync_result(
        {
            "success": True,
            "login_success": True,
            "cookie_count": 1,
        },
        env_path,
    )

    assert ok is False
    assert "missing a1" in message


def test_build_next_steps_includes_timeout_and_sync_hints():
    lines = wizard._build_next_steps(
        "login sync timeout after 30.0s, last_error=no cookies found",
        browser_id="manual_login_xhs",
        api_base="http://localhost:8080",
        timeout_sec=30.0,
    )

    joined = "\n".join(lines)
    assert "xhs-open-login" in joined
    assert "xhs-sync" in joined
    assert "auth status --json" in joined
