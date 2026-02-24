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
    assert "EnergyCrawler UI 2.0" in response.text
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


def test_app_shell_registers_welcome_route_and_first_run_default(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui/src/app-shell.js")
    assert response.status_code == 200
    assert 'id: "welcome"' in response.text
    assert 'hash: "#/welcome"' in response.text
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
    assert "环境健康 (Env Health)" in response.text
    assert "Demo Run" in response.text
    assert "#/runtime" in response.text
    assert "#/data" in response.text


def test_runtime_page_has_welcome_entry_link(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui/src/pages/runtime.js")
    assert response.status_code == 200
    assert 'href="#/welcome"' in response.text
    assert "Welcome 引导" in response.text


def test_dashboard_jump_to_runs_uses_query_params(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(api_main.scheduler_service, "start", _noop)
    monkeypatch.setattr(api_main.scheduler_service, "stop", _noop)

    client = TestClient(app)
    response = client.get("/ui/src/pages/dashboard.js")
    assert response.status_code == 200
    assert "buildRunsJumpHash" in response.text
    assert 'params.set("status", "failed")' in response.text
    assert 'params.set("limit", String(DEFAULT_RUN_LIMIT))' in response.text
    assert 'window.location.hash = buildRunsJumpHash(state.runs)' in response.text


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
