# -*- coding: utf-8 -*-
"""Tests for bundled web UI static routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import main as api_main
from api.main import app


def test_web_ui_index_served(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui")
    assert response.status_code == 200
    assert "EnergyCrawler 用户任务中心" in response.text
    assert "moduleNav" in response.text
    assert "/ui/src/main.js" in response.text


def test_web_ui_assets_served(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui/src/main.js")
    assert response.status_code == 200
    assert "AppShell" in response.text


def test_app_shell_registers_user_flow_routes_and_first_run_default(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui/src/app-shell.js")
    assert response.status_code == 200
    assert 'id: "welcome"' in response.text
    assert 'hash: "#/welcome"' in response.text
    assert 'id: "scheduler"' in response.text
    assert 'id: "runs"' in response.text
    assert 'id: "data"' in response.text
    assert 'id: "settings"' in response.text
    assert 'id: "dashboard"' not in response.text
    assert 'id: "runtime"' not in response.text
    assert "this.defaultRouteId" in response.text
    assert "ONBOARDING_COMPLETED_STORAGE_KEY" in response.text


def test_welcome_page_module_served(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui/src/pages/welcome.js")
    assert response.status_code == 200
    assert "mountWelcomePage" in response.text
    assert "3 步完成首次上手" in response.text
    assert "连接检查" in response.text
    assert "登录就绪" in response.text
    assert "创建首个任务" in response.text
    assert "#/runs" in response.text
    assert "#/settings" in response.text
    assert "#/data" in response.text


def test_runs_page_module_exposes_quick_entries_and_feedback(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui/src/pages/runs.js")
    assert response.status_code == 200
    assert 'data-action="open-data-page"' in response.text
    assert 'data-action="open-scheduler-page"' in response.text
    assert 'data-action="focus-latest-run"' in response.text
    assert "已筛选状态" in response.text
    assert "已清空筛选条件" in response.text


def test_data_page_supports_hash_filter_prefill(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui/src/pages/data.js")
    assert response.status_code == 200
    assert "parseHashQueryParams" in response.text
    assert "applyFiltersFromHash" in response.text
    assert 'params.get("file_type")' in response.text
    assert "setFormControlValue(filesForm, \"platform\"" in response.text
