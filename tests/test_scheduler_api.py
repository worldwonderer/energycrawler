# -*- coding: utf-8 -*-
"""API tests for scheduler endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import main as api_main
from api.main import app
from api.routers import diagnostics as diagnostics_router_module


def _reset_diagnostics_state() -> None:
    diagnostics_router_module._smoke_state.update(
        {
            "running": False,
            "run_id": 0,
            "current_run": None,
            "latest": None,
        }
    )


def test_scheduler_create_and_list(monkeypatch):
    async def _noop():
        return None

    async def _fake_create(request):
        return {
            "job_id": "job-123",
            "name": request.name,
            "job_type": request.job_type.value,
            "platform": request.platform.value,
            "interval_minutes": request.interval_minutes,
            "enabled": request.enabled,
            "payload": request.payload,
            "next_run_at": "2026-02-23T00:00:00+00:00",
            "last_run_at": None,
            "created_at": "2026-02-23T00:00:00+00:00",
            "updated_at": "2026-02-23T00:00:00+00:00",
        }

    async def _fake_list():
        return [
            {
                "job_id": "job-123",
                "name": "daily keyword",
                "job_type": "keyword",
                "platform": "xhs",
                "interval_minutes": 30,
                "enabled": True,
                "payload": {"keywords": "新能源"},
                "next_run_at": "2026-02-23T00:00:00+00:00",
                "last_run_at": None,
                "created_at": "2026-02-23T00:00:00+00:00",
                "updated_at": "2026-02-23T00:00:00+00:00",
            }
        ]

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "create_job", _fake_create)
    monkeypatch.setattr(api_main.scheduler_service, "list_jobs", _fake_list)

    client = TestClient(app)
    create_resp = client.post(
        "/api/scheduler/jobs",
        json={
            "name": "daily keyword",
            "job_type": "keyword",
            "platform": "xhs",
            "interval_minutes": 30,
            "payload": {"keywords": "新能源", "save_option": "json"},
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["success"] is True
    assert create_resp.json()["data"]["job_id"] == "job-123"

    list_resp = client.get("/api/scheduler/jobs")
    assert list_resp.status_code == 200
    assert list_resp.json()["success"] is True
    assert len(list_resp.json()["data"]["jobs"]) == 1


def test_scheduler_run_now(monkeypatch):
    async def _noop():
        return None

    async def _fake_run_now(_job_id):
        return {
            "accepted": True,
            "task_id": "task-000003",
            "message": "Crawler task accepted",
            "run_id": 33,
        }

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "run_now", _fake_run_now)

    client = TestClient(app)
    response = client.post("/api/scheduler/jobs/job-abc/run-now")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["accepted"] is True
    assert payload["data"]["task_id"] == "task-000003"


def test_scheduler_job_detail_clone_batch_enable(monkeypatch):
    async def _noop():
        return None

    async def _fake_get_job(job_id):
        return {
            "job_id": job_id,
            "name": "daily keyword",
            "job_type": "keyword",
            "platform": "xhs",
            "interval_minutes": 30,
            "enabled": True,
            "payload": {"keywords": "新能源"},
        }

    async def _fake_clone_job(job_id, *, name=None):
        return {
            "job_id": "job-clone-001",
            "name": name or "daily keyword (copy)",
            "source_job_id": job_id,
            "job_type": "keyword",
            "platform": "xhs",
            "interval_minutes": 30,
            "enabled": True,
            "payload": {"keywords": "新能源"},
        }

    async def _fake_batch_set_enabled(*, job_ids, enabled):
        return {
            "updated": len(job_ids),
            "enabled": enabled,
            "jobs": [{"job_id": job_id, "enabled": enabled} for job_id in job_ids],
        }

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "get_job", _fake_get_job)
    monkeypatch.setattr(api_main.scheduler_service, "clone_job", _fake_clone_job)
    monkeypatch.setattr(api_main.scheduler_service, "batch_set_enabled", _fake_batch_set_enabled)

    client = TestClient(app)

    detail_resp = client.get("/api/scheduler/jobs/job-abc")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["success"] is True
    assert detail_resp.json()["data"]["job_id"] == "job-abc"

    clone_resp = client.post(
        "/api/scheduler/jobs/job-abc/clone",
        json={"name": "daily keyword clone"},
    )
    assert clone_resp.status_code == 200
    assert clone_resp.json()["success"] is True
    assert clone_resp.json()["data"]["job_id"] == "job-clone-001"
    assert clone_resp.json()["data"]["name"] == "daily keyword clone"

    batch_resp = client.post(
        "/api/scheduler/jobs/batch-enable",
        json={"job_ids": ["job-abc", "job-def"], "enabled": False},
    )
    assert batch_resp.status_code == 200
    assert batch_resp.json()["success"] is True
    assert batch_resp.json()["data"]["updated"] == 2
    assert batch_resp.json()["data"]["enabled"] is False


def test_scheduler_run_detail_and_filtered_runs(monkeypatch):
    async def _noop():
        return None

    async def _fake_get_run(run_id):
        return {
            "run_id": run_id,
            "job_id": "job-abc",
            "triggered_at": "2026-02-23T00:00:00+00:00",
            "status": "running",
            "task_id": "task-000005",
            "message": "running",
            "details": {"trigger_reason": "manual"},
            "platform": "xhs",
        }

    captured = {}

    async def _fake_list_runs(
        *,
        job_id,
        status,
        platform,
        triggered_from,
        triggered_to,
        limit,
    ):
        captured.update(
            {
                "job_id": job_id,
                "status": status,
                "platform": platform,
                "triggered_from": triggered_from,
                "triggered_to": triggered_to,
                "limit": limit,
            }
        )
        return [
            {
                "run_id": 101,
                "job_id": "job-abc",
                "triggered_at": "2026-02-23T00:00:00+00:00",
                "status": status or "running",
                "task_id": "task-000005",
                "message": "running",
                "details": {},
                "platform": platform or "xhs",
            }
        ]

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "get_run", _fake_get_run)
    monkeypatch.setattr(api_main.scheduler_service, "list_runs", _fake_list_runs)

    client = TestClient(app)

    detail_resp = client.get("/api/scheduler/runs/101")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["success"] is True
    assert detail_resp.json()["data"]["run_id"] == 101

    list_resp = client.get(
        "/api/scheduler/runs",
        params={
            "job_id": "job-abc",
            "status": "running",
            "platform": "xhs",
            "from": "2026-02-22T00:00:00Z",
            "to": "2026-02-24T00:00:00Z",
            "limit": 10,
        },
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["success"] is True
    assert len(list_resp.json()["data"]["runs"]) == 1
    assert captured == {
        "job_id": "job-abc",
        "status": "running",
        "platform": "xhs",
        "triggered_from": "2026-02-22T00:00:00Z",
        "triggered_to": "2026-02-24T00:00:00Z",
        "limit": 10,
    }


def test_diagnostics_smoke_e2e_start_and_latest(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    scheduled = {"count": 0}

    def _fake_create_task(coro):
        scheduled["count"] += 1
        coro.close()

        class _Task:
            def done(self):
                return True

        return _Task()

    monkeypatch.setattr(diagnostics_router_module.asyncio, "create_task", _fake_create_task)

    _reset_diagnostics_state()
    try:
        client = TestClient(app)

        start_resp = client.post("/api/diagnostics/smoke-e2e/start")
        assert start_resp.status_code == 200
        start_payload = start_resp.json()
        assert start_payload["success"] is True
        assert start_payload["data"]["accepted"] is True
        assert start_payload["data"]["running"] is True
        assert start_payload["data"]["current_run"]["run_id"] == 1
        assert scheduled["count"] == 1

        latest_resp = client.get("/api/diagnostics/smoke-e2e/latest")
        assert latest_resp.status_code == 200
        latest_payload = latest_resp.json()
        assert latest_payload["success"] is True
        assert latest_payload["data"]["running"] is True
        assert latest_payload["data"]["current_run"]["run_id"] == 1
        assert latest_payload["data"]["latest"] is None
    finally:
        _reset_diagnostics_state()


def test_diagnostics_smoke_e2e_start_returns_running_snapshot(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    def _unexpected_create_task(coro):
        coro.close()
        raise AssertionError("create_task should not be called while diagnostics run is in progress")

    monkeypatch.setattr(diagnostics_router_module.asyncio, "create_task", _unexpected_create_task)

    _reset_diagnostics_state()
    diagnostics_router_module._smoke_state.update(
        {
            "running": True,
            "run_id": 3,
            "current_run": {
                "run_id": 3,
                "command": "energycrawler scheduler smoke-e2e --json",
                "started_at": "2026-02-23T00:00:00+00:00",
            },
            "latest": {
                "run_id": 2,
                "ok": True,
            },
        }
    )

    try:
        client = TestClient(app)
        response = client.post("/api/diagnostics/smoke-e2e/start")

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["accepted"] is False
        assert payload["data"]["running"] is True
        assert payload["data"]["current_run"]["run_id"] == 3
        assert payload["data"]["latest"]["run_id"] == 2
    finally:
        _reset_diagnostics_state()


def test_diagnostics_smoke_e2e_requires_token_when_enabled(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setenv("DIAGNOSTICS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("DIAGNOSTICS_ADMIN_TOKEN", "diag-secret")

    scheduled = {"count": 0}

    def _fake_create_task(coro):
        scheduled["count"] += 1
        coro.close()

        class _Task:
            def done(self):
                return True

        return _Task()

    monkeypatch.setattr(diagnostics_router_module.asyncio, "create_task", _fake_create_task)

    _reset_diagnostics_state()
    try:
        client = TestClient(app)

        unauthorized_start = client.post("/api/diagnostics/smoke-e2e/start")
        assert unauthorized_start.status_code == 401
        assert unauthorized_start.json()["success"] is False
        assert unauthorized_start.json()["error"]["code"] == "UNAUTHORIZED"

        wrong_token_start = client.post(
            "/api/diagnostics/smoke-e2e/start",
            headers={"x-admin-token": "wrong-token"},
        )
        assert wrong_token_start.status_code == 401

        authorized_start = client.post(
            "/api/diagnostics/smoke-e2e/start",
            headers={"x-admin-token": "diag-secret"},
        )
        assert authorized_start.status_code == 200
        assert authorized_start.json()["success"] is True
        assert authorized_start.json()["data"]["accepted"] is True
        assert scheduled["count"] == 1

        unauthorized_latest = client.get("/api/diagnostics/smoke-e2e/latest")
        assert unauthorized_latest.status_code == 401

        authorized_latest = client.get(
            "/api/diagnostics/smoke-e2e/latest",
            params={"token": "diag-secret"},
        )
        assert authorized_latest.status_code == 200
        assert authorized_latest.json()["success"] is True
    finally:
        _reset_diagnostics_state()
