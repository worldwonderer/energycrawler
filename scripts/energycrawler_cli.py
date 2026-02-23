#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified CLI entrypoint for crawl/auth/energy/doctor/setup workflows."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TOOLS_DIR = PROJECT_ROOT / "tools"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 50051
DEFAULT_TIMEOUT = 8.0
DEFAULT_ENSURE_RETRIES = 3
DEFAULT_ENSURE_SLEEP = 2.0

RUNTIME_CONFIG_KEYS = [
    "PLATFORM",
    "CRAWLER_TYPE",
    "LOGIN_TYPE",
    "KEYWORDS",
    "HEADLESS",
    "SAVE_DATA_OPTION",
    "SAVE_DATA_PATH",
    "ENABLE_ENERGY_BROWSER",
    "ENERGY_SERVICE_ADDRESS",
    "ENERGY_HEADLESS",
    "ENERGY_BROWSER_ID_PREFIX",
    "ENERGY_BROWSER_ID",
    "COOKIES",
    "TWITTER_COOKIE",
    "TWITTER_AUTH_TOKEN",
    "TWITTER_CT0",
]
SENSITIVE_RUNTIME_KEYS = {"COOKIES", "TWITTER_COOKIE", "TWITTER_AUTH_TOKEN", "TWITTER_CT0"}

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _normalize_passthrough_args(raw: Sequence[str]) -> list[str]:
    args = list(raw)
    if args and args[0] == "--":
        return args[1:]
    return args


def _run_command(cmd: Sequence[str]) -> int:
    return subprocess.call(list(cmd), cwd=str(PROJECT_ROOT))


def _run_command_capture(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )


def _python_exec_prefix() -> list[str]:
    if shutil.which("uv"):
        return ["uv", "run", "python"]
    return [sys.executable]


def _run_python_entry(script_path: Path, args: Sequence[str]) -> int:
    cmd = [*_python_exec_prefix(), str(script_path), *list(args)]
    return _run_command(cmd)


def _run_python_entry_capture(script_path: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    cmd = [*_python_exec_prefix(), str(script_path), *list(args)]
    return _run_command_capture(cmd)


def _run_local_script(script_name: str, args: Sequence[str]) -> int:
    return _run_python_entry(SCRIPTS_DIR / script_name, args)


def _run_local_script_capture(script_name: str, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return _run_python_entry_capture(SCRIPTS_DIR / script_name, args)


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


def _parse_json_output(value: str) -> dict[str, Any] | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_check_detail(parsed_payload: dict[str, Any] | None, process: subprocess.CompletedProcess[str]) -> str:
    if parsed_payload:
        if "healthy" in parsed_payload:
            if parsed_payload.get("healthy"):
                return "healthy"
            steps = parsed_payload.get("steps", [])
            if isinstance(steps, list):
                for item in steps:
                    if isinstance(item, dict) and not item.get("ok", False):
                        detail = str(item.get("detail", "")).strip()
                        if detail:
                            return detail
            return "health check failed"
        if "results" in parsed_payload:
            results = parsed_payload.get("results", [])
            if isinstance(results, list):
                failures: list[str] = []
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    platform = str(item.get("platform", "")).strip() or "unknown"
                    env_ok = bool(item.get("env_ok"))
                    browser_ok = bool(item.get("browser_ok"))
                    if not env_ok:
                        failures.append(f"{platform}: {item.get('env_message', 'env check failed')}")
                    if not browser_ok:
                        failures.append(f"{platform}: {item.get('browser_message', 'browser check failed')}")
                if failures:
                    return "; ".join(failures[:2])
                return "login-state readiness passed"

    fallback = (process.stderr or process.stdout or "").strip()
    if not fallback:
        return "no output"
    return fallback.splitlines()[-1][:400]


def _run_script_check(name: str, script_name: str, args: Sequence[str]) -> dict[str, Any]:
    cmd_args = list(args)
    if "--json" not in cmd_args:
        cmd_args.append("--json")
    process = _run_local_script_capture(script_name, cmd_args)
    parsed_payload = _parse_json_output(process.stdout)
    return {
        "name": name,
        "ok": process.returncode == 0,
        "exit_code": process.returncode,
        "detail": _extract_check_detail(parsed_payload, process),
        "command": [script_name, *cmd_args],
        "payload": parsed_payload,
    }


def _run_energy_service_precheck(host: str, port: int, timeout: float) -> dict[str, Any]:
    return _run_script_check(
        "energy_service",
        "energy_service_cli.py",
        [
            "check",
            "--host",
            host,
            "--port",
            str(port),
            "--timeout",
            str(timeout),
        ],
    )


def _run_login_state_precheck(host: str, port: int, *, skip_browser_check: bool = True) -> dict[str, Any]:
    args: list[str] = [
        "status",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if skip_browser_check:
        args.append("--skip-browser-check")
    return _run_script_check("login_state", "auth_cli.py", args)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _check_tcp_connectivity(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP reachable at {host}:{port}"
    except OSError as exc:
        return False, f"TCP unreachable at {host}:{port}: {exc}"


def _load_base_config_module():
    return importlib.import_module("config.base_config")


def _load_db_config_module():
    return importlib.import_module("config.db_config")


def _run_storage_precheck(timeout: float) -> dict[str, Any]:
    base_config = _load_base_config_module()
    db_config = _load_db_config_module()
    save_option = str(getattr(base_config, "SAVE_DATA_OPTION", "json")).strip().lower() or "json"
    save_data_path = str(getattr(base_config, "SAVE_DATA_PATH", "")).strip()

    result: dict[str, Any] = {
        "name": "storage_precheck",
        "ok": False,
        "exit_code": 1,
        "detail": "",
        "command": [],
        "payload": {
            "save_option": save_option,
            "save_data_path": save_data_path,
        },
    }

    if save_option in {"json", "csv", "excel"}:
        target_dir = Path(save_data_path).expanduser() if save_data_path else (PROJECT_ROOT / "data")
        check_target = target_dir if target_dir.exists() else target_dir.parent
        writable = check_target.exists() and os.access(check_target, os.W_OK)
        result["ok"] = writable
        result["exit_code"] = 0 if writable else 1
        result["detail"] = (
            f"{save_option} target path writable: {target_dir}"
            if writable
            else f"{save_option} target path not writable: {target_dir}"
        )
        result["payload"]["target_dir"] = str(target_dir)
        result["payload"]["target_exists"] = target_dir.exists()
        return result

    if save_option == "sqlite":
        sqlite_path = Path(str(getattr(db_config, "SQLITE_DB_PATH", PROJECT_ROOT / "database" / "sqlite_tables.db")))
        try:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(sqlite_path), timeout=max(0.1, timeout))
            conn.execute("select 1")
            conn.close()
            result["ok"] = True
            result["exit_code"] = 0
            result["detail"] = f"sqlite connection ok: {sqlite_path}"
            result["payload"]["sqlite_db_path"] = str(sqlite_path)
            return result
        except Exception as exc:  # pragma: no cover - defensive fallback
            result["detail"] = f"sqlite connection failed ({sqlite_path}): {exc}"
            result["payload"]["sqlite_db_path"] = str(sqlite_path)
            return result

    if save_option in {"db", "mysql"}:
        host = str(getattr(db_config, "MYSQL_DB_HOST", "localhost"))
        port = _safe_int(getattr(db_config, "MYSQL_DB_PORT", 3306), 3306)
        ok, detail = _check_tcp_connectivity(host, port, timeout)
        result["ok"] = ok
        result["exit_code"] = 0 if ok else 1
        result["detail"] = f"mysql {detail}"
        result["payload"]["host"] = host
        result["payload"]["port"] = port
        return result

    if save_option == "postgres":
        host = str(getattr(db_config, "POSTGRES_DB_HOST", "localhost"))
        port = _safe_int(getattr(db_config, "POSTGRES_DB_PORT", 5432), 5432)
        ok, detail = _check_tcp_connectivity(host, port, timeout)
        result["ok"] = ok
        result["exit_code"] = 0 if ok else 1
        result["detail"] = f"postgres {detail}"
        result["payload"]["host"] = host
        result["payload"]["port"] = port
        return result

    if save_option == "mongodb":
        host = str(getattr(db_config, "MONGODB_HOST", "localhost"))
        port = _safe_int(getattr(db_config, "MONGODB_PORT", 27017), 27017)
        ok, detail = _check_tcp_connectivity(host, port, timeout)
        result["ok"] = ok
        result["exit_code"] = 0 if ok else 1
        result["detail"] = f"mongodb {detail}"
        result["payload"]["host"] = host
        result["payload"]["port"] = port
        return result

    result["detail"] = f"unsupported SAVE_DATA_OPTION for precheck: {save_option}"
    return result


def _run_precheck_suite(
    *,
    host: str,
    port: int,
    timeout: float,
    skip_login_check: bool,
    storage_check: bool,
    login_required: bool = True,
    storage_required: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    energy = _run_energy_service_precheck(host, port, timeout)
    energy["required"] = True
    checks.append(energy)

    if not skip_login_check:
        login_check = _run_login_state_precheck(host, port, skip_browser_check=True)
        login_check["required"] = bool(login_required)
        checks.append(login_check)

    if storage_check:
        storage = _run_storage_precheck(timeout)
        storage["required"] = bool(storage_required)
        checks.append(storage)

    return {
        "host": host,
        "port": port,
        "timeout_sec": timeout,
        "checks": checks,
        "all_checks_passed": all(check.get("ok", False) for check in checks),
        "healthy": all(check.get("ok", False) or not check.get("required", True) for check in checks),
    }


def _print_precheck_human(payload: dict[str, Any], *, prefix: str) -> None:
    checks = payload.get("checks", [])
    for check in checks:
        if check.get("ok"):
            status = "PASS"
        elif check.get("required", True):
            status = "FAIL"
        else:
            status = "WARN"
        print(f"{prefix} {status}: {check.get('name')} - {check.get('detail', '')}")

    if payload.get("healthy"):
        print(f"{prefix} Summary: all required checks passed")
    else:
        print(f"{prefix} Summary: required checks failed")
        print("Try: uv run energycrawler energy ensure")


def _run_cleanup_report_check(*, json_output: bool, fail_on_findings: bool) -> dict[str, Any]:
    cmd_args: list[str] = []
    if json_output:
        cmd_args.append("--json")
    if fail_on_findings:
        cmd_args.append("--fail-on-findings")
    process = _run_python_entry_capture(TOOLS_DIR / "cleanup_report.py", cmd_args)
    payload = _parse_json_output(process.stdout)
    return {
        "name": "cleanup_report",
        "ok": process.returncode == 0,
        "exit_code": process.returncode,
        "detail": _extract_check_detail(payload, process),
        "command": ["cleanup_report.py", *cmd_args],
        "payload": payload,
    }


def _truncate_text(value: str, limit: int = 600) -> str:
    raw = (value or "").strip()
    if len(raw) <= limit:
        return raw
    return f"{raw[:limit]}... (truncated)"


def _run_doctor_checks(
    *,
    host: str,
    port: int,
    timeout: float,
    json_output: bool,
    skip_login_check: bool,
    storage_check: bool,
) -> int:
    payload = _run_precheck_suite(
        host=host,
        port=port,
        timeout=timeout,
        skip_login_check=skip_login_check,
        storage_check=storage_check,
        login_required=True,
        storage_required=True,
    )
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_precheck_human(payload, prefix="[doctor]")
    return 0 if payload.get("healthy") else 1


def _doctor_cmd(args: argparse.Namespace) -> int:
    if args.json and args.cleanup_report:
        doctor_payload = _run_precheck_suite(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            skip_login_check=args.skip_login_check,
            storage_check=args.storage_check,
            login_required=True,
            storage_required=True,
        )
        cleanup_result = _run_cleanup_report_check(
            json_output=True,
            fail_on_findings=args.cleanup_fail_on_findings,
        )
        print(
            json.dumps(
                {
                    "doctor": doctor_payload,
                    "cleanup_report": cleanup_result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        cleanup_code = 0 if cleanup_result.get("ok") else 1
        if cleanup_code != 0:
            return cleanup_code
        return 0 if doctor_payload.get("healthy") else 1

    check_code = _run_doctor_checks(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        json_output=args.json,
        skip_login_check=args.skip_login_check,
        storage_check=args.storage_check,
    )

    if check_code != 0 and not args.cleanup_report:
        return check_code

    if args.cleanup_report:
        if args.json:
            cleanup_result = _run_cleanup_report_check(
                json_output=True,
                fail_on_findings=args.cleanup_fail_on_findings,
            )
            print(json.dumps({"cleanup_report": cleanup_result}, ensure_ascii=False, indent=2))
            cleanup_code = 0 if cleanup_result.get("ok") else 1
        else:
            print("[doctor] Running: Cleanup candidate report")
            cleanup_code = _run_cleanup_report(
                json_output=False,
                fail_on_findings=args.cleanup_fail_on_findings,
            )
        if cleanup_code != 0:
            return cleanup_code

    if not args.json:
        if check_code == 0:
            print("[doctor] Summary: all checks passed")
        else:
            print("[doctor] Summary: checks failed")
    return check_code


def _resolve_project_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _prepare_env_file(*, template_path: Path, env_path: Path, force: bool) -> tuple[bool, str]:
    if not template_path.exists():
        return False, f"Template not found: {template_path}"

    if env_path.exists() and not force:
        return True, f"Keeping existing env file: {env_path}"

    env_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_path, env_path)
    return True, f"Wrote env file from template: {env_path}"


def _init_cmd(args: argparse.Namespace) -> int:
    template_path = _resolve_project_path(args.template)
    env_path = _resolve_project_path(args.env_file)

    ok, detail = _prepare_env_file(template_path=template_path, env_path=env_path, force=args.force)
    if not ok:
        print(f"[init] {detail}", file=sys.stderr)
        return 1
    print(f"[init] {detail}")

    if args.check:
        print("[init] Running basic health check (energy only)...")
        check_code = _run_doctor_checks(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            skip_login_check=True,
            json_output=args.json,
            storage_check=False,
        )
        if check_code != 0 and args.strict_check:
            return check_code

    print("[init] Next steps:")
    print("1) Ensure Energy service is healthy: uv run energycrawler energy ensure")
    print("2) Check auth readiness: uv run energycrawler auth status --json")
    print("3) Start a safe crawl: uv run energycrawler crawl -- --platform xhs --type search --keywords 新能源")
    return 0


def _mask_secret(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]} ({len(raw)} chars)"


def _collect_runtime_config(*, show_secrets: bool) -> dict[str, Any]:
    base_config = _load_base_config_module()
    payload: dict[str, Any] = {}
    for key in RUNTIME_CONFIG_KEYS:
        if hasattr(base_config, key):
            payload[key] = getattr(base_config, key)

    resolver = getattr(base_config, "resolve_energy_browser_id", None)
    if callable(resolver):
        payload["ENERGY_BROWSER_ID_RESOLVED"] = resolver(payload.get("PLATFORM"))

    if not show_secrets:
        for key in SENSITIVE_RUNTIME_KEYS:
            if key in payload:
                payload[key] = _mask_secret(str(payload[key]))

    return payload


def _config_show_cmd(args: argparse.Namespace) -> int:
    payload = {
        "project_root": str(PROJECT_ROOT),
        "runtime_config": _collect_runtime_config(show_secrets=args.show_secrets),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"project_root={payload['project_root']}")
        for key in sorted(payload["runtime_config"]):
            print(f"{key}={payload['runtime_config'][key]}")
    return 0


def _build_setup_next_steps(payload: dict[str, Any]) -> list[str]:
    by_name = {item.get("name"): item for item in payload.get("steps", [])}
    lines: list[str] = []

    energy_step = by_name.get("energy_ensure")
    if energy_step and not energy_step.get("ok", False):
        lines.append("Ensure Energy service: uv run energycrawler energy ensure")

    doctor_step = by_name.get("doctor_precheck")
    if doctor_step and not doctor_step.get("ok", False):
        lines.append("Run diagnostics: uv run energycrawler doctor --storage-check")

    login_step = by_name.get("login_readiness")
    if login_step and not login_step.get("ok", False):
        lines.append("Check login state: uv run energycrawler auth status --json")

    if not lines:
        lines.append("Start crawling: uv run energycrawler crawl -- --platform xhs --type search --keywords 新能源")
    return lines


def _setup_cmd(args: argparse.Namespace) -> int:
    template_path = _resolve_project_path(args.template)
    env_path = _resolve_project_path(args.env_file)
    steps: list[dict[str, Any]] = []

    env_ok, env_detail = _prepare_env_file(template_path=template_path, env_path=env_path, force=args.force)
    steps.append(
        {
            "name": "env_file",
            "ok": env_ok,
            "required": True,
            "detail": env_detail,
        }
    )

    ensure_args = [
        "ensure",
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
    ensure_stdout = ""
    ensure_stderr = ""
    if args.json:
        ensure_process = _run_local_script_capture("energy_service_cli.py", ensure_args)
        ensure_code = ensure_process.returncode
        ensure_stdout = _truncate_text(ensure_process.stdout)
        ensure_stderr = _truncate_text(ensure_process.stderr)
    else:
        ensure_code = _run_local_script("energy_service_cli.py", ensure_args)
    steps.append(
        {
            "name": "energy_ensure",
            "ok": ensure_code == 0,
            "required": True,
            "detail": "energy service ensure succeeded" if ensure_code == 0 else f"energy ensure failed (exit code {ensure_code})",
            "exit_code": ensure_code,
            "command": ["energy_service_cli.py", *ensure_args],
            **({"stdout": ensure_stdout} if ensure_stdout else {}),
            **({"stderr": ensure_stderr} if ensure_stderr else {}),
        }
    )

    doctor_payload = _run_precheck_suite(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        skip_login_check=True,
        storage_check=args.storage_check,
        login_required=False,
        storage_required=bool(args.strict),
    )
    steps.append(
        {
            "name": "doctor_precheck",
            "ok": bool(doctor_payload.get("healthy")),
            "required": bool(args.strict),
            "detail": "doctor precheck passed" if doctor_payload.get("healthy") else "doctor precheck has issues",
            "payload": doctor_payload,
        }
    )

    if not args.skip_login_readiness:
        login_check = _run_login_state_precheck(
            args.host,
            args.port,
            skip_browser_check=args.skip_browser_check,
        )
        login_check["name"] = "login_readiness"
        login_check["required"] = bool(args.strict)
        steps.append(login_check)

    payload = {
        "setup_ok": all(step.get("ok", False) or not step.get("required", True) for step in steps),
        "strict": bool(args.strict),
        "steps": steps,
    }
    payload["next_steps"] = _build_setup_next_steps(payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for step in payload["steps"]:
            if step.get("ok"):
                status = "PASS"
            elif step.get("required", True):
                status = "FAIL"
            else:
                status = "WARN"
            print(f"[setup] {status}: {step.get('name')} - {step.get('detail', '')}")
        print("[setup] Next steps:")
        for index, line in enumerate(payload["next_steps"], start=1):
            print(f"{index}) {line}")

    return 0 if payload["setup_ok"] else 1


def _add_doctor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--skip-login-check", action="store_true")
    parser.add_argument("--storage-check", action="store_true")
    parser.add_argument("--cleanup-report", action="store_true")
    parser.add_argument("--cleanup-fail-on-findings", action="store_true")
    parser.add_argument("--json", action="store_true")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EnergyCrawler unified CLI",
        epilog=(
            "Examples:\n"
            "  uv run energycrawler init\n"
            "  uv run energycrawler setup --storage-check\n"
            "  uv run energycrawler config show --json\n"
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
    _add_doctor_arguments(doctor_parser)
    doctor_parser.set_defaults(handler=_doctor_cmd)

    precheck_parser = subparsers.add_parser("precheck", help="Run doctor precheck suite")
    _add_doctor_arguments(precheck_parser)
    precheck_parser.set_defaults(handler=_doctor_cmd)

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

    setup_parser = subparsers.add_parser("setup", help="One-command setup wizard")
    setup_parser.add_argument("--template", default=".env.quickstart.example")
    setup_parser.add_argument("--env-file", default=".env")
    setup_parser.add_argument("--force", action="store_true")
    setup_parser.add_argument("--host", default=DEFAULT_HOST)
    setup_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    setup_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    setup_parser.add_argument("--retries", type=int, default=DEFAULT_ENSURE_RETRIES)
    setup_parser.add_argument("--sleep", type=float, default=DEFAULT_ENSURE_SLEEP)
    setup_parser.add_argument("--storage-check", action="store_true")
    setup_parser.add_argument("--skip-browser-check", action="store_true")
    setup_parser.add_argument("--skip-login-readiness", action="store_true")
    setup_parser.add_argument("--strict", action="store_true")
    setup_parser.add_argument("--json", action="store_true")
    setup_parser.set_defaults(handler=_setup_cmd)

    config_parser = subparsers.add_parser("config", help="Configuration helpers")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_show_parser = config_subparsers.add_parser("show", help="Show runtime config")
    config_show_parser.add_argument("--show-secrets", action="store_true")
    config_show_parser.add_argument("--json", action="store_true")
    config_show_parser.set_defaults(handler=_config_show_cmd)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    code = args.handler(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
