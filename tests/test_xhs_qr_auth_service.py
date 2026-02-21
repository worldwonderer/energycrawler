# -*- coding: utf-8 -*-
"""Unit tests for XHS QR auth service."""

from __future__ import annotations

import time

import pytest

import config
from api.services.xhs_qr_auth_service import (
    XhsQrAuthService,
    XhsQrAuthError,
    XhsQrSessionNotFoundError,
)
from energy_client.browser_interface import Cookie


class _FakeBackend:
    def __init__(self):
        self.connected = False
        self.closed_browser_ids: list[str] = []
        self.navigated_urls: list[str] = []
        self.cookies: dict[str, str] = {"a1": "guest_a1", "web_session": "guest_session"}

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def create_browser(self, browser_id: str, headless: bool = True) -> bool:
        return True

    def close_browser(self, browser_id: str) -> bool:
        self.closed_browser_ids.append(browser_id)
        return True

    def navigate(self, browser_id: str, url: str, timeout_ms: int = 30000) -> int:
        self.navigated_urls.append(url)
        return 200

    def get_cookies(self, browser_id: str, url: str):
        return [
            Cookie(name=name, value=value, domain=".xiaohongshu.com", path="/", secure=True, http_only=False)
            for name, value in self.cookies.items()
        ]

    def set_cookies(self, browser_id: str, cookies):
        for item in cookies:
            self.cookies[item.name] = item.value
        return True


@pytest.mark.asyncio
async def test_start_and_cancel_session(monkeypatch):
    service = XhsQrAuthService(session_ttl_sec=300)
    backend = _FakeBackend()
    monkeypatch.setattr(service, "_create_backend", lambda: backend)

    started = await service.start_session(headless=True)
    assert started["success"] is True
    assert started["session_id"]
    assert started["cookie_count"] >= 1

    cancelled = await service.cancel_session(started["session_id"])
    assert cancelled["success"] is True
    assert cancelled["session_id"] == started["session_id"]
    assert backend.closed_browser_ids == [started["browser_id"]]
    assert backend.connected is False


@pytest.mark.asyncio
async def test_cleanup_expired_sessions(monkeypatch):
    service = XhsQrAuthService(session_ttl_sec=60)
    backend = _FakeBackend()
    monkeypatch.setattr(service, "_create_backend", lambda: backend)

    started = await service.start_session()
    session = service._sessions[started["session_id"]]
    session.updated_at = time.time() - 120

    cleaned = await service.cleanup_expired_sessions()
    assert cleaned == 1
    assert started["session_id"] not in service._sessions


@pytest.mark.asyncio
async def test_create_and_poll_status_success_persists_cookies(monkeypatch):
    service = XhsQrAuthService(session_ttl_sec=300)
    backend = _FakeBackend()
    monkeypatch.setattr(service, "_create_backend", lambda: backend)

    started = await service.start_session()
    session_id = started["session_id"]

    async def _fake_send_signed_request(*, session, method, uri, params=None, payload=None):
        if uri == service.QRCODE_CREATE_URI:
            return {
                "success": True,
                "data": {"url": "https://qr.example.com", "qr_id": "qr_1", "code": "code_1"},
            }, {}
        if uri == service.QRCODE_STATUS_URI:
            return {
                "success": True,
                "data": {"code_status": 2, "login_info": {"user_id": "u1"}},
            }, {"web_session": "logged_session", "id_token": "token_1"}
        raise AssertionError(f"unexpected uri {uri}")

    async def _fake_sync_cookies_after_login(session, cookies_to_inject):
        assert cookies_to_inject.get("web_session") == "logged_session"
        return {"a1": "logged_a1", "webId": "web_1"}

    captured_cookie_map: dict[str, str] = {}

    def _fake_persist_cookies(cookies):
        captured_cookie_map.clear()
        captured_cookie_map.update(cookies)
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    monkeypatch.setattr(service, "_send_signed_request", _fake_send_signed_request)
    monkeypatch.setattr(service, "_sync_cookies_after_login", _fake_sync_cookies_after_login)
    monkeypatch.setattr(service, "_persist_cookies", _fake_persist_cookies)

    created = await service.create_qrcode(session_id)
    assert created["qr_id"] == "qr_1"

    status = await service.poll_status(session_id)
    assert status["login_success"] is True
    assert status["code_status"] == 2
    assert captured_cookie_map.get("a1") == "logged_a1"
    assert captured_cookie_map.get("web_session") == "logged_session"
    assert "a1=logged_a1" in config.COOKIES


@pytest.mark.asyncio
async def test_missing_session_raises_not_found():
    service = XhsQrAuthService(session_ttl_sec=300)
    with pytest.raises(XhsQrSessionNotFoundError):
        await service.create_qrcode("missing_session")


@pytest.mark.asyncio
async def test_sync_from_energy_browser_success(monkeypatch):
    service = XhsQrAuthService(session_ttl_sec=300)
    backend = _FakeBackend()
    monkeypatch.setattr(service, "_create_backend", lambda: backend)

    async def _fake_send_signed_request(*, session, method, uri, params=None, payload=None):
        assert method == "GET"
        assert uri == service.SELFINFO_URI
        return {
            "success": True,
            "data": {"result": {"success": True}},
        }, {"web_session": "logged_session"}

    async def _fake_sync_cookies_after_login(session, cookies_to_inject):
        assert cookies_to_inject.get("web_session") == "logged_session"
        return {"a1": "logged_a1", "webId": "web_1"}

    captured_cookie_map: dict[str, str] = {}

    def _fake_persist_cookies(cookies):
        captured_cookie_map.clear()
        captured_cookie_map.update(cookies)
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    monkeypatch.setattr(service, "_send_signed_request", _fake_send_signed_request)
    monkeypatch.setattr(service, "_sync_cookies_after_login", _fake_sync_cookies_after_login)
    monkeypatch.setattr(service, "_persist_cookies", _fake_persist_cookies)

    result = await service.sync_from_energy_browser("manual_login_xhs", verify_login=True)
    assert result["success"] is True
    assert result["browser_id"] == "manual_login_xhs"
    assert result["login_success"] is True
    assert captured_cookie_map.get("a1") == "logged_a1"
    assert "a1=logged_a1" in config.COOKIES
    assert backend.connected is False


@pytest.mark.asyncio
async def test_sync_from_energy_browser_login_failed(monkeypatch):
    service = XhsQrAuthService(session_ttl_sec=300)
    backend = _FakeBackend()
    monkeypatch.setattr(service, "_create_backend", lambda: backend)

    async def _fake_send_signed_request(*, session, method, uri, params=None, payload=None):
        return {
            "success": True,
            "data": {"result": {"success": False}},
        }, {}

    monkeypatch.setattr(service, "_send_signed_request", _fake_send_signed_request)

    with pytest.raises(XhsQrAuthError, match="not logged in to XHS"):
        await service.sync_from_energy_browser("manual_login_xhs", verify_login=True)
