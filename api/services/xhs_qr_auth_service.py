# -*- coding: utf-8 -*-
"""XHS QR login service based on Energy browser runtime."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

import config
from energy_client.browser_interface import Cookie, EnergyBrowserBackend
from media_platform.xhs.energy_client_adapter import XHSEnergyAdapter
from tools import utils
from tools.env_store import upsert_env_values
from tools.preflight import parse_energy_service_address


class XhsQrAuthError(RuntimeError):
    """Base error for XHS QR auth flow."""


class XhsQrSessionNotFoundError(XhsQrAuthError):
    """Raised when session id is unknown or expired."""


@dataclass
class _QrSession:
    session_id: str
    browser_id: str
    backend: EnergyBrowserBackend
    cookies: Dict[str, str] = field(default_factory=dict)
    qr_id: Optional[str] = None
    qr_code: Optional[str] = None
    qr_url: Optional[str] = None
    code_status: int = -1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    op_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class XhsQrAuthService:
    """Provides QR login session APIs for XHS."""

    XHS_HOME_URL = "https://www.xiaohongshu.com/"
    XHS_HOST = "https://edith.xiaohongshu.com"
    QRCODE_CREATE_URI = "/api/sns/web/v1/login/qrcode/create"
    QRCODE_STATUS_URI = "/api/sns/web/v1/login/qrcode/status"
    SELFINFO_URI = "/api/sns/web/v1/user/selfinfo"

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, session_ttl_sec: int = 300):
        self._session_ttl_sec = max(60, int(session_ttl_sec))
        self._sessions: Dict[str, _QrSession] = {}
        self._lock = asyncio.Lock()
        self._project_root = Path(__file__).resolve().parents[2]
        self._env_path = self._project_root / ".env"

    async def start_session(self, headless: Optional[bool] = None) -> Dict[str, Any]:
        await self.cleanup_expired_sessions()

        session_id = uuid.uuid4().hex
        browser_id = f"qr_login_xhs_{session_id[:12]}"
        backend = self._create_backend()

        try:
            backend.connect()
            created = backend.create_browser(
                browser_id=browser_id,
                headless=config.ENERGY_HEADLESS if headless is None else bool(headless),
            )
            if not created:
                raise XhsQrAuthError("failed to create browser instance")

            backend.navigate(browser_id, self.XHS_HOME_URL, timeout_ms=60000)
            cookies = self._get_browser_cookie_map(backend, browser_id)
        except Exception as exc:
            self._close_session_resources(
                _QrSession(session_id=session_id, browser_id=browser_id, backend=backend)
            )
            raise XhsQrAuthError(f"failed to initialize QR session: {exc}") from exc

        session = _QrSession(
            session_id=session_id,
            browser_id=browser_id,
            backend=backend,
            cookies=cookies,
        )
        async with self._lock:
            self._sessions[session_id] = session

        utils.log_event(
            "xhs.qr.session.started",
            session_id=session_id,
            browser_id=browser_id,
            cookie_count=len(cookies),
        )

        return {
            "success": True,
            "session_id": session_id,
            "browser_id": browser_id,
            "cookie_count": len(cookies),
        }

    async def create_qrcode(self, session_id: str) -> Dict[str, Any]:
        session = await self._require_session(session_id)
        async with session.op_lock:
            payload = {"qr_type": 1}
            data, _ = await self._send_signed_request(
                session=session,
                method="POST",
                uri=self.QRCODE_CREATE_URI,
                payload=payload,
            )

            if not data.get("success"):
                raise XhsQrAuthError(data.get("msg", "qrcode create failed"))

            response_data = data.get("data") or {}
            qr_url = response_data.get("url")
            qr_id = response_data.get("qr_id")
            code = response_data.get("code")
            if not (qr_url and qr_id and code):
                raise XhsQrAuthError("qrcode create response missing url/qr_id/code")

            session.qr_url = qr_url
            session.qr_id = qr_id
            session.qr_code = code
            session.code_status = 0
            self._touch_session(session)

            return {
                "success": True,
                "session_id": session_id,
                "qr_url": qr_url,
                "qr_id": qr_id,
                "code": code,
                "expires_in_sec": self._session_ttl_sec,
            }

    async def poll_status(self, session_id: str) -> Dict[str, Any]:
        session = await self._require_session(session_id)
        async with session.op_lock:
            if not session.qr_id or not session.qr_code:
                raise XhsQrAuthError("qrcode not created, call /qrcode first")

            params = {"qr_id": session.qr_id, "code": session.qr_code}
            data, api_cookies = await self._send_signed_request(
                session=session,
                method="GET",
                uri=self.QRCODE_STATUS_URI,
                params=params,
            )

            data_payload = data.get("data") or {}
            code_status = self._safe_int(data_payload.get("code_status"), default=-1)
            login_info = data_payload.get("login_info")
            login_success = code_status == 2

            if api_cookies:
                session.cookies.update(api_cookies)

            message = "waiting"
            if code_status == 1:
                message = "scanned_waiting_confirm"
            if login_success:
                synced_cookies = await self._sync_cookies_after_login(session, session.cookies)
                if synced_cookies:
                    session.cookies.update(synced_cookies)
                cookie_header = self._persist_cookies(session.cookies)
                config.COOKIES = cookie_header
                message = "login_success"

            session.code_status = code_status
            self._touch_session(session)

            return {
                "success": True,
                "session_id": session_id,
                "code_status": code_status,
                "login_success": login_success,
                "qr_id": session.qr_id,
                "cookie_count": len(session.cookies),
                "login_info": login_info,
                "message": message,
            }

    async def cancel_session(self, session_id: str) -> Dict[str, Any]:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise XhsQrSessionNotFoundError(f"session not found: {session_id}")
        self._close_session_resources(session)
        return {"success": True, "session_id": session_id, "message": "session cancelled"}

    async def sync_from_energy_browser(
        self,
        browser_id: str,
        verify_login: bool = True,
    ) -> Dict[str, Any]:
        """
        Sync cookies from an existing Energy browser session that user already logged in.
        """
        browser_id = (browser_id or "").strip()
        if not browser_id:
            raise XhsQrAuthError("browser_id is required")

        backend = self._create_backend()
        temp_session = _QrSession(
            session_id=f"sync_{uuid.uuid4().hex[:12]}",
            browser_id=browser_id,
            backend=backend,
        )

        try:
            backend.connect()
            temp_session.cookies = self._get_browser_cookie_map(backend, browser_id)
            if not temp_session.cookies:
                raise XhsQrAuthError(
                    f"no cookies found in browser '{browser_id}', please login in Energy first"
                )

            login_success = bool(temp_session.cookies.get("a1"))
            if verify_login:
                data, api_cookies = await self._send_signed_request(
                    session=temp_session,
                    method="GET",
                    uri=self.SELFINFO_URI,
                    params={},
                )
                if api_cookies:
                    temp_session.cookies.update(api_cookies)
                result = ((data.get("data") or {}).get("result") or {})
                login_success = bool(result.get("success"))

            if not login_success:
                raise XhsQrAuthError(
                    f"browser '{browser_id}' is not logged in to XHS (selfinfo check failed)"
                )

            synced_cookies = await self._sync_cookies_after_login(
                temp_session, temp_session.cookies
            )
            if synced_cookies:
                temp_session.cookies.update(synced_cookies)

            cookie_header = self._persist_cookies(temp_session.cookies)
            config.COOKIES = cookie_header
            return {
                "success": True,
                "browser_id": browser_id,
                "login_success": True,
                "cookie_count": len(temp_session.cookies),
                "message": "synced_from_energy_browser",
            }
        except XhsQrAuthError:
            raise
        except Exception as exc:
            raise XhsQrAuthError(
                f"failed to sync cookies from energy browser '{browser_id}': {exc}"
            ) from exc
        finally:
            try:
                backend.disconnect()
            except Exception:
                pass

    async def cleanup_expired_sessions(self) -> int:
        now = time.time()
        expired: list[_QrSession] = []

        async with self._lock:
            for sid, session in list(self._sessions.items()):
                if now - session.updated_at > self._session_ttl_sec:
                    expired.append(self._sessions.pop(sid))

        for session in expired:
            self._close_session_resources(session)

        if expired:
            utils.log_event("xhs.qr.session.expired.cleanup", count=len(expired))
        return len(expired)

    async def _require_session(self, session_id: str) -> _QrSession:
        await self.cleanup_expired_sessions()
        async with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise XhsQrSessionNotFoundError(f"session not found: {session_id}")
        return session

    @staticmethod
    def _touch_session(session: _QrSession) -> None:
        session.updated_at = time.time()

    def _create_backend(self) -> EnergyBrowserBackend:
        host, port = parse_energy_service_address(config.ENERGY_SERVICE_ADDRESS)
        return EnergyBrowserBackend(host=host, port=port)

    def _close_session_resources(self, session: _QrSession) -> None:
        try:
            session.backend.close_browser(session.browser_id)
        except Exception:
            pass
        try:
            session.backend.disconnect()
        except Exception:
            pass

    def _get_browser_cookie_map(self, backend: EnergyBrowserBackend, browser_id: str) -> Dict[str, str]:
        cookies = backend.get_cookies(browser_id, self.XHS_HOME_URL)
        return {c.name: c.value for c in cookies if c.name}

    async def _send_signed_request(
        self,
        session: _QrSession,
        method: str,
        uri: str,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        headers = await self._build_signed_headers(
            session=session,
            method=method,
            uri=uri,
            params=params,
            payload=payload,
        )
        url = f"{self.XHS_HOST}{uri}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "POST":
                response = await client.post(url, headers=headers, json=payload or {})
            else:
                response = await client.get(url, headers=headers, params=params or {})

        body = response.text
        if response.status_code >= 400:
            raise XhsQrAuthError(
                f"xhs login api failed ({response.status_code}): {body[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise XhsQrAuthError(f"invalid xhs api response: {body[:300]}") from exc

        set_cookie_headers = response.headers.get_list("set-cookie")
        api_cookies = self._parse_set_cookie_headers(set_cookie_headers)
        return data, api_cookies

    async def _build_signed_headers(
        self,
        session: _QrSession,
        method: str,
        uri: str,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        request_data: Dict[str, Any]
        if method.upper() == "POST":
            request_data = payload or {}
        else:
            request_data = params or {}

        adapter = XHSEnergyAdapter(
            browser_backend=session.backend,
            browser_id=session.browser_id,
            enable_cache=True,
            session_ttl_sec=getattr(config, "XHS_SIGNATURE_SESSION_TTL_SEC", 1800),
            failure_warn_threshold=getattr(config, "XHS_SIGNATURE_FAILURE_THRESHOLD", 3),
        )
        signs = await adapter.sign_with_energy(
            uri=uri,
            data=request_data,
            a1=session.cookies.get("a1", ""),
            method=method.upper(),
        )

        x_s = signs.get("x-s", "")
        x_t = signs.get("x-t", "")
        x_s_common = signs.get("x-s-common", "")
        if not (x_s and x_t and x_s_common):
            raise XhsQrAuthError("failed to generate signature headers")

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": "https://www.xiaohongshu.com",
            "referer": "https://www.xiaohongshu.com/",
            "user-agent": self.DEFAULT_USER_AGENT,
            "x-s": x_s,
            "x-t": str(x_t),
            "x-s-common": x_s_common,
            "x-b3-traceid": signs.get("x-b3-traceid", ""),
            "cookie": self._cookies_to_header(session.cookies),
        }
        if method.upper() == "POST":
            headers["content-type"] = "application/json;charset=UTF-8"
        return headers

    async def _sync_cookies_after_login(
        self, session: _QrSession, cookies_to_inject: Dict[str, str]
    ) -> Dict[str, str]:
        cookie_items = [
            Cookie(
                name=name,
                value=value,
                domain=".xiaohongshu.com",
                path="/",
                secure=True,
                http_only=False,
            )
            for name, value in cookies_to_inject.items()
            if name
        ]

        if cookie_items:
            session.backend.set_cookies(session.browser_id, cookie_items)
        session.backend.navigate(session.browser_id, self.XHS_HOME_URL, timeout_ms=60000)
        return self._get_browser_cookie_map(session.backend, session.browser_id)

    def _persist_cookies(self, cookies: Dict[str, str]) -> str:
        cookie_header = self._cookies_to_header(cookies)
        if cookie_header:
            upsert_env_values(self._env_path, {"COOKIES": cookie_header})
        return cookie_header

    @staticmethod
    def _cookies_to_header(cookies: Dict[str, str]) -> str:
        return "; ".join(f"{k}={v}" for k, v in cookies.items() if k)

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_set_cookie_headers(set_cookie_headers: list[str]) -> Dict[str, str]:
        cookies: Dict[str, str] = {}
        for item in set_cookie_headers:
            first = item.split(";", 1)[0].strip()
            if not first or "=" not in first:
                continue
            key, value = first.split("=", 1)
            key = key.strip()
            if key:
                cookies[key] = value.strip()
        return cookies


qr_auth_service = XhsQrAuthService()
