# -*- coding: utf-8 -*-
"""Unit tests for unified energycrawler CLI workflows."""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

from scripts import energycrawler_cli as cli


def _doctor_args(**overrides):
    base = {
        "host": "localhost",
        "port": 50051,
        "timeout": 8.0,
        "json": False,
        "skip_login_check": False,
        "storage_check": False,
        "cleanup_report": False,
        "cleanup_fail_on_findings": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _setup_args(**overrides):
    base = {
        "template": ".env.quickstart.example",
        "env_file": ".env",
        "force": False,
        "host": "localhost",
        "port": 50051,
        "timeout": 8.0,
        "retries": 1,
        "sleep": 0.1,
        "storage_check": False,
        "skip_browser_check": True,
        "skip_login_readiness": False,
        "strict": False,
        "json": True,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_parser_includes_setup_config_show_and_precheck():
    parser = cli._build_parser()

    setup_args = parser.parse_args(["setup", "--json"])
    assert setup_args.command == "setup"
    assert setup_args.handler is cli._setup_cmd

    config_args = parser.parse_args(["config", "show", "--json"])
    assert config_args.command == "config"
    assert config_args.config_command == "show"
    assert config_args.handler is cli._config_show_cmd

    precheck_args = parser.parse_args(["precheck", "--json"])
    assert precheck_args.command == "precheck"
    assert precheck_args.handler is cli._doctor_cmd

    run_args = parser.parse_args(["run", "--platform", "xhs", "--keywords", "新能源"])
    assert run_args.command == "run"
    assert run_args.handler is cli._run_simple_cmd


def test_collect_runtime_config_masks_sensitive_values(monkeypatch):
    fake_config = SimpleNamespace(
        PLATFORM="xhs",
        CRAWLER_TYPE="search",
        LOGIN_TYPE="cookie",
        KEYWORDS="新能源",
        HEADLESS=False,
        SAVE_DATA_OPTION="json",
        SAVE_DATA_PATH="",
        ENABLE_ENERGY_BROWSER=True,
        ENERGY_SERVICE_ADDRESS="localhost:50051",
        ENERGY_HEADLESS=True,
        ENERGY_BROWSER_ID_PREFIX="energycrawler",
        ENERGY_BROWSER_ID="energycrawler_xhs",
        COOKIES="a1=1234567890abcdef",
        TWITTER_COOKIE="auth_token=abcdef123456; ct0=ct0123456789",
        TWITTER_AUTH_TOKEN="abcdef1234567890",
        TWITTER_CT0="ct0123456789abcd",
        resolve_energy_browser_id=lambda platform: f"resolved_{platform}",
    )
    monkeypatch.setattr(cli, "_load_base_config_module", lambda: fake_config)

    payload = cli._collect_runtime_config(show_secrets=False)

    assert payload["PLATFORM"] == "xhs"
    assert payload["ENERGY_BROWSER_ID_RESOLVED"] == "resolved_xhs"
    assert payload["COOKIES"] != fake_config.COOKIES
    assert payload["TWITTER_AUTH_TOKEN"] != fake_config.TWITTER_AUTH_TOKEN
    assert "chars" in payload["COOKIES"]


def test_config_show_outputs_json(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "_collect_runtime_config",
        lambda **_: {"PLATFORM": "xhs", "COOKIES": "***"},
    )
    args = argparse.Namespace(show_secrets=False, simple=False, json=True)

    code = cli._config_show_cmd(args)

    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["runtime_config"]["PLATFORM"] == "xhs"
    assert output["runtime_config"]["COOKIES"] == "***"


def test_config_show_simple_outputs_core_keys(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "_collect_runtime_config",
        lambda **kwargs: {"PLATFORM": "xhs", "ENERGY_SERVICE_ADDRESS": "localhost:50051"},
    )
    args = argparse.Namespace(show_secrets=False, simple=True, json=False)

    code = cli._config_show_cmd(args)

    assert code == 0
    output = capsys.readouterr().out
    assert "PLATFORM=xhs" in output
    assert "ENERGY_SERVICE_ADDRESS=localhost:50051" in output


def test_doctor_keeps_failure_code_when_cleanup_passes(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_run_doctor_checks", lambda **_: 1)
    calls = {"cleanup": 0}

    def _fake_cleanup_report(*, json_output: bool, fail_on_findings: bool) -> int:
        calls["cleanup"] += 1
        return 0

    monkeypatch.setattr(cli, "_run_cleanup_report", _fake_cleanup_report)

    code = cli._doctor_cmd(_doctor_args(cleanup_report=True))

    assert code == 1
    assert calls["cleanup"] == 1
    assert "[doctor] Summary: checks failed" in capsys.readouterr().out


def test_doctor_json_cleanup_returns_single_structured_payload(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_run_precheck_suite", lambda **_: {"healthy": False, "checks": []})
    monkeypatch.setattr(
        cli,
        "_run_cleanup_report_check",
        lambda **_: {"name": "cleanup_report", "ok": True, "exit_code": 0},
    )

    code = cli._doctor_cmd(_doctor_args(json=True, cleanup_report=True))

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert "doctor" in payload
    assert "cleanup_report" in payload
    assert payload["doctor"]["healthy"] is False
    assert payload["cleanup_report"]["ok"] is True


def test_setup_minimal_json_flow(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_prepare_env_file", lambda **_: (True, "env ready"))
    monkeypatch.setattr(
        cli,
        "_run_local_script_capture",
        lambda *_, **__: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(cli, "_run_precheck_suite", lambda **_: {"healthy": True, "checks": []})
    monkeypatch.setattr(
        cli,
        "_run_login_state_precheck",
        lambda *_, **__: {"name": "login_state", "ok": True, "detail": "ok", "exit_code": 0},
    )

    code = cli._setup_cmd(_setup_args())

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["setup_ok"] is True
    step_names = [step["name"] for step in payload["steps"]]
    assert "env_file" in step_names
    assert "energy_ensure" in step_names
    assert "doctor_precheck" in step_names
    assert "login_readiness" in step_names


def test_run_simple_builds_balanced_defaults():
    args = argparse.Namespace(
        platform="xhs",
        crawler_type="search",
        keywords="新能源",
        specified_id="",
        creator_id="",
        safety_profile="balanced",
        save_option="json",
        headless=False,
        dry_run=False,
        extra=[],
    )

    forwarded = cli._build_simple_run_args(args)
    assert "--platform" in forwarded and "xhs" in forwarded
    assert "--type" in forwarded and "search" in forwarded
    assert "--keywords" in forwarded and "新能源" in forwarded
    assert "--max_notes_count" in forwarded and "10" in forwarded
    assert "--crawl_sleep_sec" in forwarded and "8.0" in forwarded


def test_run_simple_keeps_explicit_advanced_limits():
    args = argparse.Namespace(
        platform="x",
        crawler_type="search",
        keywords="open source",
        specified_id="",
        creator_id="",
        safety_profile="safe",
        save_option="json",
        headless=True,
        dry_run=False,
        extra=["--", "--max_notes_count", "3", "--crawl_sleep_sec", "12"],
    )

    forwarded = cli._build_simple_run_args(args)
    assert "--max_notes_count" in forwarded and "3" in forwarded
    assert "--crawl_sleep_sec" in forwarded and "12" in forwarded


def test_run_simple_requires_keywords_for_search(capsys):
    args = argparse.Namespace(
        platform="xhs",
        crawler_type="search",
        keywords="",
        specified_id="",
        creator_id="",
        safety_profile="balanced",
        save_option="json",
        headless=False,
        dry_run=False,
        extra=[],
    )

    code = cli._run_simple_cmd(args)

    assert code == 2
    assert "requires --keywords" in capsys.readouterr().err
