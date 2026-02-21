#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified CLI entrypoint for crawl/auth/energy/doctor workflows."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _normalize_passthrough_args(raw: List[str]) -> List[str]:
    if raw and raw[0] == "--":
        return raw[1:]
    return raw


def _run_command(cmd: List[str]) -> int:
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def _build_python_target_command(script_path: Path, args: List[str]) -> List[str]:
    if shutil.which("uv"):
        return ["uv", "run", "python", str(script_path), *args]
    return [sys.executable, str(script_path), *args]


def _crawl_cmd(args: argparse.Namespace) -> int:
    crawl_args = _normalize_passthrough_args(args.args)
    cmd = _build_python_target_command(PROJECT_ROOT / "main.py", crawl_args)
    return _run_command(cmd)


def _auth_cmd(args: argparse.Namespace) -> int:
    auth_args = _normalize_passthrough_args(args.args)
    cmd = _build_python_target_command(SCRIPTS_DIR / "auth_cli.py", auth_args)
    return _run_command(cmd)


def _energy_cmd(args: argparse.Namespace) -> int:
    energy_args = _normalize_passthrough_args(args.args)
    cmd = _build_python_target_command(SCRIPTS_DIR / "energy_service_cli.py", energy_args)
    return _run_command(cmd)


def _doctor_cmd(args: argparse.Namespace) -> int:
    checks: list[tuple[str, list[str]]] = [
        (
            "Energy service health",
            [
                *_build_python_target_command(
                    SCRIPTS_DIR / "energy_service_cli.py",
                    [
                        "check",
                        "--host",
                        args.host,
                        "--port",
                        str(args.port),
                        "--timeout",
                        str(args.timeout),
                        *(["--json"] if args.json else []),
                    ],
                ),
            ],
        )
    ]

    if not args.skip_login_check:
        checks.append(
            (
                "Login-state readiness",
                [
                    *_build_python_target_command(
                        SCRIPTS_DIR / "auth_cli.py",
                        [
                            "status",
                            "--host",
                            args.host,
                            "--port",
                            str(args.port),
                            "--skip-browser-check",
                            *(["--json"] if args.json else []),
                        ],
                    ),
                ],
            )
        )

    failed_checks: list[str] = []
    for check_name, cmd in checks:
        print(f"[doctor] Running: {check_name}")
        code = _run_command(cmd)
        if code == 0:
            print(f"[doctor] PASS: {check_name}")
        else:
            print(f"[doctor] FAIL: {check_name} (exit code {code})")
            failed_checks.append(check_name)

    if failed_checks:
        print("")
        print("[doctor] Summary: failed checks")
        for name in failed_checks:
            print(f"- {name}")
        print("Try: python3 scripts/energy_service_cli.py ensure")
        return 1

    print("[doctor] Summary: all checks passed")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EnergyCrawler unified CLI",
        epilog=(
            "Examples:\n"
            "  python3 scripts/energycrawler_cli.py energy ensure\n"
            "  python3 scripts/energycrawler_cli.py auth status --json\n"
            "  python3 scripts/energycrawler_cli.py crawl -- --platform xhs --type search --keywords 新能源\n"
            "  python3 scripts/energycrawler_cli.py doctor"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl_parser = subparsers.add_parser("crawl", help="Run crawler CLI (main.py)")
    crawl_parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to main.py",
    )
    crawl_parser.set_defaults(handler=_crawl_cmd)

    auth_parser = subparsers.add_parser("auth", help="Run auth helper CLI")
    auth_parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to scripts/auth_cli.py",
    )
    auth_parser.set_defaults(handler=_auth_cmd)

    energy_parser = subparsers.add_parser("energy", help="Run Energy service helper CLI")
    energy_parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to scripts/energy_service_cli.py",
    )
    energy_parser.set_defaults(handler=_energy_cmd)

    doctor_parser = subparsers.add_parser("doctor", help="Run quick environment diagnostics")
    doctor_parser.add_argument("--host", default="localhost")
    doctor_parser.add_argument("--port", type=int, default=50051)
    doctor_parser.add_argument("--timeout", type=float, default=8.0)
    doctor_parser.add_argument("--skip-login-check", action="store_true")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(handler=_doctor_cmd)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    code = args.handler(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
