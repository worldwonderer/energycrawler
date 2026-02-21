#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export cookies from Energy browser sessions into project .env.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from energy_client.client import BrowserClient
from tools.env_store import upsert_env_values


def _cookie_header_from_items(cookies) -> str:
    return "; ".join(f"{c.name}={c.value}" for c in cookies if c.name)


def _cookie_map(header: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for item in header.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Energy browser cookies into .env")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--xhs-browser-id", default="manual_login_xhs")
    parser.add_argument("--x-browser-id", default="manual_login_x")
    parser.add_argument("--xhs-url", default="https://www.xiaohongshu.com")
    parser.add_argument("--x-url", default="https://x.com")
    parser.add_argument(
        "--platform",
        choices=["all", "xhs", "x"],
        default="all",
        help="Which platform cookies to export",
    )
    parser.add_argument(
        "--strict-x-auth",
        action="store_true",
        help="Exit non-zero if exported X cookies do not include auth_token + ct0",
    )
    args = parser.parse_args()

    client = BrowserClient(args.host, args.port)
    client.connect()
    updates: Dict[str, str] = {}
    summary: Dict[str, int] = {}
    try:
        if args.platform in {"all", "xhs"}:
            xhs_cookies = client.get_cookies(args.xhs_browser_id, args.xhs_url)
            xhs_header = _cookie_header_from_items(xhs_cookies)
            if xhs_header:
                updates["COOKIES"] = xhs_header
            summary["xhs_cookie_count"] = len(xhs_cookies)

        if args.platform in {"all", "x"}:
            x_cookies = client.get_cookies(args.x_browser_id, args.x_url)
            x_header = _cookie_header_from_items(x_cookies)
            if x_header:
                updates["TWITTER_COOKIE"] = x_header
                x_map = _cookie_map(x_header)
                if x_map.get("auth_token"):
                    updates["TWITTER_AUTH_TOKEN"] = x_map["auth_token"]
                if x_map.get("ct0"):
                    updates["TWITTER_CT0"] = x_map["ct0"]
            summary["x_cookie_count"] = len(x_cookies)
    finally:
        client.disconnect()

    if not updates:
        raise SystemExit(
            f"No cookies captured. Check browser IDs and login state: "
            f"xhs={summary.get('xhs_cookie_count', 0)}, x={summary.get('x_cookie_count', 0)}"
        )

    env_path = Path(args.env_file).resolve()
    upsert_env_values(env_path, updates)
    print(f"Updated {env_path}")
    for key, value in updates.items():
        print(f"- {key}: len={len(value)}")
    for key, value in summary.items():
        print(f"- {key}: {value}")

    if args.platform in {"all", "x"}:
        cookie_map = _cookie_map(updates.get("TWITTER_COOKIE", ""))
        has_auth = bool(cookie_map.get("auth_token"))
        has_ct0 = bool(cookie_map.get("ct0"))
        if has_auth and has_ct0:
            print("- x_auth: auth_token + ct0 captured")
        else:
            message = "- x_auth: missing auth_token and/or ct0 in exported TWITTER_COOKIE"
            if args.strict_x_auth:
                raise SystemExit(message)
            print(message)

    if args.platform in {"all", "xhs"}:
        cookie_map = _cookie_map(updates.get("COOKIES", ""))
        has_a1 = bool(cookie_map.get("a1"))
        if has_a1:
            print("- xhs_auth: a1 captured")
        else:
            print("- xhs_auth: missing a1 in exported COOKIES")


if __name__ == "__main__":
    main()
