# -*- coding: utf-8 -*-
"""
Unit tests for simplified crawler cluster manager.
"""

from collections import deque
import importlib

import pytest

from api.schemas import CrawlerStartRequest
from api.services.crawler_manager import CrawlerManager

crawler_manager_module = importlib.import_module("api.services.crawler_manager")


class _FakeStdout:
    def __init__(self):
        self._lines = deque()

    def readline(self) -> str:
        if self._lines:
            return self._lines.popleft()
        return ""

    def read(self) -> str:
        return ""


class _FakeProcess:
    def __init__(self):
        self.returncode = None
        self.stdout = _FakeStdout()

    def poll(self):
        return self.returncode

    def send_signal(self, _signal):
        self.returncode = 0

    def kill(self):
        self.returncode = -9


class _FakeProcessFactory:
    def __init__(self):
        self.processes = []

    def __call__(self, _cmd, **_kwargs):
        process = _FakeProcess()
        self.processes.append(process)
        return process


class _FailProcessFactory:
    def __call__(self, _cmd, **_kwargs):
        raise RuntimeError("spawn boom")


def _make_request() -> CrawlerStartRequest:
    return CrawlerStartRequest(
        platform="xhs",
        crawler_type="search",
        login_type="cookie",
        keywords="test keyword",
        save_option="json",
    )


@pytest.mark.asyncio
async def test_start_dispatches_to_worker_pool_and_queues_excess_tasks(monkeypatch):
    monkeypatch.setattr(crawler_manager_module, "preflight_for_platform", lambda *_args, **_kwargs: (True, "ok"))
    factory = _FakeProcessFactory()
    manager = CrawlerManager(
        max_workers=2,
        process_factory=factory,
        enable_output_reader=False,
    )

    request = _make_request()
    await manager.start(request)
    await manager.start(request)
    third = await manager.start(request)

    status = manager.get_status()
    assert third["accepted"] is True
    assert status["status"] == "running"
    assert status["running_workers"] == 2
    assert status["queued_tasks"] == 1
    assert status["total_workers"] == 2
    assert status["max_queue_size"] == 100
    assert len(status["active_task_ids"]) == 2
    assert len(status["pending_task_ids"]) == 1


@pytest.mark.asyncio
async def test_stop_terminates_running_workers_and_clears_queue(monkeypatch):
    monkeypatch.setattr(crawler_manager_module, "preflight_for_platform", lambda *_args, **_kwargs: (True, "ok"))
    factory = _FakeProcessFactory()
    manager = CrawlerManager(
        max_workers=2,
        process_factory=factory,
        enable_output_reader=False,
    )

    request = _make_request()
    await manager.start(request)
    await manager.start(request)
    await manager.start(request)

    assert await manager.stop() is True
    assert await manager.stop() is False

    status = manager.get_status()
    assert status["status"] == "idle"
    assert status["running_workers"] == 0
    assert status["queued_tasks"] == 0
    assert all(process.returncode is not None for process in factory.processes)


def test_build_command_keeps_existing_cli_contract():
    manager = CrawlerManager(max_workers=1, enable_output_reader=False)
    request = CrawlerStartRequest(
        platform="x",
        crawler_type="detail",
        login_type="cookie",
        specified_ids="123,456",
        start_page=3,
        enable_comments=False,
        enable_sub_comments=True,
        save_option="json",
        headless=True,
    )

    cmd = manager._build_command(request)
    assert cmd[:4] == ["uv", "run", "python", "main.py"]
    assert "--platform" in cmd and "x" in cmd
    assert "--type" in cmd and "detail" in cmd
    assert "--specified_id" in cmd and "123,456" in cmd
    assert "--start" in cmd and "3" in cmd
    assert "--get_comment" in cmd and "false" in cmd
    assert "--get_sub_comment" in cmd and "true" in cmd
    assert "--headless" in cmd and "true" in cmd


def test_build_command_supports_safety_limit_overrides():
    manager = CrawlerManager(max_workers=1, enable_output_reader=False)
    request = CrawlerStartRequest(
        platform="xhs",
        crawler_type="search",
        login_type="cookie",
        keywords="新能源",
        save_option="json",
        max_notes_count=8,
        crawl_sleep_sec=12.5,
    )

    cmd = manager._build_command(request)
    assert "--max_notes_count" in cmd and "8" in cmd
    assert "--crawl_sleep_sec" in cmd and "12.5" in cmd


@pytest.mark.asyncio
async def test_start_rejects_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(crawler_manager_module, "preflight_for_platform", lambda *_args, **_kwargs: (False, "energy unreachable"))
    manager = CrawlerManager(max_workers=1, enable_output_reader=False)

    result = await manager.start(_make_request())
    assert result["accepted"] is False
    assert "energy unreachable" in result["error"]
    assert manager.get_status()["status"] in {"idle", "error"}


@pytest.mark.asyncio
async def test_start_rejects_when_queue_is_full(monkeypatch):
    monkeypatch.setattr(crawler_manager_module, "preflight_for_platform", lambda *_args, **_kwargs: (True, "ok"))
    factory = _FakeProcessFactory()
    manager = CrawlerManager(
        max_workers=1,
        max_queue_size=1,
        process_factory=factory,
        enable_output_reader=False,
    )

    first = await manager.start(_make_request())
    second = await manager.start(_make_request())
    third = await manager.start(_make_request())

    assert first["accepted"] is True
    assert second["accepted"] is True
    assert third["accepted"] is False
    assert "queue is full" in third["error"].lower()


@pytest.mark.asyncio
async def test_start_rejects_new_tasks_while_stopping(monkeypatch):
    monkeypatch.setattr(crawler_manager_module, "preflight_for_platform", lambda *_args, **_kwargs: (True, "ok"))
    manager = CrawlerManager(max_workers=1, enable_output_reader=False)
    manager._stopping = True

    result = await manager.start(_make_request())
    assert result["accepted"] is False
    assert "stopping" in result["error"].lower()


@pytest.mark.asyncio
async def test_start_rejects_immediately_when_worker_spawn_fails(monkeypatch):
    monkeypatch.setattr(crawler_manager_module, "preflight_for_platform", lambda *_args, **_kwargs: (True, "ok"))
    manager = CrawlerManager(
        max_workers=1,
        process_factory=_FailProcessFactory(),
        enable_output_reader=False,
    )

    result = await manager.start(_make_request())
    status = manager.get_status()
    assert result["accepted"] is False
    assert "failed to start task" in result["error"].lower()
    assert status["queued_tasks"] == 0
    assert status["running_workers"] == 0


def test_worker_env_includes_cluster_browser_id(monkeypatch):
    monkeypatch.setenv("ENERGY_BROWSER_ID_PREFIX", "cluster")
    manager = CrawlerManager(max_workers=1, enable_output_reader=False)
    task = crawler_manager_module._QueuedTask(
        task_id="task-000123",
        config=_make_request(),
        enqueued_at=crawler_manager_module.datetime.now(),
    )

    env = manager._build_worker_env(task, worker_id=2)
    assert env["ENERGYCRAWLER_BROWSER_ID"] == "cluster_xhs_w2_task-000123"
