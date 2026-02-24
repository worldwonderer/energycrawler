# -*- coding: utf-8 -*-
"""
Unit tests for preflight checks.
"""

import pytest

from tools import preflight


def test_parse_energy_service_address_defaults_port_on_invalid_value():
    host, port = preflight.parse_energy_service_address("localhost:not-a-port")
    assert host == "localhost"
    assert port == 50051


def test_has_twitter_auth_material_from_cookie_header():
    cookie = "foo=bar; auth_token=token123; ct0=ct0123"
    assert preflight.has_twitter_auth_material(cookie) is True


def test_has_twitter_auth_material_requires_both_fields():
    cookie = "foo=bar; auth_token=token123"
    assert preflight.has_twitter_auth_material(cookie) is False


def test_has_twitter_auth_material_explicit_cookie_does_not_fallback_to_env(monkeypatch):
    monkeypatch.setattr(preflight.config, "TWITTER_AUTH_TOKEN", "env-auth", raising=False)
    monkeypatch.setattr(preflight.config, "TWITTER_CT0", "env-ct0", raising=False)
    cookie = "foo=bar; auth_token=token123"
    assert preflight.has_twitter_auth_material(cookie) is False


def test_has_twitter_auth_material_fallback_to_env_when_cookie_empty(monkeypatch):
    monkeypatch.setattr(preflight.config, "TWITTER_AUTH_TOKEN", "env-auth", raising=False)
    monkeypatch.setattr(preflight.config, "TWITTER_CT0", "env-ct0", raising=False)
    monkeypatch.setattr(preflight.config, "TWITTER_COOKIE", "", raising=False)
    assert preflight.has_twitter_auth_material("") is True


def test_preflight_for_platform_validates_twitter_auth(monkeypatch):
    monkeypatch.setattr(preflight, "check_energy_service_reachable", lambda timeout_sec=2.0: (True, "ok"))
    ok, message = preflight.preflight_for_platform("x", "auth_token=1; ct0=2")
    assert ok is True
    assert message == "preflight passed"


def test_preflight_for_platform_xhs_canary_disabled(monkeypatch):
    called = {"ran": False}

    def _fake_canary():
        called["ran"] = True
        return True, "ok"

    monkeypatch.setattr(preflight, "check_energy_service_reachable", lambda timeout_sec=2.0: (True, "ok"))
    monkeypatch.setattr(preflight.config, "XHS_SIGNATURE_CANARY_ENABLED", False, raising=False)
    monkeypatch.setattr(preflight, "run_xhs_signature_canary", _fake_canary)
    ok, message = preflight.preflight_for_platform("xhs", "")
    assert ok is True
    assert message == "preflight passed"
    assert called["ran"] is False


def test_preflight_for_platform_xhs_canary_enabled_pass(monkeypatch):
    monkeypatch.setattr(preflight, "check_energy_service_reachable", lambda timeout_sec=2.0: (True, "ok"))
    monkeypatch.setattr(preflight.config, "XHS_SIGNATURE_CANARY_ENABLED", True, raising=False)
    monkeypatch.setattr(preflight, "run_xhs_signature_canary", lambda: (True, "xhs signature canary passed"))
    ok, message = preflight.preflight_for_platform("xhs", "")
    assert ok is True
    assert message == "preflight passed"


def test_preflight_for_platform_xhs_canary_enabled_fail(monkeypatch):
    monkeypatch.setattr(preflight, "check_energy_service_reachable", lambda timeout_sec=2.0: (True, "ok"))
    monkeypatch.setattr(preflight.config, "XHS_SIGNATURE_CANARY_ENABLED", True, raising=False)
    monkeypatch.setattr(preflight, "run_xhs_signature_canary", lambda: (False, "xhs signature canary failed"))
    ok, message = preflight.preflight_for_platform("xhs", "")
    assert ok is False
    assert "canary failed" in message


def test_ensure_energy_service_or_raise_runs_xhs_canary(monkeypatch):
    monkeypatch.setattr(preflight, "check_energy_service_reachable", lambda timeout_sec=2.0: (True, "ok"))
    monkeypatch.setattr(preflight.config, "XHS_SIGNATURE_CANARY_ENABLED", True, raising=False)
    monkeypatch.setattr(preflight, "run_xhs_signature_canary", lambda: (True, "canary ok"))
    preflight.ensure_energy_service_or_raise("xhs")


def test_ensure_energy_service_or_raise_raises_on_canary_fail(monkeypatch):
    monkeypatch.setattr(preflight, "check_energy_service_reachable", lambda timeout_sec=2.0: (True, "ok"))
    monkeypatch.setattr(preflight.config, "XHS_SIGNATURE_CANARY_ENABLED", True, raising=False)
    monkeypatch.setattr(preflight, "run_xhs_signature_canary", lambda: (False, "canary failed"))
    with pytest.raises(RuntimeError):
        preflight.ensure_energy_service_or_raise("xhs")


def test_ensure_energy_service_or_raise_validates_twitter_auth(monkeypatch):
    monkeypatch.setattr(preflight, "check_energy_service_reachable", lambda timeout_sec=2.0: (True, "ok"))
    monkeypatch.setattr(preflight.config, "TWITTER_AUTH_TOKEN", "", raising=False)
    monkeypatch.setattr(preflight.config, "TWITTER_CT0", "", raising=False)
    monkeypatch.setattr(preflight.config, "TWITTER_COOKIE", "", raising=False)
    monkeypatch.setattr(preflight.config, "COOKIES", "", raising=False)
    with pytest.raises(RuntimeError) as exc:
        preflight.ensure_energy_service_or_raise("x")
    assert "Missing Twitter auth material" in str(exc.value)
    assert "Actionable next steps:" in str(exc.value)
    assert "uv run energycrawler status --json" in str(exc.value)


def test_ensure_energy_service_or_raise_uses_twitter_cookie_for_x(monkeypatch):
    captured = {"platform": "", "cookie": ""}

    def _fake_preflight(platform: str, cookie_header: str = ""):
        captured["platform"] = platform
        captured["cookie"] = cookie_header
        return True, "ok"

    monkeypatch.setattr(preflight, "preflight_for_platform", _fake_preflight)
    monkeypatch.setattr(preflight.config, "TWITTER_COOKIE", "auth_token=abc; ct0=def", raising=False)
    monkeypatch.setattr(preflight.config, "COOKIES", "a1=xhs-only", raising=False)

    preflight.ensure_energy_service_or_raise("x")
    assert captured["platform"] == "x"
    assert captured["cookie"] == "auth_token=abc; ct0=def"


def test_build_preflight_failure_hint_for_unreachable_energy_includes_status_check():
    hint = preflight.build_preflight_failure_hint(
        "xhs",
        "Energy service unreachable at localhost:50051: connection refused",
    )

    assert "Start/recover service: uv run energycrawler energy ensure" in hint
    assert "Re-check runtime snapshot: uv run energycrawler status --json" in hint


def test_build_preflight_failure_hint_for_xhs_canary_includes_open_login_flow():
    hint = preflight.build_preflight_failure_hint(
        "xhs",
        "xhs signature canary failed: mnsv2 missing",
    )

    assert "Run canary details: uv run python scripts/check_xhs_signature_runtime.py --json" in hint
    assert "Re-login with open+sync+verify: uv run energycrawler auth xhs-open-login --api-base http://localhost:8080" in hint
    assert "Re-check runtime snapshot: uv run energycrawler status --json" in hint
