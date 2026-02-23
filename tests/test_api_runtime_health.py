# -*- coding: utf-8 -*-
"""API tests for /api/health/runtime snapshot."""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from api import main as api_main
from api.main import app


def test_runtime_health_snapshot_healthy(monkeypatch):
    monkeypatch.setattr(api_main, "check_energy_service_reachable", lambda: (True, "Energy service reachable"))
    monkeypatch.setattr(api_main.runtime_config, "COOKIES", "a1=abc", raising=False)
    monkeypatch.setattr(api_main.runtime_config, "TWITTER_AUTH_TOKEN", "token", raising=False)
    monkeypatch.setattr(api_main.runtime_config, "TWITTER_CT0", "ct0", raising=False)
    monkeypatch.setattr(api_main.runtime_config, "TWITTER_COOKIE", "", raising=False)
    monkeypatch.setattr(
        api_main.crawler_manager,
        "get_cluster_status",
        lambda: {
            "status": "running",
            "running_workers": 1,
            "total_workers": 2,
            "queued_tasks": 1,
            "max_queue_size": 100,
            "active_task_ids": ["task-000001"],
            "pending_task_ids": ["task-000002"],
        },
    )

    client = TestClient(app)
    response = client.get("/api/health/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Runtime health snapshot"

    data = payload["data"]
    datetime.fromisoformat(data["checked_at"])
    assert data["overall_healthy"] is True
    assert data["overall_status"] == "healthy"
    assert data["energy"]["ok"] is True
    assert data["login"]["xhs"]["ok"] is True
    assert data["login"]["x"]["ok"] is True
    assert data["crawler_queue"]["healthy"] is True
    assert data["crawler_queue"]["active_task_ids"] == ["task-000001"]


def test_runtime_health_snapshot_degraded(monkeypatch):
    monkeypatch.setattr(api_main, "check_energy_service_reachable", lambda: (False, "Energy service unreachable"))
    monkeypatch.setattr(api_main.runtime_config, "COOKIES", "", raising=False)
    monkeypatch.setattr(api_main.runtime_config, "TWITTER_AUTH_TOKEN", "", raising=False)
    monkeypatch.setattr(api_main.runtime_config, "TWITTER_CT0", "", raising=False)
    monkeypatch.setattr(api_main.runtime_config, "TWITTER_COOKIE", "", raising=False)
    monkeypatch.setattr(
        api_main.crawler_manager,
        "get_cluster_status",
        lambda: {
            "status": "error",
            "running_workers": 0,
            "total_workers": 2,
            "queued_tasks": 0,
            "max_queue_size": 100,
            "active_task_ids": [],
            "pending_task_ids": [],
        },
    )

    client = TestClient(app)
    response = client.get("/api/health/runtime")

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]

    assert data["overall_healthy"] is False
    assert data["overall_status"] == "degraded"
    assert data["energy"] == {"ok": False, "message": "Energy service unreachable"}
    assert data["login"]["xhs"]["ok"] is False
    assert data["login"]["x"]["ok"] is False
    assert data["crawler_queue"]["healthy"] is False
    assert data["crawler_queue"]["status"] == "error"
