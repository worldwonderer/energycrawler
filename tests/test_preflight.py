# -*- coding: utf-8 -*-
"""
Unit tests for preflight checks.
"""

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
