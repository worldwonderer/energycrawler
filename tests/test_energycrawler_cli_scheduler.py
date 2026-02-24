# -*- coding: utf-8 -*-
"""Tests for scheduler commands in unified CLI."""

from __future__ import annotations

import argparse
import json

from scripts import energycrawler_cli as cli


def test_parser_includes_scheduler_commands():
    parser = cli._build_parser()

    args = parser.parse_args(["scheduler", "list"])
    assert args.command == "scheduler"
    assert args.scheduler_command == "list"
    assert args.handler is cli._scheduler_list_cmd

    create_args = parser.parse_args(
        [
            "scheduler",
            "create-keyword",
            "--name",
            "daily",
            "--interval-minutes",
            "30",
            "--keywords",
            "新能源",
        ]
    )
    assert create_args.command == "scheduler"
    assert create_args.scheduler_command == "create-keyword"
    assert create_args.handler is cli._scheduler_create_keyword_cmd

    smoke_args = parser.parse_args(["scheduler", "smoke-e2e"])
    assert smoke_args.command == "scheduler"
    assert smoke_args.scheduler_command == "smoke-e2e"
    assert smoke_args.handler is cli._scheduler_smoke_e2e_cmd


def test_scheduler_create_keyword_cmd_json(monkeypatch, capsys):
    fake_payload = {
        "success": True,
        "data": {
            "job_id": "job-001",
            "name": "daily",
            "job_type": "keyword",
            "platform": "xhs",
            "interval_minutes": 30,
            "enabled": True,
            "payload": {"keywords": "新能源"},
            "next_run_at": "2026-02-23T00:00:00+00:00",
            "last_run_at": None,
            "created_at": "2026-02-23T00:00:00+00:00",
            "updated_at": "2026-02-23T00:00:00+00:00",
        },
        "message": "Scheduler job created",
    }

    monkeypatch.setattr(
        cli,
        "_scheduler_call",
        lambda **_kwargs: (200, fake_payload),
    )

    args = argparse.Namespace(
        name="daily",
        platform="xhs",
        interval_minutes=30,
        keywords="新能源",
        safety_profile="balanced",
        save_option="json",
        max_notes_count=None,
        crawl_sleep_sec=None,
        headless=False,
        enabled=True,
        api_base="http://127.0.0.1:8080",
        timeout=15.0,
        json=True,
    )
    code = cli._scheduler_create_keyword_cmd(args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["job_id"] == "job-001"


def test_scheduler_run_now_cmd_text(monkeypatch, capsys):
    fake_payload = {
        "success": True,
        "data": {
            "accepted": True,
            "task_id": "task-000009",
            "message": "Crawler task accepted",
            "run_id": 9,
        },
        "message": "Scheduler job triggered",
    }
    monkeypatch.setattr(cli, "_scheduler_call", lambda **_kwargs: (200, fake_payload))

    args = argparse.Namespace(
        job_id="job-009",
        api_base="http://127.0.0.1:8080",
        timeout=15.0,
        json=False,
    )
    code = cli._scheduler_run_now_cmd(args)
    assert code == 0
    output = capsys.readouterr().out
    assert "accepted=True" in output
    assert "task_id=task-000009" in output


def test_scheduler_smoke_e2e_cmd_success(monkeypatch, capsys):
    call_log: list[tuple[str, str, str | None]] = []

    def _fake_scheduler_call(*, endpoint, method="GET", payload=None, **_kwargs):
        call_log.append((method, endpoint, (payload or {}).get("job_type") if isinstance(payload, dict) else None))

        if endpoint == "/api/health/runtime":
            return 200, {"success": True, "data": {"overall_healthy": True, "overall_status": "healthy"}}

        if endpoint == "/api/scheduler/jobs" and method == "POST":
            job_type = str(payload.get("job_type"))
            return 200, {"success": True, "data": {"job_id": f"job-{job_type}"}}

        if endpoint == "/api/scheduler/jobs/job-keyword/run-now" and method == "POST":
            return 200, {"success": True, "data": {"run_id": 101, "task_id": "task-101", "accepted": True}}

        if endpoint == "/api/scheduler/jobs/job-kol/run-now" and method == "POST":
            return 200, {"success": True, "data": {"run_id": 102, "task_id": "task-102", "accepted": True}}

        if endpoint in {"/api/scheduler/jobs/job-keyword", "/api/scheduler/jobs/job-kol"} and method == "DELETE":
            return 200, {"success": True, "data": {"deleted": True}}

        raise AssertionError(f"unexpected scheduler call: method={method} endpoint={endpoint} payload={payload}")

    snapshot_counter = {"count": 0}

    def _fake_fetch_snapshot(**_kwargs):
        if snapshot_counter["count"] == 0:
            snapshot_counter["count"] += 1
            return [{"path": "xhs/json/a.json", "modified_at": 10.0}], {"xhs/json/a.json": 10.0}
        return [{"path": "xhs/json/a.json", "modified_at": 20.0}], {"xhs/json/a.json": 20.0}

    def _fake_poll_run(**kwargs):
        run_id = int(kwargs["run_id"])
        task_id = f"task-{run_id}"
        return (
            {"run_id": run_id, "status": "completed", "task_id": task_id, "message": "ok"},
            [{"status": "running"}, {"status": "completed"}],
            False,
        )

    monkeypatch.setattr(cli, "_scheduler_call", _fake_scheduler_call)
    monkeypatch.setattr(cli, "_scheduler_fetch_files_snapshot", _fake_fetch_snapshot)
    monkeypatch.setattr(cli, "_scheduler_poll_run_until_terminal", _fake_poll_run)
    monkeypatch.setattr(cli, "_scheduler_fetch_run_logs", lambda **_kwargs: [{"id": 1, "message": "ok"}])
    monkeypatch.setattr(
        cli,
        "_scheduler_fetch_latest_preview",
        lambda **_kwargs: {"file": {"path": "xhs/json/a.json"}, "total": 1, "data": [{"id": 1}]},
    )
    monkeypatch.setattr(cli.time, "sleep", lambda *_args, **_kwargs: None)

    args = argparse.Namespace(
        api_base="http://127.0.0.1:8080",
        platform="xhs",
        keywords="新能源,储能",
        creator_ids="60d5b32a000000002002cf79",
        interval_minutes=60,
        safety_profile="safe",
        save_option="json",
        max_notes_count=5,
        crawl_sleep_sec=1.2,
        headless=True,
        poll_interval=0.1,
        run_timeout=5.0,
        settle_sec=0.0,
        logs_limit=50,
        preview_limit=5,
        require_data_change=True,
        keep_jobs=False,
        timeout=5.0,
        json=False,
    )

    code = cli._scheduler_smoke_e2e_cmd(args)
    assert code == 0

    stdout = capsys.readouterr().out
    assert "[scheduler smoke-e2e] runtime overall=healthy healthy=True" in stdout
    assert "keyword run_id=101 status=completed" in stdout
    assert "kol run_id=102 status=completed" in stdout

    delete_calls = [item for item in call_log if item[0] == "DELETE"]
    assert len(delete_calls) == 2
