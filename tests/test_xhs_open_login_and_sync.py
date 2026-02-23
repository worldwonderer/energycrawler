# -*- coding: utf-8 -*-
"""Tests for scripts/xhs_open_login_and_sync.py helpers."""

from __future__ import annotations

from types import SimpleNamespace

from scripts import xhs_open_login_and_sync as open_login


def test_resolve_browser_id_uses_explicit_value():
    assert open_login._resolve_browser_id("manual_login_xhs") == "manual_login_xhs"


def test_resolve_browser_id_generates_isolated_id(monkeypatch):
    monkeypatch.setenv("ENERGY_BROWSER_ID_PREFIX", "energycrawler")
    monkeypatch.setattr(open_login.os, "getpid", lambda: 4321)
    monkeypatch.setattr(
        open_login.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890abcdef1234567890"),
    )

    browser_id = open_login._resolve_browser_id("")

    assert browser_id == "energycrawler_xhs_auth_4321_abcdef12"
