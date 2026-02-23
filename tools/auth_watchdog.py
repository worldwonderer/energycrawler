# -*- coding: utf-8 -*-
"""Auth watchdog utilities for retry + auto-recovery."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

import config
from tools import utils


@dataclass
class AuthWatchdogResult:
    platform: str
    enabled: bool
    success: bool
    attempts: int
    recovered: bool = False
    message: str = ""
    last_error: str = ""


async def run_auth_watchdog(
    platform: str,
    check_auth_fn: Callable[[], Awaitable[bool]],
    recover_auth_fn: Callable[[int], Awaitable[bool]] | None = None,
    check_label: str = "login state",
) -> AuthWatchdogResult:
    """
    Run auth checks with optional retry/recovery.

    Flow:
      1) check login state
      2) on failure, run recovery callback + sleep
      3) retry until AUTH_WATCHDOG_MAX_RETRIES exhausted
    """
    enabled = bool(getattr(config, "AUTH_WATCHDOG_ENABLED", True))
    max_retries = max(0, int(getattr(config, "AUTH_WATCHDOG_MAX_RETRIES", 1)))
    retry_interval = max(0.0, float(getattr(config, "AUTH_WATCHDOG_RETRY_INTERVAL_SEC", 2.0)))

    attempts = 0
    recovered = False
    last_error = ""
    total_rounds = 1 if not enabled else max_retries + 1

    for round_index in range(total_rounds):
        attempts += 1
        try:
            check_ok = bool(await check_auth_fn())
        except Exception as exc:  # pragma: no cover - defensive branch
            check_ok = False
            last_error = str(exc)
            utils.log_event(
                "auth.watchdog.check.exception",
                level="warning",
                platform=platform,
                attempt=attempts,
                error=str(exc),
            )

        if check_ok:
            message = (
                f"{check_label} verified on attempt {attempts}"
                if attempts > 1
                else f"{check_label} verified"
            )
            return AuthWatchdogResult(
                platform=platform,
                enabled=enabled,
                success=True,
                attempts=attempts,
                recovered=recovered,
                message=message,
                last_error=last_error,
            )

        if not enabled or round_index >= total_rounds - 1:
            break

        if recover_auth_fn is not None:
            try:
                recover_ok = bool(await recover_auth_fn(attempts))
                recovered = recovered or recover_ok
                utils.log_event(
                    "auth.watchdog.recover",
                    level="warning" if not recover_ok else "info",
                    platform=platform,
                    attempt=attempts,
                    recovered=recover_ok,
                )
            except Exception as exc:  # pragma: no cover - defensive branch
                last_error = str(exc)
                utils.log_event(
                    "auth.watchdog.recover.exception",
                    level="warning",
                    platform=platform,
                    attempt=attempts,
                    error=str(exc),
                )

        if retry_interval > 0:
            await asyncio.sleep(retry_interval)

    message = (
        f"{check_label} check failed after {attempts} attempt(s)"
        if enabled
        else f"{check_label} check failed"
    )
    return AuthWatchdogResult(
        platform=platform,
        enabled=enabled,
        success=False,
        attempts=attempts,
        recovered=recovered,
        message=message,
        last_error=last_error,
    )
