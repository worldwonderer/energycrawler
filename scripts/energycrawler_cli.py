#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified CLI entrypoint for crawl/auth/energy/doctor workflows."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TOOLS_DIR = PROJECT_ROOT / "tools"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 50051
DEFAULT_TIMEOUT = 8.0


def _normalize_passthrough_args(raw: Sequence[str]) -> list[str]:
    args = list(raw)
    if args and args[0] == "--":
        return args[1:]
    return args


def _run_command(cmd: Sequence[str]) -> int:
    return subprocess.call(list(cmd), cwd=str(PROJECT_ROOT))


def _python_exec_prefix() -> list[str]:
    if shutil.which("uv"):
        return ["uv", "run", "python"]
    return [sys.executable]


def _run_python_entry(script_path: Path, args: Sequence[str]) -> int:
    cmd = [*_python_exec_prefix(), str(script_path), *list(args)]
    return _run_command(cmd)


def _run_local_script(script_name: str, args: Sequence[str]) -> int:
    return _run_python_entry(SCRIPTS_DIR / script_name, args)


def _crawl_cmd(args: argparse.Namespace) -> int:
    return _run_python_entry(PROJECT_ROOT / "main.py", _normalize_passthrough_args(args.args))


def _auth_cmd(args: argparse.Namespace) -> int:
    return _run_local_script("auth_cli.py", _normalize_passthrough_args(args.args))


def _energy_cmd(args: argparse.Namespace) -> int:
    return _run_local_script("energy_service_cli.py", _normalize_passthrough_args(args.args))


def _run_cleanup_report(*, json_output: bool, fail_on_findings: bool) -> int:
    cmd_args: list[str] = []
    if json_output:
        cmd_args.append("--json")
    if fail_on_findings:
        cmd_args.append("--fail-on-findings")
    return _run_python_entry(TOOLS_DIR / "cleanup_report.py", cmd_args)


def _cleanup_report_cmd(args: argparse.Namespace) -> int:
    return _run_cleanup_report(
        json_output=args.json,
        fail_on_findings=args.fail_on_findings,
    )


def _run_doctor_checks(
    *,
    host: str,
    port: int,
    timeout: float,
    json_output: bool,
    skip_login_check: bool,
) -> int:
    checks: list[tuple[str, list[str]]] = [
        (
            "Energy service health",
            [
                "energy_service_cli.py",
                "check",
                "--host",
                host,
                "--port",
                str(port),
                "--timeout",
                str(timeout),
                *(["--json"] if json_output else []),
            ],
        )
    ]

    if not skip_login_check:
        checks.append(
            (
                "Login-state readiness",
                [
                    "auth_cli.py",
                    "status",
                    "--host",
                    host,
                    "--port",
                    str(port),
                    "--skip-browser-check",
                    *(["--json"] if json_output else []),
                ],
            )
        )

    failed_checks: list[str] = []
    for check_name, raw_cmd in checks:
        print(f"[doctor] Running: {check_name}")
        code = _run_local_script(raw_cmd[0], raw_cmd[1:])
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
        print("Try: uv run energycrawler energy ensure")
        return 1
    return 0


def _doctor_cmd(args: argparse.Namespace) -> int:
    check_code = _run_doctor_checks(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        json_output=args.json,
        skip_login_check=args.skip_login_check,
    )
    if check_code != 0:
        return check_code

    if args.cleanup_report:
        print("[doctor] Running: Cleanup candidate report")
        cleanup_code = _run_cleanup_report(
            json_output=args.json,
            fail_on_findings=args.cleanup_fail_on_findings,
        )
        if cleanup_code != 0:
            return cleanup_code

    print("[doctor] Summary: all checks passed")
    return 0


def _resolve_project_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _init_cmd(args: argparse.Namespace) -> int:
    template_path = _resolve_project_path(args.template)
    env_path = _resolve_project_path(args.env_file)

    if not template_path.exists():
        print(f"[init] Template not found: {template_path}", file=sys.stderr)
        return 1

    if env_path.exists() and not args.force:
        print(f"[init] Keeping existing env file: {env_path}")
    else:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template_path, env_path)
        print(f"[init] Wrote env file from template: {env_path}")

    if args.check:
        print("[init] Running basic health check (energy only)...")
        check_code = _run_doctor_checks(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            skip_login_check=True,
            json_output=args.json,
        )
        if check_code != 0 and args.strict_check:
            return check_code

    print("[init] Next steps:")
    print("1) Ensure Energy service is healthy: uv run energycrawler energy ensure")
    print("2) Check auth readiness: uv run energycrawler auth status --json")
    print("3) Start a safe crawl: uv run energycrawler crawl -- --platform xhs --type search --keywords 新能源")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EnergyCrawler unified CLI",
        epilog=(
            "Examples:\n"
            "  uv run energycrawler init\n"
            "  uv run energycrawler energy ensure\n"
            "  uv run energycrawler auth status --json\n"
            "  uv run energycrawler crawl -- --platform xhs --type search --keywords 新能源\n"
            "  uv run energycrawler doctor --cleanup-report"
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
    doctor_parser.add_argument("--host", default=DEFAULT_HOST)
    doctor_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    doctor_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    doctor_parser.add_argument("--skip-login-check", action="store_true")
    doctor_parser.add_argument("--cleanup-report", action="store_true")
    doctor_parser.add_argument("--cleanup-fail-on-findings", action="store_true")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(handler=_doctor_cmd)

    init_parser = subparsers.add_parser("init", help="Bootstrap .env and run basic checks")
    init_parser.add_argument("--template", default=".env.quickstart.example")
    init_parser.add_argument("--env-file", default=".env")
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument(
        "--check",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    init_parser.add_argument("--strict-check", action="store_true")
    init_parser.add_argument("--host", default=DEFAULT_HOST)
    init_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    init_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    init_parser.add_argument("--json", action="store_true")
    init_parser.set_defaults(handler=_init_cmd)

    cleanup_parser = subparsers.add_parser(
        "cleanup-report",
        help="Report cleanup candidates (unused docs/images)",
    )
    cleanup_parser.add_argument("--json", action="store_true")
    cleanup_parser.add_argument("--fail-on-findings", action="store_true")
    cleanup_parser.set_defaults(handler=_cleanup_report_cmd)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    code = args.handler(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
