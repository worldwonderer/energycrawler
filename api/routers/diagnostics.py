# -*- coding: utf-8 -*-
"""Diagnostics APIs for one-click smoke E2E checks."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..response import success_response


router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_E2E_COMMAND = ("energycrawler", "scheduler", "smoke-e2e", "--json")
SMOKE_E2E_FALLBACK_COMMAND = ("uv", "run", *SMOKE_E2E_COMMAND)
SMOKE_OUTPUT_LIMIT = 12_000

_state_lock = asyncio.Lock()
_smoke_state: dict[str, Any] = {
    "running": False,
    "run_id": 0,
    "current_run": None,
    "latest": None,
}
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "y", "on"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_output(value: str) -> str:
    if len(value) <= SMOKE_OUTPUT_LIMIT:
        return value
    return value[:SMOKE_OUTPUT_LIMIT]


def _parse_json_payload(raw_stdout: str) -> tuple[Any, str | None]:
    payload_text = raw_stdout.strip()
    if not payload_text:
        return None, "command produced empty stdout; expected JSON payload"

    try:
        return json.loads(payload_text), None
    except json.JSONDecodeError as exc:
        return (
            None,
            f"failed to parse JSON output: {exc.msg} (line {exc.lineno}, column {exc.colno})",
        )


def _build_smoke_command_candidates(api_base: str | None) -> list[tuple[str, ...]]:
    if not api_base:
        return [SMOKE_E2E_COMMAND, SMOKE_E2E_FALLBACK_COMMAND]

    normalized = api_base.strip().rstrip("/")
    if not normalized:
        return [SMOKE_E2E_COMMAND, SMOKE_E2E_FALLBACK_COMMAND]

    with_base = (*SMOKE_E2E_COMMAND, "--api-base", normalized)
    with_base_fallback = ("uv", "run", *with_base)
    return [with_base, with_base_fallback]


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in _TRUTHY_ENV_VALUES


def _extract_admin_token(request: Request) -> str:
    header_token = (request.headers.get("x-admin-token") or "").strip()
    if header_token:
        return header_token

    authorization = (request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
        if bearer:
            return bearer

    query_token = (
        request.query_params.get("token")
        or request.query_params.get("admin_token")
        or ""
    ).strip()
    return query_token


def _ensure_diagnostics_authorized(request: Request) -> None:
    if not _env_flag("DIAGNOSTICS_REQUIRE_AUTH", default=False):
        return

    expected_token = (os.getenv("DIAGNOSTICS_ADMIN_TOKEN", "") or "").strip()
    received_token = _extract_admin_token(request)
    if expected_token and received_token == expected_token:
        return

    raise HTTPException(status_code=401, detail="Diagnostics admin token required")


async def _run_smoke_e2e(run_id: int, started_at: str, api_base: str | None = None) -> None:
    command_candidates = _build_smoke_command_candidates(api_base)
    command = list(command_candidates[0])
    stdout_text = ""
    stderr_text = ""
    exit_code: int | None = None
    payload: Any = None
    error: str | None = None

    try:
        process = None
        for candidate in command_candidates:
            try:
                process = await asyncio.create_subprocess_exec(
                    *candidate,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(PROJECT_ROOT),
                )
                command = list(candidate)
                break
            except FileNotFoundError:
                continue

        if process is None:
            raise FileNotFoundError("energycrawler/uv command not found in PATH")

        stdout, stderr = await process.communicate()

        stdout_text = stdout.decode("utf-8", errors="ignore")
        stderr_text = stderr.decode("utf-8", errors="ignore")
        exit_code = process.returncode

        payload, parse_error = _parse_json_payload(stdout_text)
        if parse_error:
            error = parse_error

        if exit_code != 0:
            runtime_error = stderr_text.strip() or f"command exited with code {exit_code}"
            error = f"{error}; {runtime_error}" if error else runtime_error
    except FileNotFoundError:
        error = "energycrawler command not found in PATH (and fallback 'uv run' unavailable)"
    except Exception as exc:  # pragma: no cover - defensive
        error = str(exc)
    finally:
        result = {
            "run_id": run_id,
            "command": " ".join(command),
            "started_at": started_at,
            "finished_at": _utc_now(),
            "ok": bool(exit_code == 0 and error is None and payload is not None),
            "exit_code": exit_code,
            "payload": payload,
            "error": error,
            "stdout": _truncate_output(stdout_text),
            "stderr": _truncate_output(stderr_text),
        }

        async with _state_lock:
            _smoke_state["running"] = False
            _smoke_state["current_run"] = None
            _smoke_state["latest"] = result


@router.post("/smoke-e2e/start")
async def start_smoke_e2e_check(request: Request):
    _ensure_diagnostics_authorized(request)
    async with _state_lock:
        if bool(_smoke_state.get("running")):
            return success_response(
                {
                    "accepted": False,
                    "running": True,
                    "current_run": deepcopy(_smoke_state.get("current_run")),
                    "latest": deepcopy(_smoke_state.get("latest")),
                },
                message="Smoke E2E diagnostics already running",
            )

        run_id = int(_smoke_state.get("run_id") or 0) + 1
        started_at = _utc_now()
        current_run = {
            "run_id": run_id,
            "command": " ".join(SMOKE_E2E_COMMAND),
            "started_at": started_at,
        }

        _smoke_state["run_id"] = run_id
        _smoke_state["running"] = True
        _smoke_state["current_run"] = current_run

    api_base = str(request.base_url).rstrip("/")
    asyncio.create_task(_run_smoke_e2e(run_id=run_id, started_at=started_at, api_base=api_base))

    async with _state_lock:
        latest = deepcopy(_smoke_state.get("latest"))

    return success_response(
        {
            "accepted": True,
            "running": True,
            "current_run": current_run,
            "latest": latest,
        },
        message="Smoke E2E diagnostics started",
    )


@router.get("/smoke-e2e/latest")
async def get_latest_smoke_e2e_report(request: Request):
    _ensure_diagnostics_authorized(request)
    async with _state_lock:
        snapshot = {
            "running": bool(_smoke_state.get("running")),
            "current_run": deepcopy(_smoke_state.get("current_run")),
            "latest": deepcopy(_smoke_state.get("latest")),
        }

    return success_response(snapshot, message="Smoke E2E diagnostics status")
