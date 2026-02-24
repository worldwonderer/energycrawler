#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Open XHS login page in Energy browser and sync cookies after manual login.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict
import uuid

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


def _unwrap_success_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten API success envelope.

    Supports both formats:
    - {"success": true, "data": {...}, "message": "..."}
    - {"success": true, ...}
    """
    if not isinstance(payload, dict):
        return {}

    data = payload.get("data")
    if isinstance(data, dict):
        flattened = dict(data)
        if "success" not in flattened:
            flattened["success"] = bool(payload.get("success", True))
        if "message" not in flattened and isinstance(payload.get("message"), str):
            flattened["message"] = str(payload["message"])
        return flattened

    return dict(payload)


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


def _resolve_browser_id(raw_browser_id: str) -> str:
    browser_id = (raw_browser_id or "").strip()
    if browser_id:
        return browser_id
    prefix = (os.getenv("ENERGY_BROWSER_ID_PREFIX", "energycrawler") or "energycrawler").strip()
    return f"{prefix}_xhs_auth_{os.getpid()}_{uuid.uuid4().hex[:8]}"


def _parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    for item in cookie_header.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            pairs[key] = value
    return pairs


def _load_env_cookies(env_path: Path) -> str:
    if not env_path.exists():
        return ""

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "COOKIES":
            cleaned = value.strip()
            if (cleaned.startswith('"') and cleaned.endswith('"')) or (
                cleaned.startswith("'") and cleaned.endswith("'")
            ):
                cleaned = cleaned[1:-1]
            return cleaned
    return ""


def _verify_sync_result(sync_result: Dict[str, Any], env_path: Path) -> tuple[bool, str]:
    if not bool(sync_result.get("success", True)):
        return False, f"sync did not succeed: {sync_result.get('message', 'unknown error')}"
    if not bool(sync_result.get("login_success", False)):
        return False, "sync reported login_success=false"

    cookie_count = int(sync_result.get("cookie_count", 0) or 0)
    if cookie_count <= 0:
        return False, "sync returned zero cookies"

    cookie_header = _load_env_cookies(env_path)
    cookie_map = _parse_cookie_header(cookie_header)
    if not cookie_map.get("a1", "").strip():
        return False, f"verify failed: {env_path} COOKIES missing a1 after sync"

    return True, f"verify passed: {env_path} COOKIES contains a1"


def _build_next_steps(
    error_message: str,
    *,
    browser_id: str,
    api_base: str,
    timeout_sec: float,
) -> list[str]:
    msg = (error_message or "").lower()
    commands: list[str] = []

    if "timeout" in msg:
        commands.extend(
            [
                "确认已在 Energy 浏览器窗口完成小红书扫码/登录后再重试。",
                (
                    "延长等待时间后重试："
                    f" uv run energycrawler auth xhs-open-login --api-base {api_base} "
                    f"--timeout-sec {max(timeout_sec * 2, timeout_sec + 60):.0f}"
                ),
            ]
        )

    if any(token in msg for token in ("connection refused", "failed to connect", "name or service not known")):
        commands.extend(
            [
                "检查 Energy 服务状态：uv run energycrawler energy check --json",
                "必要时自动拉起服务：uv run energycrawler energy ensure",
            ]
        )

    if "no cookies found" in msg or "not logged in" in msg or "missing a1" in msg:
        if browser_id:
            commands.append(
                f"若已在该会话登录，可直接同步：uv run energycrawler auth xhs-sync --api-base {api_base} --browser-id {browser_id}"
            )
        else:
            commands.append("请重新执行 open-login，并记录输出中的 browser_id 后再执行 xhs-sync。")

    commands.append("最终校验登录态：uv run energycrawler auth status --json")
    # remove duplicates while preserving order
    deduped: list[str] = []
    seen: set[str] = set()
    for line in commands:
        if line in seen:
            continue
        seen.add(line)
        deduped.append(line)
    return deduped


def _print_next_steps(lines: list[str], *, stream: Any = sys.stdout) -> None:
    for index, line in enumerate(lines, start=1):
        print(f"[next {index}] {line}", file=stream)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open XHS login page in Energy and sync cookies after manual login"
    )
    parser.add_argument("--api-base", default="http://localhost:8080")
    parser.add_argument("--energy-host", default="localhost")
    parser.add_argument("--energy-port", type=int, default=50051)
    parser.add_argument(
        "--browser-id",
        default="",
        help="Target Energy browser id. Leave empty to auto-generate an isolated id.",
    )
    parser.add_argument("--login-url", default="https://www.xiaohongshu.com")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout-sec", type=float, default=300.0)
    parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify synced login state (.env COOKIES contains a1).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    browser_id = _resolve_browser_id(args.browser_id)
    base_api = args.api_base.rstrip("/")

    if not (args.browser_id or "").strip():
        print(f"[step 1/3] auto-generated browser_id={browser_id}")

    try:
        status_code = _open_login_page(
            host=args.energy_host,
            port=args.energy_port,
            browser_id=browser_id,
            url=args.login_url,
            headless=args.headless,
        )
        print(
            f"[step 1/3] opened login page in browser_id={browser_id} "
            f"(status={status_code}) url={args.login_url}"
        )
        print("[step 1/3] 请在 Energy 窗口完成小红书扫码/确认登录。")

        sync_url = f"{base_api}/api/auth/xhs/energy/sync"
        payload = {"browser_id": browser_id, "verify_login": True}

        started = time.monotonic()
        last_error = ""
        sync_result: Dict[str, Any] = {}

        print("[step 2/3] waiting for login completion and syncing cookies ...")
        with httpx.Client(timeout=30.0) as client:
            while True:
                try:
                    raw_response = _request_json(client, "POST", sync_url, json=payload)
                    sync_result = _unwrap_success_payload(raw_response)
                    if sync_result.get("success", False):
                        break
                    last_error = str(sync_result.get("message", "sync not successful"))
                except Exception as exc:
                    last_error = str(exc)
                print(f"[status] waiting_login: {last_error}")

                if time.monotonic() - started > args.timeout_sec:
                    raise TimeoutError(
                        f"login sync timeout after {args.timeout_sec:.1f}s, last_error={last_error}"
                    )
                time.sleep(max(0.2, args.poll_interval))

        verification: Dict[str, Any] = {"enabled": bool(args.verify), "ok": True, "message": "skipped"}
        if args.verify:
            print("[step 3/3] verifying synced login state ...")
            ok, message = _verify_sync_result(sync_result, PROJECT_ROOT / ".env")
            verification = {"enabled": True, "ok": ok, "message": message}
            if not ok:
                raise RuntimeError(message)

        result_payload: Dict[str, Any] = {
            "success": True,
            "browser_id": browser_id,
            "open": {
                "status_code": status_code,
                "url": args.login_url,
            },
            "sync": sync_result,
            "verify": verification,
            "message": "xhs_login_wizard_completed",
        }

        if args.json:
            print(json.dumps(result_payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"[done] login synced: browser_id={sync_result.get('browser_id', browser_id)} "
                f"cookies={sync_result.get('cookie_count')} message={sync_result.get('message')}"
            )
            if args.verify:
                print(f"[done] verify: {verification['message']}")
            print("[done] verify with: uv run energycrawler auth status --json")
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        next_steps = _build_next_steps(
            str(exc),
            browser_id=browser_id,
            api_base=base_api,
            timeout_sec=args.timeout_sec,
        )
        _print_next_steps(next_steps, stream=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
