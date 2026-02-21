#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified auth CLI for login-state workflows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import List

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _run_python_script(script_name: str, args: List[str]) -> int:
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path), *args]
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def _status_cmd(args: argparse.Namespace) -> int:
    cmd_args: List[str] = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--xhs-browser-id",
        args.xhs_browser_id,
        "--x-browser-id",
        args.x_browser_id,
    ]
    if args.skip_browser_check:
        cmd_args.append("--skip-browser-check")
    if args.json:
        cmd_args.append("--json")
    return _run_python_script("check_login_state.py", cmd_args)


def _export_cmd(args: argparse.Namespace) -> int:
    cmd_args: List[str] = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--env-file",
        args.env_file,
        "--xhs-browser-id",
        args.xhs_browser_id,
        "--x-browser-id",
        args.x_browser_id,
        "--xhs-url",
        args.xhs_url,
        "--x-url",
        args.x_url,
        "--platform",
        args.platform,
    ]
    if args.strict_x_auth:
        cmd_args.append("--strict-x-auth")
    return _run_python_script("export_cookies_to_env.py", cmd_args)


def _xhs_qr_login_cmd(args: argparse.Namespace) -> int:
    cmd_args: List[str] = [
        "--api-base",
        args.api_base,
        "--poll-interval",
        str(args.poll_interval),
        "--timeout-sec",
        str(args.timeout_sec),
        "--energy-host",
        args.energy_host,
        "--energy-port",
        str(args.energy_port),
        "--energy-open-mode",
        args.energy_open_mode,
    ]
    if args.session_id:
        cmd_args.extend(["--session-id", args.session_id])
    if args.browser_id:
        cmd_args.extend(["--browser-id", args.browser_id])
    if args.headless:
        cmd_args.append("--headless")
    if args.keep_session:
        cmd_args.append("--keep-session")
    if args.json:
        cmd_args.append("--json")
    if not args.open_in_energy:
        cmd_args.append("--no-open-in-energy")
    return _run_python_script("xhs_qr_login_flow.py", cmd_args)


def _xhs_sync_cmd(args: argparse.Namespace) -> int:
    url = f"{args.api_base.rstrip('/')}/api/auth/xhs/energy/sync"
    payload = {
        "browser_id": args.browser_id,
        "verify_login": args.verify_login,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload)
        if response.status_code >= 400:
            print(
                f"[error] {response.status_code} {url}: {response.text[:600]}",
                file=sys.stderr,
            )
            return 1
        data = response.json()
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"[error] xhs-sync failed: {exc}", file=sys.stderr)
        return 1


def _xhs_open_login_cmd(args: argparse.Namespace) -> int:
    cmd_args: List[str] = [
        "--api-base",
        args.api_base,
        "--energy-host",
        args.energy_host,
        "--energy-port",
        str(args.energy_port),
        "--browser-id",
        args.browser_id,
        "--login-url",
        args.login_url,
        "--poll-interval",
        str(args.poll_interval),
        "--timeout-sec",
        str(args.timeout_sec),
    ]
    if args.headless:
        cmd_args.append("--headless")
    if args.json:
        cmd_args.append("--json")
    return _run_python_script("xhs_open_login_and_sync.py", cmd_args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified auth/login CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Check login-state readiness")
    status_parser.add_argument("--host", default="localhost")
    status_parser.add_argument("--port", type=int, default=50051)
    status_parser.add_argument("--xhs-browser-id", default="manual_login_xhs")
    status_parser.add_argument("--x-browser-id", default="manual_login_x")
    status_parser.add_argument("--skip-browser-check", action="store_true")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(handler=_status_cmd)

    export_parser = subparsers.add_parser("export", help="Export cookies from Energy to .env")
    export_parser.add_argument("--host", default="localhost")
    export_parser.add_argument("--port", type=int, default=50051)
    export_parser.add_argument("--env-file", default=".env")
    export_parser.add_argument("--xhs-browser-id", default="manual_login_xhs")
    export_parser.add_argument("--x-browser-id", default="manual_login_x")
    export_parser.add_argument("--xhs-url", default="https://www.xiaohongshu.com")
    export_parser.add_argument("--x-url", default="https://x.com")
    export_parser.add_argument("--platform", choices=["all", "xhs", "x"], default="all")
    export_parser.add_argument("--strict-x-auth", action="store_true")
    export_parser.set_defaults(handler=_export_cmd)

    qr_parser = subparsers.add_parser(
        "xhs-qr-login",
        help="Run XHS QR API login flow (fallback mode)",
    )
    qr_parser.add_argument("--api-base", default="http://localhost:8080")
    qr_parser.add_argument("--session-id", default="")
    qr_parser.add_argument("--browser-id", default="")
    qr_parser.add_argument("--headless", action="store_true")
    qr_parser.add_argument("--energy-host", default="localhost")
    qr_parser.add_argument("--energy-port", type=int, default=50051)
    qr_parser.add_argument("--energy-open-mode", choices=["qr", "direct"], default="qr")
    qr_parser.add_argument(
        "--open-in-energy",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    qr_parser.add_argument("--poll-interval", type=float, default=2.0)
    qr_parser.add_argument("--timeout-sec", type=float, default=180.0)
    qr_parser.add_argument("--keep-session", action="store_true")
    qr_parser.add_argument("--json", action="store_true")
    qr_parser.set_defaults(handler=_xhs_qr_login_cmd)

    sync_parser = subparsers.add_parser(
        "xhs-sync",
        help="Sync logged-in XHS cookies from an existing Energy browser session",
    )
    sync_parser.add_argument("--api-base", default="http://localhost:8080")
    sync_parser.add_argument("--browser-id", default="manual_login_xhs")
    sync_parser.add_argument(
        "--verify-login",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    sync_parser.set_defaults(handler=_xhs_sync_cmd)

    open_login_parser = subparsers.add_parser(
        "xhs-open-login",
        help="Open XHS login page in Energy and auto-sync cookies after login",
    )
    open_login_parser.add_argument("--api-base", default="http://localhost:8080")
    open_login_parser.add_argument("--energy-host", default="localhost")
    open_login_parser.add_argument("--energy-port", type=int, default=50051)
    open_login_parser.add_argument("--browser-id", default="manual_login_xhs")
    open_login_parser.add_argument("--login-url", default="https://www.xiaohongshu.com")
    open_login_parser.add_argument("--headless", action="store_true")
    open_login_parser.add_argument("--poll-interval", type=float, default=2.0)
    open_login_parser.add_argument("--timeout-sec", type=float, default=300.0)
    open_login_parser.add_argument("--json", action="store_true")
    open_login_parser.set_defaults(handler=_xhs_open_login_cmd)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    code = args.handler(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
