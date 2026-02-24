# -*- coding: utf-8 -*-
"""Preflight checks before starting crawler tasks."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Tuple

import config
from tools import utils


def parse_energy_service_address(address: str) -> Tuple[str, int]:
    host, _, port_str = address.partition(":")
    host = host.strip() or "localhost"
    try:
        port = int(port_str.strip()) if port_str else 50051
    except ValueError:
        port = 50051
    return host, port


def check_energy_service_reachable(timeout_sec: float = 2.0) -> Tuple[bool, str]:
    host, port = parse_energy_service_address(config.ENERGY_SERVICE_ADDRESS)
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True, f"Energy service reachable at {host}:{port}"
    except OSError as exc:
        return False, f"Energy service unreachable at {host}:{port}: {exc}"


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookie_dict: dict[str, str] = {}
    for item in cookie_header.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            cookie_dict[key] = value
    return cookie_dict


def has_twitter_auth_material(cookie_header: str = "") -> bool:
    explicit_cookie = (cookie_header or "").strip()
    if explicit_cookie:
        cookie_map = parse_cookie_header(explicit_cookie)
        return bool(cookie_map.get("auth_token", "").strip() and cookie_map.get("ct0", "").strip())

    merged_cookie = getattr(config, "TWITTER_COOKIE", "").strip()
    cookie_map = parse_cookie_header(merged_cookie)
    auth_token = getattr(config, "TWITTER_AUTH_TOKEN", "").strip() or cookie_map.get("auth_token", "").strip()
    ct0 = getattr(config, "TWITTER_CT0", "").strip() or cookie_map.get("ct0", "").strip()
    return bool(auth_token and ct0)


def run_xhs_signature_canary() -> Tuple[bool, str]:
    """Run optional XHS signature runtime canary."""
    try:
        from scripts.check_xhs_signature_runtime import DEFAULT_BASELINE, load_baseline, run_probe
    except Exception as exc:
        return False, f"xhs signature canary unavailable: {exc}"

    host, port = parse_energy_service_address(config.ENERGY_SERVICE_ADDRESS)
    timeout_sec = float(getattr(config, "XHS_SIGNATURE_CANARY_TIMEOUT_SEC", 8.0))
    baseline: dict | None = None

    configured_baseline = getattr(config, "XHS_SIGNATURE_CANARY_BASELINE_PATH", "").strip()
    baseline_path = Path(configured_baseline) if configured_baseline else Path(DEFAULT_BASELINE)
    if baseline_path.exists():
        try:
            baseline = load_baseline(baseline_path)
        except Exception as exc:
            return False, f"xhs signature canary baseline invalid: {exc}"

    try:
        payload = run_probe(
            host=host,
            port=port,
            timeout_sec=timeout_sec,
            browser_id=None,
            headless=bool(getattr(config, "ENERGY_HEADLESS", True)),
            baseline=baseline,
            keep_browser=False,
        )
    except Exception as exc:
        return False, f"xhs signature canary execution failed: {exc}"

    if payload.get("healthy"):
        return True, "xhs signature canary passed"

    checks = payload.get("evaluation", {}).get("checks", [])
    failed = [item for item in checks if not item.get("ok")]
    if failed:
        detail = failed[0].get("detail", "")
        return False, f"xhs signature canary failed: {failed[0].get('name')} ({detail})"
    return False, "xhs signature canary failed"


def preflight_for_platform(platform: str, cookie_header: str = "") -> Tuple[bool, str]:
    ok, message = check_energy_service_reachable()
    if not ok:
        return False, message

    if platform in {"x", "twitter"} and not has_twitter_auth_material(cookie_header):
        return False, "Missing Twitter auth material: require auth_token and ct0 (via TWITTER_COOKIE or env vars)"

    if platform in {"xhs", "xiaohongshu"} and bool(getattr(config, "XHS_SIGNATURE_CANARY_ENABLED", False)):
        canary_ok, canary_msg = run_xhs_signature_canary()
        if not canary_ok:
            return False, canary_msg

    return True, "preflight passed"


def build_preflight_failure_hint(platform: str, message: str) -> str:
    normalized = (platform or "").strip().lower()
    hint_lines = [message, "", "Actionable next steps:"]

    if "unreachable" in message.lower() and "energy service" in message.lower():
        hint_lines.extend(
            [
                "1) Start/recover service: uv run energycrawler energy ensure",
                "2) Verify health: uv run energycrawler energy check --json",
                "3) Re-check runtime snapshot: uv run energycrawler status --json",
            ]
        )
    elif normalized in {"x", "twitter"} and "missing twitter auth material" in message.lower():
        hint_lines.extend(
            [
                "1) Export from logged-in browser: uv run energycrawler auth export --platform x",
                "2) Or set env vars: TWITTER_AUTH_TOKEN / TWITTER_CT0 (or TWITTER_COOKIE)",
                "3) Validate login state: uv run energycrawler auth status --json",
                "4) Re-check runtime snapshot: uv run energycrawler status --json",
            ]
        )
    elif normalized in {"xhs", "xiaohongshu"} and "canary" in message.lower():
        hint_lines.extend(
            [
                "1) Probe signature runtime: uv run energycrawler energy check --json",
                "2) Run canary details: uv run python scripts/check_xhs_signature_runtime.py --json",
                "3) Re-login with open+sync+verify: uv run energycrawler auth xhs-open-login --api-base http://localhost:8080",
                "4) Re-check runtime snapshot: uv run energycrawler status --json",
            ]
        )
    else:
        hint_lines.extend(
            [
                "1) Re-run with doctor: uv run energycrawler doctor",
                "2) Check runtime snapshot: uv run energycrawler status --json",
            ]
        )

    return "\n".join(hint_lines)


def ensure_energy_service_or_raise(platform: str = "") -> None:
    check_platform = (platform or getattr(config, "PLATFORM", "")).strip().lower()
    cookie_header = ""
    if check_platform in {"x", "twitter"}:
        cookie_header = getattr(config, "TWITTER_COOKIE", "")
    elif check_platform in {"xhs", "xiaohongshu"}:
        cookie_header = getattr(config, "COOKIES", "")

    ok, message = preflight_for_platform(check_platform, cookie_header)
    if not ok:
        raise RuntimeError(build_preflight_failure_hint(check_platform, message))

    utils.log_event("preflight.energy.ok", message=message)
