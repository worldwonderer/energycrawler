# -*- coding: utf-8 -*-
"""Unit tests for scheduler service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import importlib
from types import SimpleNamespace

import pytest

from api.response import ApiError
from api.schemas.scheduler import SchedulerJobCreateRequest
from api.services.scheduler_service import SchedulerService
from api.services.scheduler_store import SchedulerStore

scheduler_service_module = importlib.import_module("api.services.scheduler_service")


@pytest.mark.asyncio
async def test_scheduler_run_now_records_run(monkeypatch, tmp_path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)

    request = SchedulerJobCreateRequest(
        name="daily keyword",
        job_type="keyword",
        platform="xhs",
        interval_minutes=10,
        payload={
            "keywords": "新能源",
            "save_option": "json",
            "headless": False,
            "safety_profile": "balanced",
        },
    )
    job = await service.create_job(request)

    async def _fake_start(_req):
        return {
            "accepted": True,
            "task_id": "task-000001",
            "queued_tasks": 1,
            "running_workers": 1,
        }

    monkeypatch.setattr(scheduler_service_module.crawler_manager, "start", _fake_start)

    result = await service.run_now(job["job_id"])
    assert result["accepted"] is True
    assert result["task_id"] == "task-000001"
    assert result["run_id"] > 0

    runs = await service.list_runs(
        job_id=job["job_id"],
        status=None,
        platform=None,
        triggered_from=None,
        triggered_to=None,
        limit=10,
    )
    assert len(runs) == 1
    assert runs[0]["status"] == "queued"
    assert runs[0]["task_id"] == "task-000001"
    assert runs[0]["started_at"] is None
    assert runs[0]["finished_at"] is None
    assert runs[0]["platform"] == "xhs"

    # backward-compat call shape: keep old callers working
    compat_runs = await service.list_runs(job_id=job["job_id"], limit=10)
    assert len(compat_runs) == 1
    assert compat_runs[0]["run_id"] == runs[0]["run_id"]

    jobs = await service.list_jobs()
    assert jobs[0]["last_run_at"] is not None


@pytest.mark.asyncio
async def test_scheduler_run_lifecycle_queued_to_running_to_completed(monkeypatch, tmp_path):
    class _FakeCrawlerManager:
        def __init__(self):
            self.logs: list[SimpleNamespace] = []
            self.cluster = {
                "active_task_ids": [],
                "pending_task_ids": ["task-000010"],
            }

        async def start(self, _request):
            return {
                "accepted": True,
                "task_id": "task-000010",
                "queued_tasks": 1,
                "running_workers": 0,
            }

        def get_cluster_status(self):
            return {
                "active_task_ids": list(self.cluster["active_task_ids"]),
                "pending_task_ids": list(self.cluster["pending_task_ids"]),
            }

    fake_manager = _FakeCrawlerManager()
    monkeypatch.setattr(scheduler_service_module, "crawler_manager", fake_manager)

    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)
    job = await service.create_job(
        SchedulerJobCreateRequest(
            name="lifecycle keyword",
            job_type="keyword",
            platform="xhs",
            interval_minutes=10,
            payload={
                "keywords": "新能源",
                "save_option": "json",
                "headless": False,
                "safety_profile": "balanced",
            },
        )
    )

    await service.run_now(job["job_id"])
    queued_runs = await service.list_runs(job_id=job["job_id"], limit=10)
    assert queued_runs[0]["status"] == "queued"
    assert queued_runs[0]["started_at"] is None
    assert queued_runs[0]["finished_at"] is None

    fake_manager.cluster["pending_task_ids"] = []
    fake_manager.cluster["active_task_ids"] = ["task-000010"]
    running_runs = await service.list_runs(job_id=job["job_id"], limit=10)
    assert running_runs[0]["status"] == "running"
    assert running_runs[0]["started_at"] is not None
    assert running_runs[0]["finished_at"] is None

    fake_manager.cluster["active_task_ids"] = []
    fake_manager.logs.append(SimpleNamespace(id=901, message="[W1] Task task-000010 completed successfully"))
    completed_runs = await service.list_runs(job_id=job["job_id"], limit=10)
    assert completed_runs[0]["status"] == "completed"
    assert completed_runs[0]["finished_at"] is not None
    assert completed_runs[0]["details"]["exit_code"] == 0
    assert completed_runs[0]["details"]["terminal_log_id"] == 901
    assert "task-000010 completed successfully" in completed_runs[0]["details"]["terminal_message_excerpt"]


@pytest.mark.asyncio
async def test_scheduler_runtime_state_missing_can_be_backfilled_by_late_terminal_log(monkeypatch, tmp_path):
    class _FakeCrawlerManager:
        def __init__(self):
            self.logs: list[SimpleNamespace] = []

        async def start(self, _request):
            raise AssertionError("start should not be called in this test")

        def get_cluster_status(self):
            return {
                "active_task_ids": [],
                "pending_task_ids": [],
            }

    fake_manager = _FakeCrawlerManager()
    monkeypatch.setattr(scheduler_service_module, "crawler_manager", fake_manager)
    monkeypatch.setenv("SCHEDULER_RUN_TERMINAL_GRACE_SEC", "1")

    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)
    job = await service.create_job(
        SchedulerJobCreateRequest(
            name="late-terminal-backfill",
            job_type="keyword",
            platform="xhs",
            interval_minutes=10,
            payload={
                "keywords": "新能源",
                "save_option": "json",
                "headless": False,
                "safety_profile": "balanced",
            },
        )
    )

    run_id = await asyncio.to_thread(
        store.create_run,
        job_id=job["job_id"],
        status="queued",
        message="Crawler task queued",
        task_id="task-000283",
        triggered_at=(datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
    )

    await service._sync_run_lifecycle()  # pylint: disable=protected-access
    failed_run = await service.get_run(run_id)
    assert failed_run["status"] == "failed"
    assert failed_run["details"]["failure_reason"] == "runtime_state_missing"

    fake_manager.logs.append(SimpleNamespace(id=28301, message="[W2] Task task-000283 exited with code 3"))
    await service._sync_run_lifecycle()  # pylint: disable=protected-access

    backfilled_run = await service.get_run(run_id)
    assert backfilled_run["status"] == "failed"
    assert backfilled_run["message"] == "Crawler task failed with exit code 3"
    assert backfilled_run["details"]["exit_code"] == 3
    assert backfilled_run["details"]["terminal_log_id"] == 28301
    assert "task-000283 exited with code 3" in backfilled_run["details"]["terminal_message_excerpt"]
    assert backfilled_run["details"]["runtime_state_backfilled"] is True


@pytest.mark.asyncio
async def test_scheduler_runtime_state_missing_backfill_to_completed_clears_failure_reason(monkeypatch, tmp_path):
    class _FakeCrawlerManager:
        def __init__(self):
            self.logs: list[SimpleNamespace] = []

        async def start(self, _request):
            raise AssertionError("start should not be called in this test")

        def get_cluster_status(self):
            return {
                "active_task_ids": [],
                "pending_task_ids": [],
            }

    fake_manager = _FakeCrawlerManager()
    monkeypatch.setattr(scheduler_service_module, "crawler_manager", fake_manager)
    monkeypatch.setenv("SCHEDULER_RUN_TERMINAL_GRACE_SEC", "1")

    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)
    job = await service.create_job(
        SchedulerJobCreateRequest(
            name="late-terminal-completed-backfill",
            job_type="keyword",
            platform="xhs",
            interval_minutes=10,
            payload={
                "keywords": "新能源",
                "save_option": "json",
                "headless": False,
                "safety_profile": "balanced",
            },
        )
    )

    run_id = await asyncio.to_thread(
        store.create_run,
        job_id=job["job_id"],
        status="queued",
        message="Crawler task queued",
        task_id="task-000284",
        triggered_at=(datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
    )

    await service._sync_run_lifecycle()  # pylint: disable=protected-access
    first_failed = await service.get_run(run_id)
    assert first_failed["status"] == "failed"
    assert first_failed["details"]["failure_reason"] == "runtime_state_missing"

    fake_manager.logs.append(SimpleNamespace(id=28401, message="[W1] Task task-000284 completed successfully"))
    await service._sync_run_lifecycle()  # pylint: disable=protected-access

    completed_run = await service.get_run(run_id)
    assert completed_run["status"] == "completed"
    assert completed_run["message"] == "Crawler task completed successfully"
    assert completed_run["details"]["exit_code"] == 0
    assert completed_run["details"]["terminal_log_id"] == 28401
    assert completed_run["details"]["failure_reason"] is None
    assert completed_run["details"]["runtime_state_backfilled"] is True


@pytest.mark.asyncio
async def test_scheduler_run_now_rejected_records_failed(monkeypatch, tmp_path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)

    job = await service.create_job(
        SchedulerJobCreateRequest(
            name="reject keyword",
            job_type="keyword",
            platform="xhs",
            interval_minutes=10,
            payload={
                "keywords": "新能源",
                "save_option": "json",
                "headless": False,
                "safety_profile": "balanced",
            },
        )
    )

    async def _fake_start(_req):
        return {
            "accepted": False,
            "error": "queue full",
        }

    monkeypatch.setattr(scheduler_service_module.crawler_manager, "start", _fake_start)

    result = await service.run_now(job["job_id"])
    assert result["accepted"] is False

    runs = await service.list_runs(job_id=job["job_id"], limit=10)
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["message"] == "queue full"
    assert runs[0]["finished_at"] is not None
    assert runs[0]["details"]["exit_code"] is None
    assert runs[0]["details"]["terminal_log_id"] is None
    assert runs[0]["details"]["terminal_message_excerpt"] == "queue full"


@pytest.mark.asyncio
async def test_scheduler_tick_dispatches_due_jobs(monkeypatch, tmp_path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)

    request = SchedulerJobCreateRequest(
        name="daily kol",
        job_type="kol",
        platform="x",
        interval_minutes=30,
        payload={
            "creator_ids": "elonmusk",
            "save_option": "json",
            "headless": False,
            "safety_profile": "safe",
        },
    )
    job = await service.create_job(request)

    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await asyncio.to_thread(store.update_job, job["job_id"], {"next_run_at": past})

    call_counter = {"count": 0}

    async def _fake_start(_req):
        call_counter["count"] += 1
        return {
            "accepted": True,
            "task_id": "task-000002",
            "queued_tasks": 1,
            "running_workers": 1,
        }

    monkeypatch.setattr(scheduler_service_module.crawler_manager, "start", _fake_start)

    await service._tick()  # pylint: disable=protected-access
    assert call_counter["count"] == 1


@pytest.mark.asyncio
async def test_scheduler_clone_job_and_get_job(tmp_path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)

    source = await service.create_job(
        SchedulerJobCreateRequest(
            name="source job",
            job_type="keyword",
            platform="xhs",
            interval_minutes=15,
            payload={
                "keywords": "新能源",
                "save_option": "json",
                "headless": False,
                "safety_profile": "balanced",
            },
        )
    )

    got = await service.get_job(source["job_id"])
    assert got["job_id"] == source["job_id"]

    cloned = await service.clone_job(source["job_id"], name="source job clone")
    assert cloned["job_id"] != source["job_id"]
    assert cloned["name"] == "source job clone"
    assert cloned["payload"]["keywords"] == "新能源"


@pytest.mark.asyncio
async def test_scheduler_batch_enable_and_run_filters(tmp_path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)

    job1 = await service.create_job(
        SchedulerJobCreateRequest(
            name="job-1",
            job_type="keyword",
            platform="xhs",
            interval_minutes=10,
            payload={
                "keywords": "新能源",
                "save_option": "json",
                "headless": False,
                "safety_profile": "balanced",
            },
        )
    )
    job2 = await service.create_job(
        SchedulerJobCreateRequest(
            name="job-2",
            job_type="kol",
            platform="x",
            interval_minutes=10,
            payload={
                "creator_ids": "elonmusk",
                "save_option": "json",
                "headless": False,
                "safety_profile": "safe",
            },
        )
    )

    batch = await service.batch_set_enabled(job_ids=[job1["job_id"], job2["job_id"]], enabled=False)
    assert batch["updated"] == 2
    assert batch["enabled"] is False
    assert all(item["enabled"] is False for item in batch["jobs"])

    now = datetime.now(timezone.utc)
    await asyncio.to_thread(
        store.create_run,
        job_id=job1["job_id"],
        status="completed",
        message="ok",
        task_id="task-1",
        triggered_at=(now - timedelta(minutes=10)).isoformat(),
    )
    await asyncio.to_thread(
        store.create_run,
        job_id=job2["job_id"],
        status="failed",
        message="failed",
        task_id="task-2",
        triggered_at=(now - timedelta(minutes=5)).isoformat(),
    )

    runs = await service.list_runs(
        job_id=None,
        status="failed",
        platform="x",
        triggered_from=(now - timedelta(minutes=6)).isoformat(),
        triggered_to=(now - timedelta(minutes=1)).isoformat(),
        limit=10,
    )
    assert len(runs) == 1
    assert runs[0]["job_id"] == job2["job_id"]
    assert runs[0]["status"] == "failed"
    assert runs[0]["platform"] == "x"


@pytest.mark.asyncio
async def test_scheduler_list_runs_invalid_filter_raises(tmp_path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    service = SchedulerService(store=store, enabled=False, poll_interval_sec=1.0)

    with pytest.raises(ApiError) as exc_info:
        await service.list_runs(
            job_id=None,
            status="unknown",
            platform=None,
            triggered_from=None,
            triggered_to=None,
            limit=10,
        )
    assert exc_info.value.status_code == 422
