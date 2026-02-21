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
