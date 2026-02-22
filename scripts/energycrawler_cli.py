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
TOOLS_DIR = PROJECT_ROOT / "tools"


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


def _run_cleanup_report(*, json_output: bool, fail_on_findings: bool) -> int:
    cmd_args = []
    if json_output:
        cmd_args.append("--json")
    if fail_on_findings:
        cmd_args.append("--fail-on-findings")
    cmd = _build_python_target_command(TOOLS_DIR / "cleanup_report.py", cmd_args)
    return _run_command(cmd)


def _cleanup_report_cmd(args: argparse.Namespace) -> int:
    return _run_cleanup_report(
        json_output=args.json,
        fail_on_findings=args.fail_on_findings,
    )


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

    if getattr(args, "cleanup_report", False):
        print("[doctor] Running: Cleanup candidate report")
        cleanup_code = _run_cleanup_report(
            json_output=args.json,
            fail_on_findings=getattr(args, "cleanup_fail_on_findings", False),
        )
        if cleanup_code != 0:
            return cleanup_code

    print("[doctor] Summary: all checks passed")
    return 0


def _resolve_project_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


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
        doctor_args = argparse.Namespace(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            skip_login_check=True,
            json=args.json,
            cleanup_report=False,
            cleanup_fail_on_findings=False,
        )
        check_code = _doctor_cmd(doctor_args)
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
    doctor_parser.add_argument("--host", default="localhost")
    doctor_parser.add_argument("--port", type=int, default=50051)
    doctor_parser.add_argument("--timeout", type=float, default=8.0)
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
    init_parser.add_argument("--host", default="localhost")
    init_parser.add_argument("--port", type=int, default=50051)
    init_parser.add_argument("--timeout", type=float, default=8.0)
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
