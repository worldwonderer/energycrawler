#!/usr/bin/env python3
"""
Interactive real-flow runner for XHS and X crawling.

Flow:
1. Check Energy service connectivity.
2. Ensure XHS and X login state (open login page and wait for user if needed).
3. Run real crawler start flow for XHS and X.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from energy_client.client import BrowserClient
from main import CrawlerFactory
from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.energy_client_adapter import create_xhs_energy_adapter


@dataclass(frozen=True)
class LoginSpec:
    platform: str
    browser_id: str
    login_url: str
    cookie_check: Callable[[dict[str, str]], bool]
    prompt: str


def _cookies_to_dict(cookies) -> dict[str, str]:
    return {c.name: c.value for c in cookies}


def _is_xhs_logged(cookies: dict[str, str]) -> bool:
    # Deprecated in favor of API-level login check via XiaoHongShuClient.pong().
    return False


def _is_x_logged(cookies: dict[str, str]) -> bool:
    # Twitter/X authenticated cookie pair.
    return bool(cookies.get("auth_token") and cookies.get("ct0"))


LOGIN_SPECS = (
    LoginSpec(
        platform="xhs",
        browser_id="manual_login_xhs",
        login_url="https://www.xiaohongshu.com",
        cookie_check=_is_xhs_logged,
        prompt="Please finish XHS login in browser, then press Enter to continue...",
    ),
    LoginSpec(
        platform="x",
        browser_id="manual_login_x",
        login_url="https://x.com/i/flow/login",
        cookie_check=_is_x_logged,
        prompt="Please finish X login in browser, then press Enter to continue...",
    ),
)


def probe_service(host: str, port: int) -> None:
    client = BrowserClient(host, port)
    client.connect()
    try:
        ok = client.create_browser("__probe__", headless=True)
        if not ok:
            raise RuntimeError("Energy service reachable but create_browser failed")
        client.close_browser("__probe__")
    finally:
        client.disconnect()


async def ensure_login(host: str, port: int, spec: LoginSpec) -> None:
    if spec.platform == "x":
        auth_token = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
        ct0 = os.getenv("TWITTER_CT0", "").strip()
        if auth_token and ct0:
            print("[x] detected TWITTER_AUTH_TOKEN/TWITTER_CT0 in env, skip interactive login")
            return

    client = BrowserClient(host, port)
    client.connect()
    try:
        # Create may return False if browser id already exists; continue anyway.
        client.create_browser(spec.browser_id, headless=False)
        status = client.navigate(spec.browser_id, spec.login_url, timeout_ms=60000)
        print(f"[{spec.platform}] login page status: {status}")

        while True:
            if spec.platform == "xhs":
                if await _check_xhs_login_state(host, port, spec.browser_id):
                    print("[xhs] login detected (pong=true)")
                    return
            else:
                cookies = _cookies_to_dict(client.get_cookies(spec.browser_id, spec.login_url))
                if spec.cookie_check(cookies):
                    print(f"[{spec.platform}] login detected")
                    return
            input(f"[{spec.platform}] {spec.prompt}")
    finally:
        client.disconnect()


async def _check_xhs_login_state(host: str, port: int, browser_id: str) -> bool:
    """
    Validate XHS login state with API-level check to avoid false positives
    from visitor cookies.
    """
    adapter = create_xhs_energy_adapter(
        host=host,
        port=port,
        browser_id=browser_id,
        headless=False,
    )
    try:
        cookie_dict = adapter.get_cookies()
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        client = XiaoHongShuClient(
            proxy=None,
            headers={
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://www.xiaohongshu.com",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://www.xiaohongshu.com/",
                "sec-ch-ua": '"Chromium";v="109"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Mac OS X"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
                "Cookie": cookie_str,
            },
            cookie_dict=cookie_dict,
            energy_adapter=adapter,
        )
        return await client.pong()
    except Exception:
        return False
    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass


async def run_platform_crawl(platform: str, keyword: str, max_count: int) -> None:
    config.PLATFORM = platform
    config.CRAWLER_TYPE = "search"
    config.KEYWORDS = keyword
    config.CRAWLER_MAX_NOTES_COUNT = max_count
    config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = min(config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES, 3)
    config.CRAWLER_MAX_SLEEP_SEC = max(config.CRAWLER_MAX_SLEEP_SEC, 10)
    config.SAVE_DATA_OPTION = "json"
    if platform == "x":
        env_auth_token = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
        env_ct0 = os.getenv("TWITTER_CT0", "").strip()
        if env_auth_token:
            config.TWITTER_AUTH_TOKEN = env_auth_token
        if env_ct0:
            config.TWITTER_CT0 = env_ct0

    crawler = CrawlerFactory.create_crawler(platform)
    await crawler.start()
    print(f"[{platform}] crawl flow completed")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run interactive XHS/X real crawl flow")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--xhs-keyword", default="新能源")
    parser.add_argument("--x-keyword", default="tesla")
    parser.add_argument("--max-count", type=int, default=3)
    parser.add_argument("--skip-crawl", action="store_true", help="Only do login checks")
    args = parser.parse_args()

    print(f"Checking Energy service at {args.host}:{args.port} ...")
    probe_service(args.host, args.port)
    print("Energy service is available.")

    for spec in LOGIN_SPECS:
        await ensure_login(args.host, args.port, spec)

    if args.skip_crawl:
        print("Login checks completed.")
        return

    await run_platform_crawl("xhs", args.xhs_keyword, args.max_count)
    await run_platform_crawl("x", args.x_keyword, args.max_count)


if __name__ == "__main__":
    asyncio.run(main())
