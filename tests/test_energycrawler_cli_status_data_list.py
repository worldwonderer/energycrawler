# -*- coding: utf-8 -*-
"""Tests for energycrawler status and data list commands."""

from __future__ import annotations

import argparse
import json
from urllib.parse import parse_qs, urlparse

from scripts import energycrawler_cli as cli


def _status_args(**overrides) -> argparse.Namespace:
    base = {
        "api_base": "http://127.0.0.1:8080",
        "timeout": cli.DEFAULT_API_TIMEOUT,
        "json": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _data_list_args(**overrides) -> argparse.Namespace:
    base = {
        "api_base": "http://127.0.0.1:8080",
        "platform": None,
        "file_type": None,
        "limit": 20,
        "json": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_parser_includes_data_list_command():
    parser = cli._build_parser()
    args = parser.parse_args(["data", "list", "--platform", "xhs", "--limit", "5"])

    assert args.command == "data"
    assert args.data_command == "list"
    assert args.platform == "xhs"
    assert args.limit == 5
    assert args.handler is cli._data_list_cmd


def test_data_list_outputs_human_summary(monkeypatch, capsys):
    seen: dict[str, str] = {}
    payload = {
        "success": True,
        "data": {
            "files": [
                {
                    "name": "newer.json",
                    "path": "xhs/newer.json",
                    "type": "json",
                    "record_count": 20,
                    "size": 1024,
                    "modified_at": 1700000000,
                },
                {
                    "name": "older.csv",
                    "path": "xhs/older.csv",
                    "type": "csv",
                    "record_count": 5,
                    "size": 256,
                    "modified_at": 1699990000,
                },
            ]
        },
    }

    def _fake_fetch(url: str, *, timeout: float = cli.DEFAULT_API_TIMEOUT):
        seen["url"] = url
        return 200, json.dumps(payload).encode("utf-8"), {}

    monkeypatch.setattr(cli, "_api_fetch", _fake_fetch)

    code = cli._data_list_cmd(_data_list_args(platform="xhs", file_type="json", limit=1))

    assert code == 0
    output = capsys.readouterr().out
    assert "[data list] total_files=2 showing=1" in output
    assert "path=xhs/newer.json" in output
    query = parse_qs(urlparse(seen["url"]).query)
    assert query["platform"] == ["xhs"]
    assert query["file_type"] == ["json"]


def test_data_list_returns_nonzero_with_hints_when_no_files(monkeypatch, capsys):
    payload = {"success": True, "data": {"files": []}}
    monkeypatch.setattr(
        cli,
        "_api_fetch",
        lambda *_args, **_kwargs: (200, json.dumps(payload).encode("utf-8"), {}),
    )

    code = cli._data_list_cmd(_data_list_args(platform="x"))

    assert code == 4
    stderr = capsys.readouterr().err
    assert "No data files found" in stderr
    assert "Actionable next steps:" in stderr
    assert "uv run energycrawler run --platform x --keywords" in stderr


def test_data_list_returns_nonzero_when_api_unreachable(monkeypatch, capsys):
    def _raise_unreachable(*_args, **_kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(cli, "_api_fetch", _raise_unreachable)

    code = cli._data_list_cmd(_data_list_args())

    assert code == 2
    stderr = capsys.readouterr().err
    assert "API unreachable" in stderr
    assert "Actionable next steps:" in stderr


def test_status_outputs_summary_for_healthy_snapshot(monkeypatch, capsys):
    payload = {
        "success": True,
        "data": {
            "checked_at": "2026-02-23T08:00:00+00:00",
            "overall_healthy": True,
            "overall_status": "healthy",
            "energy": {"ok": True, "message": "reachable"},
            "login": {
                "xhs": {"ok": True, "message": "ok"},
                "x": {"ok": True, "message": "ok"},
            },
            "crawler_queue": {"healthy": True, "status": "ready", "running_workers": 0, "total_workers": 2, "queued_tasks": 0},
        },
    }
    monkeypatch.setattr(
        cli,
        "_api_fetch",
        lambda *_args, **_kwargs: (200, json.dumps(payload).encode("utf-8"), {}),
    )

    code = cli._status_cmd(_status_args())

    assert code == 0
    stdout = capsys.readouterr().out
    assert "[status] overall=healthy healthy=True" in stdout
    assert "Summary: all runtime checks passed" in stdout


def test_status_prints_next_steps_for_degraded_snapshot(monkeypatch, capsys):
    payload = {
        "success": True,
        "data": {
            "checked_at": "2026-02-23T08:00:00+00:00",
            "overall_healthy": False,
            "overall_status": "degraded",
            "energy": {"ok": False, "message": "unreachable"},
            "login": {
                "xhs": {"ok": False, "message": "missing a1"},
                "x": {"ok": True, "message": "ok"},
            },
            "crawler_queue": {"healthy": True, "status": "ready", "running_workers": 0, "total_workers": 2, "queued_tasks": 0},
        },
    }
    monkeypatch.setattr(
        cli,
        "_api_fetch",
        lambda *_args, **_kwargs: (200, json.dumps(payload).encode("utf-8"), {}),
    )

    code = cli._status_cmd(_status_args())

    assert code == 1
    stdout = capsys.readouterr().out
    assert "[status] overall=degraded healthy=False" in stdout
    assert "Actionable next steps:" in stdout
    assert "uv run energycrawler auth xhs-open-login" in stdout


def test_status_returns_nonzero_when_api_unreachable(monkeypatch, capsys):
    def _raise_unreachable(*_args, **_kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(cli, "_api_fetch", _raise_unreachable)

    code = cli._status_cmd(_status_args())

    assert code == 2
    stderr = capsys.readouterr().err
    assert "API unreachable" in stderr
    assert "Actionable next steps:" in stderr


def test_status_json_returns_nonzero_for_degraded_runtime(monkeypatch, capsys):
    payload = {
        "success": True,
        "data": {
            "checked_at": "2026-02-23T08:00:00+00:00",
            "overall_healthy": False,
            "overall_status": "degraded",
        },
    }
    monkeypatch.setattr(
        cli,
        "_api_fetch",
        lambda *_args, **_kwargs: (200, json.dumps(payload).encode("utf-8"), {}),
    )

    code = cli._status_cmd(_status_args(json=True))

    assert code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["data"]["overall_status"] == "degraded"


def test_status_http_error_includes_actionable_hints(monkeypatch, capsys):
    payload = {"detail": "runtime service unavailable"}
    monkeypatch.setattr(
        cli,
        "_api_fetch",
        lambda *_args, **_kwargs: (503, json.dumps(payload).encode("utf-8"), {}),
    )

    code = cli._status_cmd(_status_args())

    assert code == 1
    stderr = capsys.readouterr().err
    assert "Runtime status check failed (HTTP 503): runtime service unavailable" in stderr
    assert "Actionable next steps:" in stderr


def test_data_list_json_output_truncates_to_limit(monkeypatch, capsys):
    payload = {
        "success": True,
        "data": {
            "files": [
                {"path": "a.json", "type": "json", "modified_at": 3},
                {"path": "b.json", "type": "json", "modified_at": 2},
                {"path": "c.json", "type": "json", "modified_at": 1},
            ]
        },
    }
    monkeypatch.setattr(
        cli,
        "_api_fetch",
        lambda *_args, **_kwargs: (200, json.dumps(payload).encode("utf-8"), {}),
    )

    code = cli._data_list_cmd(_data_list_args(limit=2, json=True))

    assert code == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["total_files"] == 3
    assert data["shown"] == 2
    assert len(data["files"]) == 2


def test_data_list_invalid_limit_fails_without_calling_api(monkeypatch, capsys):
    called = {"count": 0}

    def _fake_fetch(*_args, **_kwargs):
        called["count"] += 1
        return 200, b"{}", {}

    monkeypatch.setattr(cli, "_api_fetch", _fake_fetch)

    code = cli._data_list_cmd(_data_list_args(limit=0))

    assert code == 2
    assert called["count"] == 0
    assert "--limit must be >= 1" in capsys.readouterr().err


def test_data_list_invalid_json_response_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_api_fetch", lambda *_args, **_kwargs: (200, b"not-json", {}))

    code = cli._data_list_cmd(_data_list_args())

    assert code == 1
    assert "Invalid JSON response from API" in capsys.readouterr().err
