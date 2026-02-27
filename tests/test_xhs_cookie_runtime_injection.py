# -*- coding: utf-8 -*-
"""Tests for XHS runtime cookie injection and reconciliation."""

from __future__ import annotations

from typing import Dict, List

import pytest

from energy_client.browser_interface import Cookie
from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.energy_client_adapter import XHSEnergyAdapter


class _CookieBackend:
    def __init__(self, cookies: List[Cookie]):
        self._cookies = cookies

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def create_browser(self, _browser_id: str, headless: bool = True) -> bool:
        _ = headless
        return True

    def close_browser(self, _browser_id: str) -> bool:
        return True

    def navigate(self, _browser_id: str, _url: str, timeout_ms: int = 30000) -> int:
        _ = timeout_ms
        return 200

    def get_cookies(self, _browser_id: str, _url: str):
        return list(self._cookies)

    def set_cookies(self, _browser_id: str, _cookies) -> bool:
        return True

    def execute_js(self, _browser_id: str, _script: str):
        return ""

    def set_proxy(self, _browser_id: str, _proxy_url: str, username: str = "", password: str = "") -> bool:
        _ = (username, password)
        return True

    def execute_signature(self, _browser_id: str, _platform: str, _url: str):
        return {}


def test_xhs_get_cookies_domain_matching_supports_host_only_domains():
    backend = _CookieBackend(
        [
            Cookie(name="a1", value="v1", domain="xiaohongshu.com", path="/"),
            Cookie(name="gid", value="v2", domain=".xiaohongshu.com", path="/"),
            Cookie(name="webId", value="v3", domain="www.xiaohongshu.com", path="/"),
            Cookie(name="ignore", value="x", domain=".x.com", path="/"),
        ]
    )
    adapter = XHSEnergyAdapter(backend, browser_id="test-browser", enable_cache=False)

    cookies = adapter.get_cookies(domain=".xiaohongshu.com")

    assert cookies["a1"] == "v1"
    assert cookies["gid"] == "v2"
    assert cookies["webId"] == "v3"
    assert "ignore" not in cookies


class _RuntimeCookieAdapter:
    def __init__(self, runtime_cookie_dict: Dict[str, str]):
        self.runtime_cookie_dict = dict(runtime_cookie_dict)
        self.set_calls = 0
        self.js_calls = 0

    def set_cookies(self, _cookies, domain: str = ".xiaohongshu.com") -> bool:
        _ = domain
        self.set_calls += 1
        return True

    def set_cookies_via_js(self, cookies_dict: Dict[str, str], domain: str = ".xiaohongshu.com") -> bool:
        _ = domain
        self.js_calls += 1
        self.runtime_cookie_dict.update(cookies_dict)
        return True

    def get_cookies(self) -> Dict[str, str]:
        return dict(self.runtime_cookie_dict)


def test_xhs_runtime_cookie_injection_falls_back_to_js_when_backend_set_not_effective():
    crawler = XiaoHongShuCrawler()
    crawler.energy_adapter = _RuntimeCookieAdapter(
        {
            "a1": "runtime-a1",
            "gid": "runtime-gid",
            "webId": "runtime-webid",
            "abRequestId": "runtime-ab",
            "xsecappid": "xhs-pc-web",
        }
    )

    cookie_map = {
        "a1": "cfg-a1",
        "gid": "cfg-gid",
        "webId": "cfg-webid",
        "abRequestId": "cfg-ab",
        "xsecappid": "xhs-pc-web",
    }

    injected, runtime_cookie_dict, mismatch = crawler._inject_runtime_cookies(
        cookie_map,
        source="unit-test",
    )

    assert injected is True
    assert mismatch == {}
    assert crawler.energy_adapter.set_calls == 1
    assert crawler.energy_adapter.js_calls == 1
    for key, value in cookie_map.items():
        assert runtime_cookie_dict[key] == value


class _SignAdapter:
    def __init__(self):
        self.a1_values: List[str] = []

    async def sign_with_energy(self, uri: str, data, a1: str, method: str):
        _ = (uri, data, method)
        self.a1_values.append(a1)
        return {
            "x-s": "xs",
            "x-t": "xt",
            "x-s-common": "xsc",
            "x-b3-traceid": "trace",
        }

    def get_cookies(self):
        return {"a1": "runtime-a1"}


@pytest.mark.asyncio
async def test_xhs_pre_headers_uses_a1_from_cookie_header_when_cookie_dict_missing():
    adapter = _SignAdapter()
    client = XiaoHongShuClient(
        headers={"Cookie": "foo=bar; a1=header-a1"},
        cookie_dict={},
        energy_adapter=adapter,
    )

    await client._pre_headers("/api/sns/web/v1/user/selfinfo", params={})

    assert adapter.a1_values == ["header-a1"]


@pytest.mark.asyncio
async def test_xhs_pre_headers_falls_back_to_runtime_a1_when_header_missing():
    adapter = _SignAdapter()
    client = XiaoHongShuClient(
        headers={},
        cookie_dict={},
        energy_adapter=adapter,
    )

    await client._pre_headers("/api/sns/web/v1/user/selfinfo", params={})

    assert adapter.a1_values == ["runtime-a1"]
