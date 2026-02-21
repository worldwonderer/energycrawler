#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Energy service CLI.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _run_python_script(script_name: str, args: List[str]) -> int:
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path), *args]
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def _check_cmd(args: argparse.Namespace) -> int:
    cmd_args: List[str] = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--timeout",
        str(args.timeout),
    ]
    if args.skip_grpc_probe:
        cmd_args.append("--skip-grpc-probe")
    if args.json:
        cmd_args.append("--json")
    return _run_python_script("energy_service_healthcheck.py", cmd_args)


def _ensure_cmd(args: argparse.Namespace) -> int:
    script_path = SCRIPTS_DIR / "ensure_energy_service.sh"
    cmd = [
        "bash",
        str(script_path),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--timeout",
        str(args.timeout),
        "--retries",
        str(args.retries),
        "--sleep",
        str(args.sleep),
    ]
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified Energy service CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Run Energy health check")
    check_parser.add_argument("--host", default="localhost")
    check_parser.add_argument("--port", type=int, default=50051)
    check_parser.add_argument("--timeout", type=float, default=8.0)
    check_parser.add_argument("--skip-grpc-probe", action="store_true")
    check_parser.add_argument("--json", action="store_true")
    check_parser.set_defaults(handler=_check_cmd)

    ensure_parser = subparsers.add_parser(
        "ensure",
        help="Ensure Energy service is up (retry + restart)",
    )
    ensure_parser.add_argument("--host", default="localhost")
    ensure_parser.add_argument("--port", type=int, default=50051)
    ensure_parser.add_argument("--timeout", type=float, default=8.0)
    ensure_parser.add_argument("--retries", type=int, default=3)
    ensure_parser.add_argument("--sleep", type=float, default=2.0)
    ensure_parser.set_defaults(handler=_ensure_cmd)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    code = args.handler(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
