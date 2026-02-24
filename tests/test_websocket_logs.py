# -*- coding: utf-8 -*-
"""Tests for /api/ws/logs message enrichment."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from api import main as api_main
from api.main import app
from api.routers import websocket as websocket_router
from api.schemas import LogEntry


class _FakeCrawlerManager:
    def __init__(self, logs):
        self.logs = logs
        self._queue = asyncio.Queue()

    def get_log_queue(self):
        return self._queue


def _patch_ws_runtime(monkeypatch, *, logs):
    async def _noop():
        return None

    async def _fake_list_runs(*, job_id, limit):
        _ = (job_id, limit)
        return []

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)
    monkeypatch.setattr(websocket_router, "crawler_manager", _FakeCrawlerManager(logs))
    monkeypatch.setattr(websocket_router.scheduler_service, "list_runs", _fake_list_runs)
    monkeypatch.setattr(websocket_router, "start_broadcaster", lambda: None)
    monkeypatch.setattr(websocket_router, "manager", websocket_router.ConnectionManager())
    monkeypatch.setattr(websocket_router, "_TASK_TO_RUN_ID_CACHE", {})
    monkeypatch.setattr(websocket_router, "_TASK_TO_RUN_ID_CACHE_SYNC_AT_MONOTONIC", 0.0)
    monkeypatch.setattr(websocket_router, "_WS_ACTIVE_CONNECTIONS", 0)


def test_ws_logs_include_task_id_and_run_id(monkeypatch):
    async def _fake_list_runs(*, job_id, limit):
        _ = (job_id, limit)
        return [
            {"run_id": 901, "task_id": "task-000321"},
        ]

    logs = [
        LogEntry(
            id=1,
            timestamp="12:10:01",
            level="info",
            message="[W1][task-000321] scraping started",
        ),
        LogEntry(
            id=2,
            timestamp="12:10:02",
            level="warning",
            message="[AUTH] CookieCloud sync failed",
        ),
    ]

    _patch_ws_runtime(monkeypatch, logs=logs)
    monkeypatch.setattr(websocket_router.scheduler_service, "list_runs", _fake_list_runs)

    client = TestClient(app)
    with client.websocket_connect("/api/ws/logs") as ws:
        first = ws.receive_json()
        second = ws.receive_json()

    assert first["id"] == 1
    assert first["message"].startswith("[W1][task-000321]")
    assert first["task_id"] == "task-000321"
    assert first["run_id"] == 901
    assert {"id", "timestamp", "level", "message"}.issubset(first.keys())

    assert second["id"] == 2
    assert "task_id" not in second
    assert "run_id" not in second


def test_ws_logs_reject_unauthorized_when_auth_enabled(monkeypatch):
    _patch_ws_runtime(monkeypatch, logs=[])
    monkeypatch.setenv("WEBSOCKET_REQUIRE_AUTH", "true")
    monkeypatch.setenv("WEBSOCKET_ADMIN_TOKEN", "ws-secret")

    client = TestClient(app)

    with client.websocket_connect("/api/ws/logs") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_text()
    assert exc_info.value.code == 1008

    with client.websocket_connect("/api/ws/logs?token=ws-secret") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_ws_logs_respect_connection_limit(monkeypatch):
    _patch_ws_runtime(monkeypatch, logs=[])
    monkeypatch.setenv("WEBSOCKET_MAX_CONNECTIONS", "1")

    client = TestClient(app)

    with client.websocket_connect("/api/ws/logs") as primary:
        with client.websocket_connect("/api/ws/logs") as overflow:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                overflow.receive_text()
        assert exc_info.value.code == 1013

        primary.send_text("ping")
        assert primary.receive_text() == "pong"
