#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check login state readiness for XHS and X.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from energy_client.client import BrowserClient


@dataclass
class LoginCheckResult:
    platform: str
    env_ok: bool
    env_message: str
    browser_cookie_count: int = 0
    browser_ok: bool = False
    browser_message: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "platform": self.platform,
            "env_ok": self.env_ok,
            "env_message": self.env_message,
            "browser_cookie_count": self.browser_cookie_count,
            "browser_ok": self.browser_ok,
            "browser_message": self.browser_message,
        }


def parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for item in cookie_header.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result


def check_x_env_state() -> tuple[bool, str]:
    cookie_header = (getattr(config, "TWITTER_COOKIE", "") or "").strip()
    auth_token = (getattr(config, "TWITTER_AUTH_TOKEN", "") or "").strip()
    ct0 = (getattr(config, "TWITTER_CT0", "") or "").strip()
    cookie_map = parse_cookie_header(cookie_header)

    has_auth = bool(auth_token or cookie_map.get("auth_token", "").strip())
    has_ct0 = bool(ct0 or cookie_map.get("ct0", "").strip())

    if has_auth and has_ct0:
        return True, "env has auth_token + ct0"
    return False, "env missing auth_token and/or ct0"


def check_xhs_env_state() -> tuple[bool, str]:
    cookie_header = (getattr(config, "COOKIES", "") or "").strip()
    cookie_map = parse_cookie_header(cookie_header)
    if not cookie_map:
        return False, "env COOKIES is empty"
    # a1 is a practical minimum for XHS signed API calls.
    if not cookie_map.get("a1", "").strip():
        return False, "env COOKIES missing a1"
    return True, "env COOKIES present (a1 found; supports QR login output)"


def _browser_cookie_header(cookies: List[object]) -> str:
    pairs: List[str] = []
    for cookie in cookies:
        name = getattr(cookie, "name", "")
        value = getattr(cookie, "value", "")
        if not name:
            continue
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def check_browser_state(
    host: str,
    port: int,
    browser_id: str,
    url: str,
    platform: str,
) -> tuple[bool, str, int]:
    client = BrowserClient(host, port)
    try:
        client.connect()
        cookies = client.get_cookies(browser_id, url)
    except Exception as exc:
        return False, f"browser check failed: {exc}", 0
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

    header = _browser_cookie_header(cookies)
    cookie_map = parse_cookie_header(header)
    if platform == "x":
        ok = bool(cookie_map.get("auth_token") and cookie_map.get("ct0"))
        msg = "browser has auth_token + ct0" if ok else "browser missing auth_token and/or ct0"
    else:
        ok = bool(cookie_map.get("a1"))
        msg = "browser has a1" if ok else "browser missing a1"
    return ok, msg, len(cookies)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check login-state readiness for XHS/X")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--xhs-browser-id", default="manual_login_xhs")
    parser.add_argument("--x-browser-id", default="manual_login_x")
    parser.add_argument("--skip-browser-check", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args()

    env_file = PROJECT_ROOT / ".env"
    results: List[LoginCheckResult] = []

    xhs_env_ok, xhs_env_msg = check_xhs_env_state()
    x_env_ok, x_env_msg = check_x_env_state()
    results.append(LoginCheckResult(platform="xhs", env_ok=xhs_env_ok, env_message=xhs_env_msg))
    results.append(LoginCheckResult(platform="x", env_ok=x_env_ok, env_message=x_env_msg))

    if not args.skip_browser_check:
        xhs_ok, xhs_msg, xhs_count = check_browser_state(
            host=args.host,
            port=args.port,
            browser_id=args.xhs_browser_id,
            url="https://www.xiaohongshu.com",
            platform="xhs",
        )
        x_ok, x_msg, x_count = check_browser_state(
            host=args.host,
            port=args.port,
            browser_id=args.x_browser_id,
            url="https://x.com",
            platform="x",
        )
        results[0].browser_ok = xhs_ok
        results[0].browser_message = xhs_msg
        results[0].browser_cookie_count = xhs_count
        results[1].browser_ok = x_ok
        results[1].browser_message = x_msg
        results[1].browser_cookie_count = x_count

    payload = {
        "project_root": str(PROJECT_ROOT),
        "env_exists": env_file.exists(),
        "results": [item.to_dict() for item in results],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"project_root={payload['project_root']}")
        print(f"env_exists={payload['env_exists']}")
        for item in results:
            print(
                f"[{item.platform}] env_ok={item.env_ok} ({item.env_message}) | "
                f"browser_ok={item.browser_ok} cookies={item.browser_cookie_count} ({item.browser_message})"
            )

    all_ok = all(item.env_ok for item in results)
    if not args.skip_browser_check:
        all_ok = all_ok and all(item.browser_ok for item in results)
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
