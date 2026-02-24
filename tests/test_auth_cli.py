# -*- coding: utf-8 -*-
"""Tests for scripts/auth_cli.py."""

from __future__ import annotations

import argparse

from scripts import auth_cli


def test_open_login_parser_defaults_to_empty_browser_id():
    parser = auth_cli._build_parser()
    args = parser.parse_args(["xhs-open-login"])

    assert args.command == "xhs-open-login"
    assert args.browser_id == ""
    assert args.verify is True


def test_xhs_login_parser_available_with_verify_toggle():
    parser = auth_cli._build_parser()
    args = parser.parse_args(["xhs-login", "--no-verify"])

    assert args.command == "xhs-login"
    assert args.verify is False
    assert args.handler is auth_cli._xhs_login_cmd


def test_xhs_open_login_cmd_omits_browser_id_when_empty(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_run_python_script(script_name: str, args: list[str]) -> int:
        captured["script_name"] = script_name
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(auth_cli, "_run_python_script", _fake_run_python_script)
    ns = argparse.Namespace(
        api_base="http://localhost:8080",
        energy_host="localhost",
        energy_port=50051,
        browser_id="",
        login_url="https://www.xiaohongshu.com",
        headless=False,
        poll_interval=2.0,
        timeout_sec=300.0,
        verify=True,
        json=False,
    )

    code = auth_cli._xhs_open_login_cmd(ns)

    assert code == 0
    assert captured["script_name"] == "xhs_open_login_and_sync.py"
    forwarded = captured["args"]
    assert "--browser-id" not in forwarded
    assert "--no-verify" not in forwarded


def test_xhs_open_login_cmd_passes_browser_id_when_provided(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_run_python_script(script_name: str, args: list[str]) -> int:
        captured["script_name"] = script_name
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(auth_cli, "_run_python_script", _fake_run_python_script)
    ns = argparse.Namespace(
        api_base="http://localhost:8080",
        energy_host="localhost",
        energy_port=50051,
        browser_id="manual_login_xhs",
        login_url="https://www.xiaohongshu.com",
        headless=False,
        poll_interval=2.0,
        timeout_sec=300.0,
        verify=False,
        json=False,
    )

    code = auth_cli._xhs_open_login_cmd(ns)

    assert code == 0
    forwarded = captured["args"]
    idx = forwarded.index("--browser-id")
    assert forwarded[idx + 1] == "manual_login_xhs"
    assert "--no-verify" in forwarded


def test_xhs_login_alias_reuses_open_login_flow(monkeypatch):
    called = {"count": 0}

    def _fake_open_login(args):
        called["count"] += 1
        return 0

    monkeypatch.setattr(auth_cli, "_xhs_open_login_cmd", _fake_open_login)
    ns = argparse.Namespace()

    code = auth_cli._xhs_login_cmd(ns)

    assert code == 0
    assert called["count"] == 1
