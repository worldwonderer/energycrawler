# -*- coding: utf-8 -*-
"""API tests for XHS QR auth routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routers import auth as auth_router_module
from api.services.xhs_qr_auth_service import XhsQrAuthError, XhsQrSessionNotFoundError


class _FakeQrService:
    async def start_session(self, headless=None):
        return {
            "success": True,
            "session_id": "s1",
            "browser_id": "qr_login_xhs_s1",
            "cookie_count": 2,
        }

    async def create_qrcode(self, session_id: str):
        if session_id == "missing":
            raise XhsQrSessionNotFoundError("session not found")
        return {
            "success": True,
            "session_id": session_id,
            "qr_url": "https://qr.example.com",
            "qr_id": "qr_1",
            "code": "code_1",
            "expires_in_sec": 300,
        }

    async def poll_status(self, session_id: str):
        if session_id == "missing":
            raise XhsQrSessionNotFoundError("session not found")
        return {
            "success": True,
            "session_id": session_id,
            "code_status": 0,
            "login_success": False,
            "qr_id": "qr_1",
            "cookie_count": 2,
            "login_info": None,
            "message": "waiting",
        }

    async def cancel_session(self, session_id: str):
        if session_id == "missing":
            raise XhsQrSessionNotFoundError("session not found")
        return {"success": True, "session_id": session_id, "message": "session cancelled"}

    async def sync_from_energy_browser(self, browser_id: str, verify_login: bool = True):
        if browser_id == "missing":
            raise XhsQrAuthError("browser not logged in")
        return {
            "success": True,
            "browser_id": browser_id,
            "login_success": verify_login,
            "cookie_count": 13,
            "message": "synced_from_energy_browser",
        }


def test_qr_auth_routes_success(monkeypatch):
    monkeypatch.setattr(auth_router_module, "qr_auth_service", _FakeQrService())
    client = TestClient(app)

    start_resp = client.post("/api/auth/xhs/qr/session/start", json={"headless": True})
    assert start_resp.status_code == 200
    assert start_resp.json()["session_id"] == "s1"

    qr_resp = client.post("/api/auth/xhs/qr/session/s1/qrcode")
    assert qr_resp.status_code == 200
    assert qr_resp.json()["qr_id"] == "qr_1"

    status_resp = client.get("/api/auth/xhs/qr/session/s1/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["code_status"] == 0

    cancel_resp = client.post("/api/auth/xhs/qr/session/s1/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["message"] == "session cancelled"


def test_qr_auth_routes_not_found(monkeypatch):
    monkeypatch.setattr(auth_router_module, "qr_auth_service", _FakeQrService())
    client = TestClient(app)

    qr_resp = client.post("/api/auth/xhs/qr/session/missing/qrcode")
    assert qr_resp.status_code == 404

    status_resp = client.get("/api/auth/xhs/qr/session/missing/status")
    assert status_resp.status_code == 404

    cancel_resp = client.post("/api/auth/xhs/qr/session/missing/cancel")
    assert cancel_resp.status_code == 404


def test_energy_sync_route_success(monkeypatch):
    monkeypatch.setattr(auth_router_module, "qr_auth_service", _FakeQrService())
    client = TestClient(app)

    resp = client.post(
        "/api/auth/xhs/energy/sync",
        json={"browser_id": "manual_login_xhs", "verify_login": True},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["browser_id"] == "manual_login_xhs"
    assert payload["message"] == "synced_from_energy_browser"


def test_energy_sync_route_failed(monkeypatch):
    monkeypatch.setattr(auth_router_module, "qr_auth_service", _FakeQrService())
    client = TestClient(app)

    resp = client.post(
        "/api/auth/xhs/energy/sync",
        json={"browser_id": "missing", "verify_login": True},
    )
    assert resp.status_code == 400
