# -*- coding: utf-8 -*-
"""Preflight checks before starting crawler tasks."""

from __future__ import annotations

import socket
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
    merged_cookie = (cookie_header or "").strip() or getattr(config, "TWITTER_COOKIE", "").strip()
    cookie_map = parse_cookie_header(merged_cookie)
    auth_token = getattr(config, "TWITTER_AUTH_TOKEN", "").strip() or cookie_map.get("auth_token", "").strip()
    ct0 = getattr(config, "TWITTER_CT0", "").strip() or cookie_map.get("ct0", "").strip()
    return bool(auth_token and ct0)


def preflight_for_platform(platform: str, cookie_header: str = "") -> Tuple[bool, str]:
    ok, message = check_energy_service_reachable()
    if not ok:
        return False, message

    if platform in {"x", "twitter"} and not has_twitter_auth_material(cookie_header):
        return False, "Missing Twitter auth material: require auth_token and ct0 (via TWITTER_COOKIE or env vars)"

    return True, "preflight passed"


def ensure_energy_service_or_raise() -> None:
    ok, message = check_energy_service_reachable()
    if not ok:
        raise RuntimeError(message)
    utils.log_event("preflight.energy.ok", message=message)
