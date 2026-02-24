# -*- coding: utf-8 -*-
"""Tests for energycrawler quickstart command."""

from __future__ import annotations

import argparse

from scripts import energycrawler_cli as cli


def _quickstart_args(**overrides) -> argparse.Namespace:
    base = {
        "template": ".env.quickstart.example",
        "env_file": ".env",
        "force": False,
        "host": "localhost",
        "port": 50051,
        "timeout": cli.DEFAULT_TIMEOUT,
        "retries": cli.DEFAULT_ENSURE_RETRIES,
        "sleep": cli.DEFAULT_ENSURE_SLEEP,
        "api_base": "http://127.0.0.1:8080",
        "api_timeout": cli.DEFAULT_API_TIMEOUT,
        "platform": "xhs",
        "keywords": "新能源,储能",
        "creator_ids": "60d5b32a000000002002cf79",
        "interval_minutes": 60,
        "save_option": "json",
        "headless": True,
        "storage_check": False,
        "skip_demo": False,
        "non_interactive": False,
        "strict": False,
        "json": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_parser_includes_quickstart_command():
    parser = cli._build_parser()
    args = parser.parse_args(["quickstart", "--non-interactive", "--platform", "x"])

    assert args.command == "quickstart"
    assert args.non_interactive is True
    assert args.platform == "x"
    assert args.handler is cli._quickstart_cmd


def test_quickstart_success_outputs_user_flow_next_steps(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_prepare_env_file", lambda **_kwargs: (True, "env ready"))
    monkeypatch.setattr(cli, "_run_local_script", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        cli,
        "_run_precheck_suite",
        lambda **_kwargs: {"healthy": True, "checks": []},
    )
    monkeypatch.setattr(
        cli,
        "_run_login_state_precheck",
        lambda *_args, **_kwargs: {"ok": True, "detail": "login ready"},
    )
    monkeypatch.setattr(
        cli,
        "_run_quickstart_demo_trigger",
        lambda **_kwargs: {"ok": True, "detail": "demo trigger ok"},
    )

    code = cli._quickstart_cmd(_quickstart_args())

    assert code == 0
    output = capsys.readouterr().out
    assert "[quickstart] PASS: demo_trigger - demo trigger ok" in output
    assert "/ui#/welcome" in output
    assert "/ui#/runs" in output
    assert "/ui#/settings" in output


def test_quickstart_non_interactive_skips_demo_when_login_not_ready(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_prepare_env_file", lambda **_kwargs: (True, "env ready"))
    monkeypatch.setattr(cli, "_run_local_script", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        cli,
        "_run_precheck_suite",
        lambda **_kwargs: {"healthy": True, "checks": []},
    )
    monkeypatch.setattr(
        cli,
        "_run_login_state_precheck",
        lambda *_args, **_kwargs: {"ok": False, "detail": "xhs login not ready"},
    )

    def _should_not_run_demo(**_kwargs):
        raise AssertionError("demo trigger should be skipped in non-interactive mode without login")

    monkeypatch.setattr(cli, "_run_quickstart_demo_trigger", _should_not_run_demo)

    code = cli._quickstart_cmd(_quickstart_args(non_interactive=True))

    assert code == 0
    output = capsys.readouterr().out
    assert "[quickstart] WARN: login_readiness - xhs login not ready" in output
    assert "demo trigger skipped because login is not ready in --non-interactive mode" in output
    assert "auth xhs-open-login" in output
    assert "scheduler smoke-e2e" in output


def test_quickstart_strict_mode_fails_when_login_not_ready(monkeypatch):
    monkeypatch.setattr(cli, "_prepare_env_file", lambda **_kwargs: (True, "env ready"))
    monkeypatch.setattr(cli, "_run_local_script", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        cli,
        "_run_precheck_suite",
        lambda **_kwargs: {"healthy": True, "checks": []},
    )
    monkeypatch.setattr(
        cli,
        "_run_login_state_precheck",
        lambda *_args, **_kwargs: {"ok": False, "detail": "xhs login not ready"},
    )
    monkeypatch.setattr(
        cli,
        "_run_quickstart_demo_trigger",
        lambda **_kwargs: {"ok": False, "detail": "demo trigger failed"},
    )

    code = cli._quickstart_cmd(_quickstart_args(non_interactive=True, strict=True))

    assert code == 1
