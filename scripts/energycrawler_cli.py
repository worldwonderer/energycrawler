#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified CLI entrypoint for crawl/auth/energy/doctor/setup workflows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from typing import Any, Sequence
import urllib.error
import urllib.parse
import urllib.request
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TOOLS_DIR = PROJECT_ROOT / "tools"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 50051
DEFAULT_TIMEOUT = 8.0
DEFAULT_ENSURE_RETRIES = 3
DEFAULT_ENSURE_SLEEP = 2.0
DEFAULT_API_BASE = os.getenv("ENERGYCRAWLER_API_BASE", "http://127.0.0.1:8080")
DEFAULT_API_TIMEOUT = 15.0

SIMPLE_SAFETY_DEFAULTS: dict[str, dict[str, float | int]] = {
    "safe": {"max_notes_count": 5, "crawl_sleep_sec": 10.0},
    "balanced": {"max_notes_count": 10, "crawl_sleep_sec": 8.0},
    "aggressive": {"max_notes_count": 20, "crawl_sleep_sec": 6.0},
}

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
CORE_RUNTIME_CONFIG_KEYS = [
    "PLATFORM",
    "CRAWLER_TYPE",
    "LOGIN_TYPE",
    "KEYWORDS",
    "SAVE_DATA_OPTION",
    "SAVE_DATA_PATH",
    "ENABLE_ENERGY_BROWSER",
    "ENERGY_SERVICE_ADDRESS",
]
SENSITIVE_RUNTIME_KEYS = {"COOKIES", "TWITTER_COOKIE", "TWITTER_AUTH_TOKEN", "TWITTER_CT0"}
CORE_ENV_KEYS = [
    "PLATFORM",
    "CRAWLER_TYPE",
    "LOGIN_TYPE",
    "KEYWORDS",
    "HEADLESS",
    "SAVE_DATA_OPTION",
    "ENERGY_SERVICE_ADDRESS",
    "CRAWLER_MAX_NOTES_COUNT",
    "MAX_CONCURRENCY_NUM",
    "CRAWLER_MAX_SLEEP_SEC",
    "COOKIES",
    "TWITTER_AUTH_TOKEN",
    "TWITTER_CT0",
]
ADVANCED_ENV_KEYS = [
    "SAVE_DATA_PATH",
    "TWITTER_COOKIE",
    "COOKIECLOUD_ENABLED",
    "COOKIECLOUD_FORCE_SYNC",
    "COOKIECLOUD_SERVER",
    "COOKIECLOUD_UUID",
    "COOKIECLOUD_PASSWORD",
    "COOKIECLOUD_TIMEOUT_SEC",
    "AUTH_WATCHDOG_ENABLED",
    "AUTH_WATCHDOG_MAX_RETRIES",
    "AUTH_WATCHDOG_RETRY_INTERVAL_SEC",
    "AUTH_WATCHDOG_FORCE_COOKIECLOUD_SYNC",
    "AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES",
    "CRAWLER_HARD_MAX_NOTES_COUNT",
    "CRAWLER_HARD_MAX_CONCURRENCY",
    "CRAWLER_MIN_SLEEP_SEC",
    "CRAWLER_SLEEP_JITTER_SEC",
    "CRAWLER_RETRY_BASE_DELAY_SEC",
    "CRAWLER_RETRY_MAX_DELAY_SEC",
    "XHS_SIGNATURE_CANARY_ENABLED",
    "XHS_SIGNATURE_CANARY_TIMEOUT_SEC",
    "XHS_SIGNATURE_CANARY_BASELINE_PATH",
    "XHS_SIGNATURE_SESSION_TTL_SEC",
    "XHS_SIGNATURE_FAILURE_THRESHOLD",
    "MYSQL_DB_HOST",
    "MYSQL_DB_PORT",
    "MYSQL_DB_USER",
    "MYSQL_DB_PWD",
    "MYSQL_DB_NAME",
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_USER",
    "MONGODB_PWD",
    "MONGODB_DB_NAME",
    "POSTGRES_DB_HOST",
    "POSTGRES_DB_PORT",
    "POSTGRES_DB_USER",
    "POSTGRES_DB_PWD",
    "POSTGRES_DB_NAME",
]
SENSITIVE_ENV_KEYS = {
    "COOKIES",
    "TWITTER_COOKIE",
    "TWITTER_AUTH_TOKEN",
    "TWITTER_CT0",
    "COOKIECLOUD_PASSWORD",
    "COOKIECLOUD_UUID",
    "MYSQL_DB_PWD",
    "MONGODB_PWD",
    "POSTGRES_DB_PWD",
}

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _normalize_passthrough_args(raw: Sequence[str]) -> list[str]:
    args = list(raw)
    if args and args[0] == "--":
        return args[1:]
    return args


def _extract_option_value(args: Sequence[str], flag: str) -> str | None:
    for idx, item in enumerate(args):
        if item == flag:
            if idx + 1 < len(args):
                next_item = args[idx + 1]
                if not next_item.startswith("-"):
                    return next_item
            return None
        if item.startswith(f"{flag}="):
            return item.split("=", 1)[1]
    return None


def _default_platform() -> str:
    return (os.getenv("PLATFORM", "xhs") or "xhs").strip().lower() or "xhs"


def _build_auto_browser_id(platform: str) -> str:
    prefix = (os.getenv("ENERGY_BROWSER_ID_PREFIX", "energycrawler") or "energycrawler").strip()
    normalized_platform = (platform or _default_platform()).strip().lower() or "xhs"
    return f"{prefix}_{normalized_platform}_cli_{os.getpid()}_{uuid.uuid4().hex[:8]}"


def _runtime_env_with_auto_browser_id(platform: str | None = None) -> dict[str, str] | None:
    manual_browser_id = (os.getenv("ENERGYCRAWLER_BROWSER_ID", "") or "").strip()
    if manual_browser_id:
        return None

    resolved_platform = (platform or _default_platform()).strip().lower() or "xhs"
    return {
        **os.environ,
        "ENERGYCRAWLER_BROWSER_ID": _build_auto_browser_id(resolved_platform),
    }


def _run_command(cmd: Sequence[str], *, env: dict[str, str] | None = None) -> int:
    return subprocess.call(list(cmd), cwd=str(PROJECT_ROOT), env=env)


def _run_command_capture(
    cmd: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def _python_exec_prefix() -> list[str]:
    if shutil.which("uv"):
        return ["uv", "run", "python"]
    return [sys.executable]


def _run_python_entry(
    script_path: Path,
    args: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> int:
    cmd = [*_python_exec_prefix(), str(script_path), *list(args)]
    return _run_command(cmd, env=env)


def _run_python_entry_capture(
    script_path: Path,
    args: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [*_python_exec_prefix(), str(script_path), *list(args)]
    return _run_command_capture(cmd, env=env)


def _run_local_script(script_name: str, args: Sequence[str]) -> int:
    return _run_python_entry(SCRIPTS_DIR / script_name, args)


def _run_local_script_capture(script_name: str, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return _run_python_entry_capture(SCRIPTS_DIR / script_name, args)


def _crawl_cmd(args: argparse.Namespace) -> int:
    passthrough = _normalize_passthrough_args(args.args)
    platform = _extract_option_value(passthrough, "--platform") or _default_platform()
    run_env = _runtime_env_with_auto_browser_id(platform)
    return _run_python_entry(PROJECT_ROOT / "main.py", passthrough, env=run_env)


def _auth_cmd(args: argparse.Namespace) -> int:
    return _run_local_script("auth_cli.py", _normalize_passthrough_args(args.args))


def _energy_cmd(args: argparse.Namespace) -> int:
    return _run_local_script("energy_service_cli.py", _normalize_passthrough_args(args.args))


def _contains_flag(args: Sequence[str], flag: str) -> bool:
    prefix = f"{flag}="
    return any(item == flag or item.startswith(prefix) for item in args)


def _require_non_empty(value: str, message: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(message)
    return cleaned


def _build_simple_run_args(args: argparse.Namespace) -> list[str]:
    crawler_type = str(args.crawler_type).strip().lower()
    if crawler_type not in {"search", "detail", "creator"}:
        raise ValueError(f"Unsupported crawler type: {crawler_type}")

    platform = str(args.platform).strip().lower()
    if platform not in {"xhs", "x"}:
        raise ValueError(f"Unsupported platform: {platform}")

    run_args = [
        "--platform",
        platform,
        "--lt",
        "cookie",
        "--type",
        crawler_type,
        "--save_data_option",
        str(args.save_option).strip().lower(),
        "--headless",
        "true" if bool(args.headless) else "false",
    ]

    if crawler_type == "search":
        run_args.extend(
            [
                "--keywords",
                _require_non_empty(args.keywords, "run mode=search requires --keywords"),
            ]
        )
    elif crawler_type == "detail":
        run_args.extend(
            [
                "--specified_id",
                _require_non_empty(args.specified_id, "run mode=detail requires --specified-id"),
            ]
        )
    else:
        run_args.extend(
            [
                "--creator_id",
                _require_non_empty(args.creator_id, "run mode=creator requires --creator-id"),
            ]
        )

    extra = _normalize_passthrough_args(args.extra)
    safety_profile = str(args.safety_profile).strip().lower()
    defaults = SIMPLE_SAFETY_DEFAULTS.get(safety_profile)
    if defaults is None:
        raise ValueError(
            f"Unsupported safety profile: {safety_profile} "
            f"(expected one of {', '.join(sorted(SIMPLE_SAFETY_DEFAULTS))})"
        )

    if not _contains_flag(extra, "--max_notes_count"):
        run_args.extend(["--max_notes_count", str(int(defaults["max_notes_count"]))])
    if not _contains_flag(extra, "--crawl_sleep_sec"):
        run_args.extend(["--crawl_sleep_sec", str(float(defaults["crawl_sleep_sec"]))])

    run_args.extend(extra)
    return run_args


def _run_simple_cmd(args: argparse.Namespace) -> int:
    try:
        forwarded = _build_simple_run_args(args)
    except ValueError as exc:
        print(f"[run] {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print("uv run python main.py " + " ".join(forwarded))
        return 0

    run_env = _runtime_env_with_auto_browser_id(str(args.platform))
    print(
        "[run] profile="
        f"{args.safety_profile} platform={args.platform} type={args.crawler_type} "
        "-> forwarding to main.py"
    )
    return _run_python_entry(PROJECT_ROOT / "main.py", forwarded, env=run_env)


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


def _normalize_api_base(api_base: str) -> str:
    base = (api_base or "").strip() or DEFAULT_API_BASE
    base = base.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    return base


def _build_api_url(api_base: str, endpoint: str, params: dict[str, Any] | None = None) -> str:
    base = _normalize_api_base(api_base)
    path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    if not params:
        return f"{base}{path}"

    query_items: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            query_items[key] = "true" if value else "false"
        else:
            query_items[key] = str(value)

    if not query_items:
        return f"{base}{path}"
    return f"{base}{path}?{urllib.parse.urlencode(query_items)}"


def _api_request(
    *,
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = DEFAULT_API_TIMEOUT,
) -> tuple[int, bytes, dict[str, str]]:
    body: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
            return status, response.read(), headers
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 500))
        headers = {str(key).lower(): str(value) for key, value in (exc.headers.items() if exc.headers else [])}
        return status, exc.read(), headers
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise ConnectionError(str(reason)) from exc


def _api_fetch(url: str, *, timeout: float = DEFAULT_API_TIMEOUT) -> tuple[int, bytes, dict[str, str]]:
    return _api_request(url=url, method="GET", timeout=timeout)


def _parse_json_bytes(raw: bytes) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_api_error_message(payload: dict[str, Any] | None, fallback: str) -> str:
    if payload and isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message", "")).strip()
            if message:
                return message
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return fallback


def _filename_from_content_disposition(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for part in raw.split(";"):
        item = part.strip()
        if item.lower().startswith("filename="):
            filename = item.split("=", 1)[1].strip().strip('"').strip("'")
            return filename or None
    return None


def _resolve_download_output_path(output: str | None, filename: str) -> Path:
    if not output:
        return Path(filename)

    candidate = Path(output).expanduser()
    if candidate.exists() and candidate.is_dir():
        return candidate / filename
    return candidate


def _print_latest_preview_summary(payload: dict[str, Any]) -> None:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    file_info = data.get("file", {}) if isinstance(data, dict) else {}
    name = file_info.get("name", "unknown")
    file_type = file_info.get("type", "unknown")
    total = data.get("total")
    if total is None:
        total = file_info.get("record_count", "unknown")
    print(f"[data latest] file={name}")
    print(f"[data latest] type={file_type}")
    print(f"[data latest] records={total}")


def _print_next_steps(prefix: str, steps: Sequence[str], *, stream: Any) -> None:
    actionable = [str(step).strip() for step in steps if str(step).strip()]
    if not actionable:
        return
    print(f"{prefix} Actionable next steps:", file=stream)
    for index, step in enumerate(actionable, start=1):
        print(f"{index}) {step}", file=stream)


def _build_api_unreachable_hints(*, api_base: str) -> list[str]:
    normalized = _normalize_api_base(api_base)
    return [
        "Start API service: uv run uvicorn api.main:app --port 8080 --reload",
        f"Verify API health: curl -s {normalized}/api/health",
        "Ensure Energy service is ready: uv run energycrawler energy ensure",
    ]


def _build_no_data_file_hints(*, platform: str | None) -> list[str]:
    platform_hint = (platform or "xhs").strip() or "xhs"
    return [
        f"Run a crawl first: uv run energycrawler run --platform {platform_hint} --keywords 新能源",
        "Then retry file list: uv run energycrawler data list",
        f"Or preview latest file: uv run energycrawler data latest --platform {platform_hint}",
    ]


def _format_modified_at(value: Any) -> str:
    try:
        timestamp = float(value)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except Exception:
        return str(value)


def _build_status_next_steps(runtime_data: dict[str, Any], *, api_base: str) -> list[str]:
    steps: list[str] = []
    energy = runtime_data.get("energy")
    if isinstance(energy, dict) and not bool(energy.get("ok", False)):
        steps.append("Recover Energy service: uv run energycrawler energy ensure")
        steps.append("Probe Energy health details: uv run energycrawler energy check --json")

    login = runtime_data.get("login")
    if isinstance(login, dict):
        xhs = login.get("xhs")
        if isinstance(xhs, dict) and not bool(xhs.get("ok", False)):
            steps.append(
                f"Finish XHS open+sync+verify flow: uv run energycrawler auth xhs-open-login --api-base {_normalize_api_base(api_base)}"
            )
        x_login = login.get("x")
        if isinstance(x_login, dict) and not bool(x_login.get("ok", False)):
            steps.append("Repair X login material: uv run energycrawler auth status --json")

    queue = runtime_data.get("crawler_queue")
    if isinstance(queue, dict) and not bool(queue.get("healthy", True)):
        steps.append("Inspect crawler queue/runtime: uv run energycrawler doctor --json")

    if not steps:
        steps.append("Run full diagnostics: uv run energycrawler doctor --json")

    deduped: list[str] = []
    seen: set[str] = set()
    for step in steps:
        if step in seen:
            continue
        seen.add(step)
        deduped.append(step)
    return deduped


def _print_status_summary(payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    data = payload.get("data")
    runtime_data = data if isinstance(data, dict) else payload
    if not isinstance(runtime_data, dict):
        runtime_data = {}

    overall_status = str(runtime_data.get("overall_status", "unknown"))
    checked_at = str(runtime_data.get("checked_at", "unknown"))
    overall_healthy = bool(runtime_data.get("overall_healthy", False))

    print(f"[status] overall={overall_status} healthy={overall_healthy} checked_at={checked_at}")

    energy = runtime_data.get("energy", {})
    if isinstance(energy, dict):
        print(f"[status] energy_ok={bool(energy.get('ok', False))} message={energy.get('message', '')}")

    login = runtime_data.get("login", {})
    if isinstance(login, dict):
        for platform in ("xhs", "x"):
            item = login.get(platform, {})
            if isinstance(item, dict):
                print(
                    f"[status] login_{platform}_ok={bool(item.get('ok', False))} "
                    f"message={item.get('message', '')}"
                )

    queue = runtime_data.get("crawler_queue", {})
    if isinstance(queue, dict):
        print(
            "[status] queue_healthy="
            f"{bool(queue.get('healthy', False))} status={queue.get('status', 'unknown')} "
            f"running={queue.get('running_workers', 0)}/{queue.get('total_workers', 0)} "
            f"queued={queue.get('queued_tasks', 0)}"
        )

    return overall_healthy, runtime_data


def _status_cmd(args: argparse.Namespace) -> int:
    try:
        url = _build_api_url(args.api_base, "/api/health/runtime")
        status, body, _headers = _api_fetch(url, timeout=args.timeout)
        payload = _parse_json_bytes(body)
        if status != 200:
            message = _extract_api_error_message(payload, f"HTTP {status}")
            print(f"[status] Runtime status check failed (HTTP {status}): {message}", file=sys.stderr)
            _print_next_steps("[status]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
            return 1

        if payload is None:
            print("[status] Invalid JSON response from API", file=sys.stderr)
            _print_next_steps("[status]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
            return 1

        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        overall_healthy = bool(data.get("overall_healthy", False)) if isinstance(data, dict) else False

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if overall_healthy else 1

        healthy, runtime_data = _print_status_summary(payload)
        if healthy:
            print("[status] Summary: all runtime checks passed")
            return 0

        _print_next_steps(
            "[status]",
            _build_status_next_steps(runtime_data, api_base=args.api_base),
            stream=sys.stdout,
        )
        return 1
    except ConnectionError as exc:
        print(f"[status] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps("[status]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
        return 2


def _print_data_list_summary(files: Sequence[dict[str, Any]], *, limit: int) -> None:
    shown = list(files[:limit])
    print(f"[data list] total_files={len(files)} showing={len(shown)}")
    for index, item in enumerate(shown, start=1):
        path = str(item.get("path", item.get("name", "unknown")))
        file_type = str(item.get("type", "unknown"))
        records = item.get("record_count")
        size = item.get("size")
        modified_at = _format_modified_at(item.get("modified_at"))
        print(
            f"[data list] {index}. path={path} type={file_type} "
            f"records={records} size={size} modified_at={modified_at}"
        )


def _data_list_cmd(args: argparse.Namespace) -> int:
    if args.limit < 1:
        print("[data list] --limit must be >= 1", file=sys.stderr)
        return 2

    query: dict[str, Any] = {
        "platform": args.platform,
        "file_type": args.file_type,
    }

    try:
        url = _build_api_url(args.api_base, "/api/data/files", query)
        status, body, _headers = _api_fetch(url)
        payload = _parse_json_bytes(body)
        if status != 200:
            message = _extract_api_error_message(payload, f"HTTP {status}")
            print(f"[data list] List failed (HTTP {status}): {message}", file=sys.stderr)
            _print_next_steps("[data list]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
            return 1

        if payload is None:
            print("[data list] Invalid JSON response from API", file=sys.stderr)
            return 1

        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        files = data.get("files", []) if isinstance(data, dict) else []
        if not isinstance(files, list):
            files = []

        if not files:
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print("[data list] No data files found for current filters", file=sys.stderr)
            _print_next_steps(
                "[data list]",
                _build_no_data_file_hints(platform=args.platform),
                stream=sys.stderr,
            )
            return 4

        shown = files[: args.limit]
        if args.json:
            output_payload = payload.copy()
            output_data = dict(data)
            output_data["files"] = shown
            output_data["total_files"] = len(files)
            output_data["shown"] = len(shown)
            output_payload["data"] = output_data
            print(json.dumps(output_payload, ensure_ascii=False, indent=2))
        else:
            _print_data_list_summary(files, limit=args.limit)
        return 0
    except ConnectionError as exc:
        print(f"[data list] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps("[data list]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
        return 2


def _data_latest_cmd(args: argparse.Namespace) -> int:
    if args.limit < 1:
        print("[data latest] --limit must be >= 1", file=sys.stderr)
        return 2

    query: dict[str, Any] = {
        "platform": args.platform,
        "file_type": args.file_type,
    }

    try:
        if args.download:
            url = _build_api_url(args.api_base, "/api/data/latest/download", query)
            status, body, headers = _api_fetch(url)
            if status != 200:
                payload = _parse_json_bytes(body)
                message = _extract_api_error_message(payload, f"HTTP {status}")
                if status == 404:
                    print(f"[data latest] No latest file found: {message}", file=sys.stderr)
                    _print_next_steps(
                        "[data latest]",
                        _build_no_data_file_hints(platform=args.platform),
                        stream=sys.stderr,
                    )
                    return 4
                print(f"[data latest] Download failed (HTTP {status}): {message}", file=sys.stderr)
                _print_next_steps(
                    "[data latest]",
                    _build_api_unreachable_hints(api_base=args.api_base),
                    stream=sys.stderr,
                )
                return 1

            file_type = str(args.file_type or "data").lstrip(".")
            filename = _filename_from_content_disposition(headers.get("content-disposition", "")) or f"latest.{file_type}"
            target = _resolve_download_output_path(args.output, filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)

            result_payload = {
                "success": True,
                "download": {
                    "path": str(target),
                    "filename": target.name,
                    "bytes": len(body),
                    "source": url,
                },
            }
            if args.json:
                print(json.dumps(result_payload, ensure_ascii=False, indent=2))
            else:
                print(f"[data latest] downloaded: {target} ({len(body)} bytes)")
            return 0

        preview_query = {
            **query,
            "preview": True,
            "limit": args.limit,
        }
        url = _build_api_url(args.api_base, "/api/data/latest", preview_query)
        status, body, _headers = _api_fetch(url)
        payload = _parse_json_bytes(body)
        if status != 200:
            message = _extract_api_error_message(payload, f"HTTP {status}")
            if status == 404:
                print(f"[data latest] No latest file found: {message}", file=sys.stderr)
                _print_next_steps(
                    "[data latest]",
                    _build_no_data_file_hints(platform=args.platform),
                    stream=sys.stderr,
                )
                return 4
            print(f"[data latest] Preview failed (HTTP {status}): {message}", file=sys.stderr)
            _print_next_steps(
                "[data latest]",
                _build_api_unreachable_hints(api_base=args.api_base),
                stream=sys.stderr,
            )
            return 1

        if payload is None:
            print("[data latest] Invalid JSON response from API", file=sys.stderr)
            _print_next_steps(
                "[data latest]",
                _build_api_unreachable_hints(api_base=args.api_base),
                stream=sys.stderr,
            )
            return 1

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_latest_preview_summary(payload)
        return 0
    except ConnectionError as exc:
        print(f"[data latest] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps("[data latest]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
        return 2


def _scheduler_call(
    *,
    api_base: str,
    endpoint: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = DEFAULT_API_TIMEOUT,
) -> tuple[int, dict[str, Any] | None]:
    url = _build_api_url(api_base, endpoint)
    status, body, _headers = _api_request(url=url, method=method, payload=payload, timeout=timeout)
    return status, _parse_json_bytes(body)


def _scheduler_get_with_query(
    *,
    api_base: str,
    endpoint: str,
    query: dict[str, Any] | None = None,
    timeout: float = DEFAULT_API_TIMEOUT,
) -> tuple[int, dict[str, Any] | None]:
    url = _build_api_url(api_base, endpoint, query)
    status, body, _headers = _api_fetch(url, timeout=timeout)
    return status, _parse_json_bytes(body)


def _scheduler_fetch_files_snapshot(
    *,
    api_base: str,
    platform: str,
    timeout: float,
    page_size: int = 300,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    status, payload = _scheduler_get_with_query(
        api_base=api_base,
        endpoint="/api/data/files",
        query={
            "platform": platform,
            "page": 1,
            "page_size": page_size,
            "sort_by": "modified_at",
            "sort_order": "desc",
        },
        timeout=timeout,
    )
    if status != 200 or payload is None:
        message = _extract_api_error_message(payload, f"HTTP {status}")
        raise RuntimeError(f"fetch data files failed: {message}")

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    files = data.get("files", []) if isinstance(data, dict) else []
    if not isinstance(files, list):
        files = []

    snapshot: dict[str, float] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        try:
            modified_at = float(item.get("modified_at", 0))
        except Exception:
            modified_at = 0.0
        snapshot[path] = modified_at

    return files, snapshot


def _scheduler_poll_run_until_terminal(
    *,
    api_base: str,
    run_id: int,
    timeout: float,
    poll_interval: float,
    request_timeout: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    started = time.monotonic()
    terminal_statuses = {"completed", "failed", "cancelled"}
    history: list[dict[str, Any]] = []
    last_run: dict[str, Any] = {}

    while True:
        status, payload = _scheduler_call(
            api_base=api_base,
            endpoint=f"/api/scheduler/runs/{run_id}",
            timeout=request_timeout,
        )
        if status != 200 or payload is None:
            message = _extract_api_error_message(payload, f"HTTP {status}")
            raise RuntimeError(f"poll run failed(run_id={run_id}): {message}")

        run_data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if not isinstance(run_data, dict):
            run_data = {}
        last_run = run_data

        run_status = str(run_data.get("status", "unknown")).strip().lower()
        history.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "status": run_status,
                "message": run_data.get("message"),
                "task_id": run_data.get("task_id"),
            }
        )
        if run_status in terminal_statuses:
            return run_data, history, False

        if (time.monotonic() - started) >= timeout:
            return run_data, history, True

        time.sleep(max(0.2, float(poll_interval)))


def _scheduler_fetch_run_logs(
    *,
    api_base: str,
    run_id: int,
    task_id: str | None,
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    status, payload = _scheduler_get_with_query(
        api_base=api_base,
        endpoint="/api/crawler/logs",
        query={"limit": max(1, int(limit)), "run_id": run_id},
        timeout=timeout,
    )
    if status != 200 or payload is None:
        message = _extract_api_error_message(payload, f"HTTP {status}")
        raise RuntimeError(f"fetch run logs failed(run_id={run_id}): {message}")

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    logs = data.get("logs", []) if isinstance(data, dict) else []
    if not isinstance(logs, list):
        logs = []

    if logs or not task_id:
        return [item for item in logs if isinstance(item, dict)]

    # fallback: some environments may have delayed run_id enrichment
    status, payload = _scheduler_get_with_query(
        api_base=api_base,
        endpoint="/api/crawler/logs",
        query={"limit": max(1, int(limit)), "task_id": task_id},
        timeout=timeout,
    )
    if status != 200 or payload is None:
        return []

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    logs = data.get("logs", []) if isinstance(data, dict) else []
    if not isinstance(logs, list):
        logs = []
    return [item for item in logs if isinstance(item, dict)]


def _scheduler_fetch_latest_preview(
    *,
    api_base: str,
    platform: str,
    preview_limit: int,
    timeout: float,
) -> dict[str, Any]:
    status, payload = _scheduler_get_with_query(
        api_base=api_base,
        endpoint="/api/data/latest",
        query={"platform": platform, "limit": max(1, int(preview_limit))},
        timeout=timeout,
    )
    if status != 200 or payload is None:
        message = _extract_api_error_message(payload, f"HTTP {status}")
        raise RuntimeError(f"fetch latest preview failed: {message}")

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    return data


def _scheduler_print_or_json(payload: dict[str, Any], *, json_output: bool, text_lines: Sequence[str]) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for line in text_lines:
        print(line)


def _scheduler_list_cmd(args: argparse.Namespace) -> int:
    try:
        status, payload = _scheduler_call(
            api_base=args.api_base,
            endpoint="/api/scheduler/jobs",
            timeout=args.timeout,
        )
        if status != 200 or payload is None:
            message = _extract_api_error_message(payload, f"HTTP {status}")
            print(f"[scheduler list] Failed: {message}", file=sys.stderr)
            return 1
        jobs = payload.get("data", {}).get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            jobs = []
        lines = [f"[scheduler list] total_jobs={len(jobs)}"]
        for index, job in enumerate(jobs, start=1):
            lines.append(
                "[scheduler list] "
                f"{index}. id={job.get('job_id')} name={job.get('name')} "
                f"type={job.get('job_type')} platform={job.get('platform')} "
                f"interval_min={job.get('interval_minutes')} enabled={job.get('enabled')} "
                f"next_run_at={job.get('next_run_at')}"
            )
        _scheduler_print_or_json(payload, json_output=args.json, text_lines=lines)
        return 0
    except ConnectionError as exc:
        print(f"[scheduler list] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps("[scheduler list]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
        return 2


def _scheduler_status_cmd(args: argparse.Namespace) -> int:
    try:
        status, payload = _scheduler_call(
            api_base=args.api_base,
            endpoint="/api/scheduler/status",
            timeout=args.timeout,
        )
        if status != 200 or payload is None:
            message = _extract_api_error_message(payload, f"HTTP {status}")
            print(f"[scheduler status] Failed: {message}", file=sys.stderr)
            return 1
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        lines = [
            f"[scheduler status] enabled={data.get('enabled')} running={data.get('running')}",
            f"[scheduler status] poll_interval_sec={data.get('poll_interval_sec')}",
            f"[scheduler status] last_tick_at={data.get('last_tick_at')} last_error={data.get('last_error')}",
        ]
        _scheduler_print_or_json(payload, json_output=args.json, text_lines=lines)
        return 0
    except ConnectionError as exc:
        print(f"[scheduler status] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps("[scheduler status]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
        return 2


def _scheduler_runs_cmd(args: argparse.Namespace) -> int:
    if args.limit < 1:
        print("[scheduler runs] --limit must be >= 1", file=sys.stderr)
        return 2
    try:
        url = _build_api_url(
            args.api_base,
            "/api/scheduler/runs",
            {
                "job_id": args.job_id,
                "limit": args.limit,
            },
        )
        status, body, _headers = _api_fetch(url, timeout=args.timeout)
        payload = _parse_json_bytes(body)
        if status != 200 or payload is None:
            message = _extract_api_error_message(payload, f"HTTP {status}")
            print(f"[scheduler runs] Failed: {message}", file=sys.stderr)
            return 1

        runs = payload.get("data", {}).get("runs", []) if isinstance(payload, dict) else []
        if not isinstance(runs, list):
            runs = []
        lines = [f"[scheduler runs] total_runs={len(runs)}"]
        for index, run in enumerate(runs, start=1):
            lines.append(
                "[scheduler runs] "
                f"{index}. run_id={run.get('run_id')} job_id={run.get('job_id')} "
                f"status={run.get('status')} task_id={run.get('task_id')} "
                f"triggered_at={run.get('triggered_at')} message={run.get('message')}"
            )
        _scheduler_print_or_json(payload, json_output=args.json, text_lines=lines)
        return 0
    except ConnectionError as exc:
        print(f"[scheduler runs] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps("[scheduler runs]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
        return 2


def _scheduler_create_keyword_cmd(args: argparse.Namespace) -> int:
    payload = {
        "name": args.name,
        "job_type": "keyword",
        "platform": args.platform,
        "interval_minutes": args.interval_minutes,
        "enabled": args.enabled,
        "payload": {
            "keywords": args.keywords,
            "save_option": args.save_option,
            "headless": args.headless,
            "safety_profile": args.safety_profile,
        },
    }
    if args.max_notes_count is not None:
        payload["payload"]["max_notes_count"] = args.max_notes_count
    if args.crawl_sleep_sec is not None:
        payload["payload"]["crawl_sleep_sec"] = args.crawl_sleep_sec

    try:
        status, response_payload = _scheduler_call(
            api_base=args.api_base,
            endpoint="/api/scheduler/jobs",
            method="POST",
            payload=payload,
            timeout=args.timeout,
        )
        if status != 200 or response_payload is None:
            message = _extract_api_error_message(response_payload, f"HTTP {status}")
            print(f"[scheduler create-keyword] Failed: {message}", file=sys.stderr)
            return 1
        lines = [f"[scheduler create-keyword] created job_id={response_payload.get('data', {}).get('job_id')}"]
        _scheduler_print_or_json(response_payload, json_output=args.json, text_lines=lines)
        return 0
    except ConnectionError as exc:
        print(f"[scheduler create-keyword] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps(
            "[scheduler create-keyword]",
            _build_api_unreachable_hints(api_base=args.api_base),
            stream=sys.stderr,
        )
        return 2


def _scheduler_create_kol_cmd(args: argparse.Namespace) -> int:
    payload = {
        "name": args.name,
        "job_type": "kol",
        "platform": args.platform,
        "interval_minutes": args.interval_minutes,
        "enabled": args.enabled,
        "payload": {
            "creator_ids": args.creator_ids,
            "save_option": args.save_option,
            "headless": args.headless,
            "safety_profile": args.safety_profile,
        },
    }
    if args.max_notes_count is not None:
        payload["payload"]["max_notes_count"] = args.max_notes_count
    if args.crawl_sleep_sec is not None:
        payload["payload"]["crawl_sleep_sec"] = args.crawl_sleep_sec

    try:
        status, response_payload = _scheduler_call(
            api_base=args.api_base,
            endpoint="/api/scheduler/jobs",
            method="POST",
            payload=payload,
            timeout=args.timeout,
        )
        if status != 200 or response_payload is None:
            message = _extract_api_error_message(response_payload, f"HTTP {status}")
            print(f"[scheduler create-kol] Failed: {message}", file=sys.stderr)
            return 1
        lines = [f"[scheduler create-kol] created job_id={response_payload.get('data', {}).get('job_id')}"]
        _scheduler_print_or_json(response_payload, json_output=args.json, text_lines=lines)
        return 0
    except ConnectionError as exc:
        print(f"[scheduler create-kol] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps(
            "[scheduler create-kol]",
            _build_api_unreachable_hints(api_base=args.api_base),
            stream=sys.stderr,
        )
        return 2


def _scheduler_enable_disable_cmd(args: argparse.Namespace) -> int:
    payload = {"enabled": bool(args.enabled)}
    try:
        status, response_payload = _scheduler_call(
            api_base=args.api_base,
            endpoint=f"/api/scheduler/jobs/{args.job_id}",
            method="PATCH",
            payload=payload,
            timeout=args.timeout,
        )
        if status != 200 or response_payload is None:
            message = _extract_api_error_message(response_payload, f"HTTP {status}")
            print(f"[scheduler set-enabled] Failed: {message}", file=sys.stderr)
            return 1
        lines = [
            f"[scheduler set-enabled] job_id={args.job_id} enabled={payload['enabled']}",
        ]
        _scheduler_print_or_json(response_payload, json_output=args.json, text_lines=lines)
        return 0
    except ConnectionError as exc:
        print(f"[scheduler set-enabled] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps(
            "[scheduler set-enabled]",
            _build_api_unreachable_hints(api_base=args.api_base),
            stream=sys.stderr,
        )
        return 2


def _scheduler_delete_cmd(args: argparse.Namespace) -> int:
    try:
        status, response_payload = _scheduler_call(
            api_base=args.api_base,
            endpoint=f"/api/scheduler/jobs/{args.job_id}",
            method="DELETE",
            timeout=args.timeout,
        )
        if status != 200 or response_payload is None:
            message = _extract_api_error_message(response_payload, f"HTTP {status}")
            print(f"[scheduler delete] Failed: {message}", file=sys.stderr)
            return 1
        lines = [f"[scheduler delete] deleted job_id={args.job_id}"]
        _scheduler_print_or_json(response_payload, json_output=args.json, text_lines=lines)
        return 0
    except ConnectionError as exc:
        print(f"[scheduler delete] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps("[scheduler delete]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
        return 2


def _scheduler_run_now_cmd(args: argparse.Namespace) -> int:
    try:
        status, response_payload = _scheduler_call(
            api_base=args.api_base,
            endpoint=f"/api/scheduler/jobs/{args.job_id}/run-now",
            method="POST",
            payload={},
            timeout=args.timeout,
        )
        if status != 200 or response_payload is None:
            message = _extract_api_error_message(response_payload, f"HTTP {status}")
            print(f"[scheduler run-now] Failed: {message}", file=sys.stderr)
            return 1
        data = response_payload.get("data", {}) if isinstance(response_payload, dict) else {}
        lines = [
            f"[scheduler run-now] accepted={data.get('accepted')} task_id={data.get('task_id')} "
            f"run_id={data.get('run_id')} message={data.get('message')}"
        ]
        _scheduler_print_or_json(response_payload, json_output=args.json, text_lines=lines)
        return 0
    except ConnectionError as exc:
        print(f"[scheduler run-now] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps("[scheduler run-now]", _build_api_unreachable_hints(api_base=args.api_base), stream=sys.stderr)
        return 2


def _scheduler_smoke_e2e_cmd(args: argparse.Namespace) -> int:
    created_job_ids: list[str] = []
    run_summaries: list[dict[str, Any]] = []
    cleanup_deleted: list[str] = []
    cleanup_errors: list[dict[str, Any]] = []
    smoke_started_at = datetime.now(timezone.utc).isoformat()

    try:
        status, runtime_payload = _scheduler_call(
            api_base=args.api_base,
            endpoint="/api/health/runtime",
            timeout=args.timeout,
        )
        if status != 200 or runtime_payload is None:
            message = _extract_api_error_message(runtime_payload, f"HTTP {status}")
            print(f"[scheduler smoke-e2e] Failed runtime check: {message}", file=sys.stderr)
            return 1
        runtime_data = runtime_payload.get("data", {}) if isinstance(runtime_payload, dict) else {}
        if not isinstance(runtime_data, dict):
            runtime_data = {}

        before_files, before_snapshot = _scheduler_fetch_files_snapshot(
            api_base=args.api_base,
            platform=args.platform,
            timeout=args.timeout,
        )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        create_requests: list[tuple[str, dict[str, Any]]] = [
            (
                "keyword",
                {
                    "name": f"scheduler-smoke-keyword-{timestamp}",
                    "job_type": "keyword",
                    "platform": args.platform,
                    "interval_minutes": args.interval_minutes,
                    "enabled": False,
                    "payload": {
                        "keywords": args.keywords,
                        "login_type": "cookie",
                        "save_option": args.save_option,
                        "headless": bool(args.headless),
                        "start_page": 1,
                        "enable_comments": True,
                        "enable_sub_comments": False,
                        "safety_profile": args.safety_profile,
                        "max_notes_count": args.max_notes_count,
                        "crawl_sleep_sec": args.crawl_sleep_sec,
                    },
                },
            ),
            (
                "kol",
                {
                    "name": f"scheduler-smoke-kol-{timestamp}",
                    "job_type": "kol",
                    "platform": args.platform,
                    "interval_minutes": args.interval_minutes,
                    "enabled": False,
                    "payload": {
                        "creator_ids": args.creator_ids,
                        "login_type": "cookie",
                        "save_option": args.save_option,
                        "headless": bool(args.headless),
                        "start_page": 1,
                        "enable_comments": True,
                        "enable_sub_comments": False,
                        "safety_profile": args.safety_profile,
                        "max_notes_count": args.max_notes_count,
                        "crawl_sleep_sec": args.crawl_sleep_sec,
                    },
                },
            ),
        ]

        created_jobs: list[dict[str, Any]] = []
        for label, create_payload in create_requests:
            status, payload = _scheduler_call(
                api_base=args.api_base,
                endpoint="/api/scheduler/jobs",
                method="POST",
                payload=create_payload,
                timeout=args.timeout,
            )
            if status != 200 or payload is None:
                message = _extract_api_error_message(payload, f"HTTP {status}")
                raise RuntimeError(f"create {label} job failed: {message}")
            job_data = payload.get("data", {}) if isinstance(payload, dict) else {}
            if not isinstance(job_data, dict):
                raise RuntimeError(f"create {label} job failed: invalid response payload")
            job_id = str(job_data.get("job_id", "")).strip()
            if not job_id:
                raise RuntimeError(f"create {label} job failed: empty job_id")
            created_job_ids.append(job_id)
            created_jobs.append({"label": label, "job": job_data})

        for item in created_jobs:
            label = str(item.get("label"))
            job = item.get("job", {})
            if not isinstance(job, dict):
                continue
            job_id = str(job.get("job_id", "")).strip()
            if not job_id:
                continue

            status, trigger_payload = _scheduler_call(
                api_base=args.api_base,
                endpoint=f"/api/scheduler/jobs/{job_id}/run-now",
                method="POST",
                payload={},
                timeout=args.timeout,
            )
            if status != 200 or trigger_payload is None:
                message = _extract_api_error_message(trigger_payload, f"HTTP {status}")
                raise RuntimeError(f"run-now failed(job_id={job_id}): {message}")

            trigger_data = trigger_payload.get("data", {}) if isinstance(trigger_payload, dict) else {}
            if not isinstance(trigger_data, dict):
                trigger_data = {}
            run_id = int(trigger_data.get("run_id", 0) or 0)
            if run_id <= 0:
                raise RuntimeError(f"run-now failed(job_id={job_id}): invalid run_id")

            run_data, run_history, timed_out = _scheduler_poll_run_until_terminal(
                api_base=args.api_base,
                run_id=run_id,
                timeout=args.run_timeout,
                poll_interval=args.poll_interval,
                request_timeout=args.timeout,
            )
            logs = _scheduler_fetch_run_logs(
                api_base=args.api_base,
                run_id=run_id,
                task_id=str(run_data.get("task_id", "")).strip() or None,
                limit=args.logs_limit,
                timeout=args.timeout,
            )

            run_summaries.append(
                {
                    "label": label,
                    "job_id": job_id,
                    "trigger": trigger_data,
                    "final": run_data,
                    "timed_out": timed_out,
                    "history_count": len(run_history),
                    "history_tail": run_history[-6:],
                    "logs_count": len(logs),
                    "logs_tail": logs[-8:],
                }
            )

        # Allow filesystem flush before re-checking latest files.
        time.sleep(max(0.0, float(args.settle_sec)))
        after_files, after_snapshot = _scheduler_fetch_files_snapshot(
            api_base=args.api_base,
            platform=args.platform,
            timeout=args.timeout,
        )
        latest_preview = _scheduler_fetch_latest_preview(
            api_base=args.api_base,
            platform=args.platform,
            preview_limit=args.preview_limit,
            timeout=args.timeout,
        )

        changed_files: list[dict[str, Any]] = []
        for path, modified_at in after_snapshot.items():
            previous = before_snapshot.get(path)
            if previous is None or modified_at > previous:
                changed_files.append(
                    {
                        "path": path,
                        "modified_at": modified_at,
                        "new": previous is None,
                    }
                )
        changed_files.sort(key=lambda item: float(item.get("modified_at", 0.0)), reverse=True)

        summary_payload = {
            "started_at_utc": smoke_started_at,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "runtime_health": runtime_data,
            "jobs": [item.get("job", {}) for item in created_jobs],
            "runs": run_summaries,
            "data_changes": {
                "before_top3": before_files[:3],
                "after_top5": after_files[:5],
                "new_or_updated_files": changed_files[:20],
            },
            "latest_preview": {
                "file": latest_preview.get("file"),
                "total": latest_preview.get("total"),
                "sample_size": len(latest_preview.get("data", []) if isinstance(latest_preview.get("data"), list) else []),
            },
            "cleanup": {
                "deleted_jobs": cleanup_deleted,
                "errors": cleanup_errors,
                "kept_jobs": bool(args.keep_jobs),
            },
        }

        if args.json:
            print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
        else:
            print(
                "[scheduler smoke-e2e] runtime "
                f"overall={runtime_data.get('overall_status')} healthy={runtime_data.get('overall_healthy')}"
            )
            print(
                "[scheduler smoke-e2e] created_jobs="
                + ", ".join(str(item.get("job", {}).get("job_id", "")) for item in created_jobs)
            )
            for run in run_summaries:
                final = run.get("final", {}) if isinstance(run, dict) else {}
                print(
                    "[scheduler smoke-e2e] "
                    f"{run.get('label')} run_id={final.get('run_id')} status={final.get('status')} "
                    f"task_id={final.get('task_id')} logs={run.get('logs_count')} timeout={run.get('timed_out')}"
                )
            print(
                "[scheduler smoke-e2e] data changed files="
                f"{len(changed_files)} latest={latest_preview.get('file', {}).get('path') if isinstance(latest_preview.get('file'), dict) else None}"
            )

        run_all_completed = all(
            str((run.get("final", {}) if isinstance(run, dict) else {}).get("status", "")).lower() == "completed"
            and not bool(run.get("timed_out"))
            for run in run_summaries
        )

        if not run_all_completed:
            print("[scheduler smoke-e2e] One or more runs did not complete successfully", file=sys.stderr)
            return 1

        if args.require_data_change and not changed_files:
            print("[scheduler smoke-e2e] No data file changes detected after runs", file=sys.stderr)
            return 1

        return 0
    except ConnectionError as exc:
        print(f"[scheduler smoke-e2e] API unreachable: {exc}", file=sys.stderr)
        _print_next_steps(
            "[scheduler smoke-e2e]",
            _build_api_unreachable_hints(api_base=args.api_base),
            stream=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(f"[scheduler smoke-e2e] Failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if not args.keep_jobs:
            for job_id in created_job_ids:
                try:
                    status, payload = _scheduler_call(
                        api_base=args.api_base,
                        endpoint=f"/api/scheduler/jobs/{job_id}",
                        method="DELETE",
                        timeout=args.timeout,
                    )
                    if status == 200 and payload is not None and bool(payload.get("success", True)):
                        cleanup_deleted.append(job_id)
                    else:
                        cleanup_errors.append(
                            {
                                "job_id": job_id,
                                "status": status,
                                "message": _extract_api_error_message(payload, f"HTTP {status}"),
                            }
                        )
                except Exception as cleanup_exc:  # pragma: no cover - defensive cleanup
                    cleanup_errors.append({"job_id": job_id, "error": str(cleanup_exc)})


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


def _collect_runtime_config(*, show_secrets: bool, simple: bool = False) -> dict[str, Any]:
    base_config = _load_base_config_module()
    payload: dict[str, Any] = {}
    keys = CORE_RUNTIME_CONFIG_KEYS if simple else RUNTIME_CONFIG_KEYS
    for key in keys:
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
        "runtime_config": _collect_runtime_config(show_secrets=args.show_secrets, simple=args.simple),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"project_root={payload['project_root']}")
        for key in sorted(payload["runtime_config"]):
            print(f"{key}={payload['runtime_config'][key]}")
    return 0


def _env_keys_for_mode(mode: str) -> list[str]:
    normalized = (mode or "core").strip().lower()
    if normalized == "core":
        return list(CORE_ENV_KEYS)
    if normalized == "advanced":
        return list(ADVANCED_ENV_KEYS)
    if normalized == "all":
        merged = list(CORE_ENV_KEYS)
        for key in ADVANCED_ENV_KEYS:
            if key not in merged:
                merged.append(key)
        return merged
    raise ValueError(f"Unsupported mode: {mode}")


def _config_env_cmd(args: argparse.Namespace) -> int:
    mode = str(args.mode).strip().lower()
    try:
        keys = _env_keys_for_mode(mode)
    except ValueError as exc:
        print(f"[config env] {exc}", file=sys.stderr)
        return 2

    variables: dict[str, dict[str, Any]] = {}
    for key in keys:
        raw = os.getenv(key, "")
        configured = bool(str(raw).strip())
        display_value = str(raw)
        if not args.show_secrets and key in SENSITIVE_ENV_KEYS:
            display_value = _mask_secret(display_value)
        variables[key] = {
            "configured": configured,
            "value": display_value,
        }

    payload = {
        "mode": mode,
        "variables": variables,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"[config env] mode={mode}")
    for key in keys:
        value = variables[key]["value"]
        configured = variables[key]["configured"]
        suffix = "" if configured else "  # <empty>"
        print(f"{key}={value}{suffix}")

    if mode == "core":
        print("[config env] Tip: use --mode advanced to view additional tuning variables.")
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
            "  uv run energycrawler setup\n"
            "  uv run energycrawler status\n"
            "  uv run energycrawler run --platform xhs --keywords 新能源\n"
            "  uv run energycrawler data list --platform xhs --limit 20\n"
            "  uv run energycrawler data latest --download\n"
            "  uv run energycrawler config show --simple\n"
            "  uv run energycrawler config env --mode core\n"
            "  uv run energycrawler data latest --platform xhs\n"
            "  uv run energycrawler data latest --download --platform x --output ./latest.json\n"
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

    run_parser = subparsers.add_parser("run", help="Simple crawl mode (recommended)")
    run_parser.add_argument("--platform", choices=["xhs", "x"], default="xhs")
    run_parser.add_argument(
        "--type",
        dest="crawler_type",
        choices=["search", "detail", "creator"],
        default="search",
    )
    run_parser.add_argument("--keywords", default="")
    run_parser.add_argument("--specified-id", default="")
    run_parser.add_argument("--creator-id", default="")
    run_parser.add_argument(
        "--safety-profile",
        choices=sorted(SIMPLE_SAFETY_DEFAULTS.keys()),
        default="balanced",
    )
    run_parser.add_argument(
        "--save-option",
        choices=["json", "csv", "excel", "sqlite", "db", "mongodb", "postgres"],
        default="json",
    )
    run_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Advanced args forwarded to main.py (put them after --)",
    )
    run_parser.set_defaults(handler=_run_simple_cmd)

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

    status_parser = subparsers.add_parser("status", help="Show runtime status snapshot via API")
    status_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    status_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(handler=_status_cmd)

    data_parser = subparsers.add_parser("data", help="Data API helper commands")
    data_subparsers = data_parser.add_subparsers(dest="data_command", required=True)
    data_list_parser = data_subparsers.add_parser(
        "list",
        help="List exported data files via API",
    )
    data_list_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    data_list_parser.add_argument("--platform", help="Optional platform filter, e.g. xhs/x/twitter")
    data_list_parser.add_argument("--file-type", help="Optional file type filter, e.g. json/csv/xlsx")
    data_list_parser.add_argument("--limit", type=int, default=20, help="Max files to display (default: 20)")
    data_list_parser.add_argument("--json", action="store_true", help="Print JSON output")
    data_list_parser.set_defaults(handler=_data_list_cmd)

    data_latest_parser = data_subparsers.add_parser(
        "latest",
        help="Preview or download latest exported file via API",
    )
    data_latest_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    data_latest_parser.add_argument("--platform", help="Optional platform filter, e.g. xhs/x/twitter")
    data_latest_parser.add_argument("--file-type", help="Optional file type filter, e.g. json/csv/xlsx")
    data_latest_parser.add_argument("--limit", type=int, default=100, help="Preview limit (default: 100)")
    data_latest_parser.add_argument("--download", action="store_true", help="Download latest file instead of preview")
    data_latest_parser.add_argument(
        "--output",
        help="Output path for downloaded file (file path or existing directory)",
    )
    data_latest_parser.add_argument("--json", action="store_true", help="Print JSON output")
    data_latest_parser.set_defaults(handler=_data_latest_cmd)

    scheduler_parser = subparsers.add_parser("scheduler", help="Scheduler management commands")
    scheduler_subparsers = scheduler_parser.add_subparsers(dest="scheduler_command", required=True)

    scheduler_list_parser = scheduler_subparsers.add_parser("list", help="List scheduler jobs")
    scheduler_list_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_list_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_list_parser.add_argument("--json", action="store_true")
    scheduler_list_parser.set_defaults(handler=_scheduler_list_cmd)

    scheduler_status_parser = scheduler_subparsers.add_parser("status", help="Show scheduler runtime status")
    scheduler_status_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_status_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_status_parser.add_argument("--json", action="store_true")
    scheduler_status_parser.set_defaults(handler=_scheduler_status_cmd)

    scheduler_runs_parser = scheduler_subparsers.add_parser("runs", help="List scheduler run history")
    scheduler_runs_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_runs_parser.add_argument("--job-id", help="Filter by scheduler job id")
    scheduler_runs_parser.add_argument("--limit", type=int, default=50)
    scheduler_runs_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_runs_parser.add_argument("--json", action="store_true")
    scheduler_runs_parser.set_defaults(handler=_scheduler_runs_cmd)

    scheduler_keyword_parser = scheduler_subparsers.add_parser(
        "create-keyword",
        help="Create keyword scheduler job",
    )
    scheduler_keyword_parser.add_argument("--name", required=True)
    scheduler_keyword_parser.add_argument("--platform", choices=["xhs", "x"], default="xhs")
    scheduler_keyword_parser.add_argument("--interval-minutes", type=int, required=True)
    scheduler_keyword_parser.add_argument("--keywords", required=True)
    scheduler_keyword_parser.add_argument(
        "--safety-profile",
        choices=sorted(SIMPLE_SAFETY_DEFAULTS.keys()),
        default="balanced",
    )
    scheduler_keyword_parser.add_argument(
        "--save-option",
        choices=["json", "csv", "excel", "sqlite", "db", "mongodb", "postgres"],
        default="json",
    )
    scheduler_keyword_parser.add_argument("--max-notes-count", type=int)
    scheduler_keyword_parser.add_argument("--crawl-sleep-sec", type=float)
    scheduler_keyword_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    scheduler_keyword_parser.add_argument(
        "--enabled",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    scheduler_keyword_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_keyword_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_keyword_parser.add_argument("--json", action="store_true")
    scheduler_keyword_parser.set_defaults(handler=_scheduler_create_keyword_cmd)

    scheduler_kol_parser = scheduler_subparsers.add_parser("create-kol", help="Create KOL scheduler job")
    scheduler_kol_parser.add_argument("--name", required=True)
    scheduler_kol_parser.add_argument("--platform", choices=["xhs", "x"], default="xhs")
    scheduler_kol_parser.add_argument("--interval-minutes", type=int, required=True)
    scheduler_kol_parser.add_argument("--creator-ids", required=True)
    scheduler_kol_parser.add_argument(
        "--safety-profile",
        choices=sorted(SIMPLE_SAFETY_DEFAULTS.keys()),
        default="balanced",
    )
    scheduler_kol_parser.add_argument(
        "--save-option",
        choices=["json", "csv", "excel", "sqlite", "db", "mongodb", "postgres"],
        default="json",
    )
    scheduler_kol_parser.add_argument("--max-notes-count", type=int)
    scheduler_kol_parser.add_argument("--crawl-sleep-sec", type=float)
    scheduler_kol_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    scheduler_kol_parser.add_argument(
        "--enabled",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    scheduler_kol_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_kol_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_kol_parser.add_argument("--json", action="store_true")
    scheduler_kol_parser.set_defaults(handler=_scheduler_create_kol_cmd)

    scheduler_enable_parser = scheduler_subparsers.add_parser("enable", help="Enable scheduler job")
    scheduler_enable_parser.add_argument("job_id")
    scheduler_enable_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_enable_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_enable_parser.add_argument("--json", action="store_true")
    scheduler_enable_parser.set_defaults(handler=_scheduler_enable_disable_cmd, enabled=True)

    scheduler_disable_parser = scheduler_subparsers.add_parser("disable", help="Disable scheduler job")
    scheduler_disable_parser.add_argument("job_id")
    scheduler_disable_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_disable_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_disable_parser.add_argument("--json", action="store_true")
    scheduler_disable_parser.set_defaults(handler=_scheduler_enable_disable_cmd, enabled=False)

    scheduler_delete_parser = scheduler_subparsers.add_parser("delete", help="Delete scheduler job")
    scheduler_delete_parser.add_argument("job_id")
    scheduler_delete_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_delete_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_delete_parser.add_argument("--json", action="store_true")
    scheduler_delete_parser.set_defaults(handler=_scheduler_delete_cmd)

    scheduler_run_now_parser = scheduler_subparsers.add_parser("run-now", help="Trigger scheduler job immediately")
    scheduler_run_now_parser.add_argument("job_id")
    scheduler_run_now_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_run_now_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_run_now_parser.add_argument("--json", action="store_true")
    scheduler_run_now_parser.set_defaults(handler=_scheduler_run_now_cmd)

    scheduler_smoke_parser = scheduler_subparsers.add_parser(
        "smoke-e2e",
        help="Run keyword+KOL scheduler smoke test and verify data output",
    )
    scheduler_smoke_parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="API base URL (default: ENERGYCRAWLER_API_BASE or http://127.0.0.1:8080)",
    )
    scheduler_smoke_parser.add_argument("--platform", choices=["xhs", "x"], default="xhs")
    scheduler_smoke_parser.add_argument("--keywords", default="新能源,储能")
    scheduler_smoke_parser.add_argument(
        "--creator-ids",
        default="60d5b32a000000002002cf79,6522c385000000002a034681",
    )
    scheduler_smoke_parser.add_argument("--interval-minutes", type=int, default=60)
    scheduler_smoke_parser.add_argument(
        "--safety-profile",
        choices=sorted(SIMPLE_SAFETY_DEFAULTS.keys()),
        default="safe",
    )
    scheduler_smoke_parser.add_argument(
        "--save-option",
        choices=["json", "csv", "excel", "sqlite", "db", "mongodb", "postgres"],
        default="json",
    )
    scheduler_smoke_parser.add_argument("--max-notes-count", type=int, default=5)
    scheduler_smoke_parser.add_argument("--crawl-sleep-sec", type=float, default=1.2)
    scheduler_smoke_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    scheduler_smoke_parser.add_argument("--poll-interval", type=float, default=5.0)
    scheduler_smoke_parser.add_argument("--run-timeout", type=float, default=420.0)
    scheduler_smoke_parser.add_argument("--settle-sec", type=float, default=5.0)
    scheduler_smoke_parser.add_argument("--logs-limit", type=int, default=200)
    scheduler_smoke_parser.add_argument("--preview-limit", type=int, default=5)
    scheduler_smoke_parser.add_argument(
        "--require-data-change",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    scheduler_smoke_parser.add_argument("--keep-jobs", action="store_true")
    scheduler_smoke_parser.add_argument("--timeout", type=float, default=DEFAULT_API_TIMEOUT)
    scheduler_smoke_parser.add_argument("--json", action="store_true")
    scheduler_smoke_parser.set_defaults(handler=_scheduler_smoke_e2e_cmd)

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
    config_show_parser.add_argument(
        "--simple",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show only core runtime config (default: true)",
    )
    config_show_parser.add_argument("--json", action="store_true")
    config_show_parser.set_defaults(handler=_config_show_cmd)

    config_env_parser = config_subparsers.add_parser("env", help="Show environment variables by complexity")
    config_env_parser.add_argument("--mode", choices=["core", "advanced", "all"], default="core")
    config_env_parser.add_argument("--show-secrets", action="store_true")
    config_env_parser.add_argument("--json", action="store_true")
    config_env_parser.set_defaults(handler=_config_env_cmd)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    code = args.handler(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
