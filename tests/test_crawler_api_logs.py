# -*- coding: utf-8 -*-
"""API tests for /api/crawler/logs observability fields and filters."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import main as api_main
from api.main import app
from api.routers import crawler as crawler_router
from api.schemas import LogEntry


class _FakeCrawlerManager:
    def __init__(self, logs):
        self.logs = logs


def _build_logs():
    return [
        LogEntry(
            id=1,
            timestamp="12:00:01",
            level="info",
            message="[QUEUE] Task accepted: task-000101 (platform=xhs, type=search)",
        ),
        LogEntry(
            id=2,
            timestamp="12:00:02",
            level="info",
            message="[W1][task-000101] crawling page 1",
        ),
        LogEntry(
            id=3,
            timestamp="12:00:03",
            level="success",
            message="[W1][task-000202] crawl completed",
        ),
        LogEntry(
            id=4,
            timestamp="12:00:04",
            level="info",
            message="[HEALTH] queue ok",
        ),
    ]


def test_crawler_logs_include_task_and_run_context(monkeypatch):
    async def _noop():
        return None

    async def _fake_list_runs(*, job_id, limit):
        assert job_id is None
        assert limit == 500
        return [
            {"run_id": 22, "task_id": "task-000202"},
            {"run_id": 11, "task_id": "task-000101"},
        ]

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setattr(crawler_router, "crawler_manager", _FakeCrawlerManager(_build_logs()))
    monkeypatch.setattr(crawler_router.scheduler_service, "list_runs", _fake_list_runs)

    client = TestClient(app)
    response = client.get("/api/crawler/logs?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    logs = payload["data"]["logs"]
    assert len(logs) == 4
    assert logs[0]["task_id"] == "task-000101"
    assert logs[0]["run_id"] == 11
    assert logs[1]["task_id"] == "task-000101"
    assert logs[1]["run_id"] == 11
    assert logs[2]["task_id"] == "task-000202"
    assert logs[2]["run_id"] == 22
    assert "task_id" not in logs[3]
    assert "run_id" not in logs[3]


def test_crawler_logs_support_task_and_run_filters(monkeypatch):
    async def _noop():
        return None

    async def _fake_list_runs(*, job_id, limit):
        _ = (job_id, limit)
        return [
            {"run_id": 22, "task_id": "task-000202"},
            {"run_id": 11, "task_id": "task-000101"},
        ]

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setattr(crawler_router, "crawler_manager", _FakeCrawlerManager(_build_logs()))
    monkeypatch.setattr(crawler_router.scheduler_service, "list_runs", _fake_list_runs)

    client = TestClient(app)

    by_task = client.get("/api/crawler/logs?task_id=task-000101")
    assert by_task.status_code == 200
    by_task_logs = by_task.json()["data"]["logs"]
    assert len(by_task_logs) == 2
    assert all(item["task_id"] == "task-000101" for item in by_task_logs)

    by_run = client.get("/api/crawler/logs?run_id=22")
    assert by_run.status_code == 200
    by_run_logs = by_run.json()["data"]["logs"]
    assert len(by_run_logs) == 1
    assert by_run_logs[0]["task_id"] == "task-000202"
    assert by_run_logs[0]["run_id"] == 22


def test_crawler_logs_support_level_filter(monkeypatch):
    async def _noop():
        return None

    async def _fake_list_runs(*, job_id, limit):
        _ = (job_id, limit)
        return []

    level_logs = [
        LogEntry(id=1, timestamp="12:30:01", level="info", message="[HEALTH] queue ok"),
        LogEntry(id=2, timestamp="12:30:02", level="warning", message="[AUTH] cookie expiring"),
        LogEntry(id=3, timestamp="12:30:03", level="error", message="[RUN] failed to enqueue"),
    ]

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setattr(crawler_router, "crawler_manager", _FakeCrawlerManager(level_logs))
    monkeypatch.setattr(crawler_router.scheduler_service, "list_runs", _fake_list_runs)

    client = TestClient(app)

    filtered = client.get("/api/crawler/logs?level=warning,error")
    assert filtered.status_code == 200
    filtered_logs = filtered.json()["data"]["logs"]
    assert len(filtered_logs) == 2
    assert {item["level"] for item in filtered_logs} == {"warning", "error"}

    info_only = client.get("/api/crawler/logs?level=INFO")
    assert info_only.status_code == 200
    info_logs = info_only.json()["data"]["logs"]
    assert len(info_logs) == 1
    assert info_logs[0]["level"] == "info"
