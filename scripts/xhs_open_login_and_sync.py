#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Open XHS login page in Energy browser and sync cookies after manual login.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from energy_client.client import BrowserClient


def _request_json(client: httpx.Client, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
    response = client.request(method, url, **kwargs)
    body = response.text
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {url} failed [{response.status_code}]: {body[:400]}")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {url} returned invalid JSON: {body[:400]}") from exc


def _open_login_page(host: str, port: int, browser_id: str, url: str, headless: bool) -> int:
    client = BrowserClient(host, port)
    client.connect()
    try:
        # create may return False when browser already exists; continue.
        try:
            client.create_browser(browser_id, headless=headless)
        except Exception:
            pass
        return client.navigate(browser_id, url, timeout_ms=60000)
    finally:
        client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open XHS login page in Energy and sync cookies after manual login"
    )
    parser.add_argument("--api-base", default="http://localhost:8080")
    parser.add_argument("--energy-host", default="localhost")
    parser.add_argument("--energy-port", type=int, default=50051)
    parser.add_argument("--browser-id", default="manual_login_xhs")
    parser.add_argument("--login-url", default="https://www.xiaohongshu.com")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout-sec", type=float, default=300.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    status_code = _open_login_page(
        host=args.energy_host,
        port=args.energy_port,
        browser_id=args.browser_id,
        url=args.login_url,
        headless=args.headless,
    )
    print(
        f"[energy] opened login page in browser_id={args.browser_id} "
        f"(status={status_code}) url={args.login_url}"
    )
    print("[hint] 请在 Energy 窗口完成小红书扫码/确认登录，脚本会自动轮询并同步 COOKIES。")

    sync_url = f"{args.api_base.rstrip('/')}/api/auth/xhs/energy/sync"
    payload = {"browser_id": args.browser_id, "verify_login": True}

    started = time.monotonic()
    last_error = ""
    result: Dict[str, Any] = {}
    with httpx.Client(timeout=30.0) as client:
        while True:
            try:
                result = _request_json(client, "POST", sync_url, json=payload)
                if result.get("success"):
                    break
            except Exception as exc:
                last_error = str(exc)
                print(f"[status] waiting_login: {last_error}")

            if time.monotonic() - started > args.timeout_sec:
                raise TimeoutError(
                    f"login sync timeout after {args.timeout_sec:.1f}s, last_error={last_error}"
                )
            time.sleep(max(0.2, args.poll_interval))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"[done] login synced: browser_id={result.get('browser_id')} "
            f"cookies={result.get('cookie_count')} message={result.get('message')}"
        )
        print(
            "[done] verify with: uv run energycrawler auth status "
            f"--xhs-browser-id {args.browser_id} --skip-browser-check"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        raise SystemExit(1) from exc
