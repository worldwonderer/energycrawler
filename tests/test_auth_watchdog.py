# -*- coding: utf-8 -*-
"""Unit tests for auth watchdog retry + recovery flow."""

from __future__ import annotations

import pytest

from tools import auth_watchdog


@pytest.mark.asyncio
async def test_watchdog_disabled_runs_single_check_without_recover(monkeypatch):
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_ENABLED", False, raising=False)
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_MAX_RETRIES", 3, raising=False)
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_RETRY_INTERVAL_SEC", 0.0, raising=False)

    calls = {"check": 0, "recover": 0}

    async def _check() -> bool:
        calls["check"] += 1
        return False

    async def _recover(_attempt: int) -> bool:
        calls["recover"] += 1
        return True

    result = await auth_watchdog.run_auth_watchdog(
        platform="xhs",
        check_auth_fn=_check,
        recover_auth_fn=_recover,
        check_label="xhs login state",
    )

    assert result.enabled is False
    assert result.success is False
    assert result.attempts == 1
    assert calls["check"] == 1
    assert calls["recover"] == 0


@pytest.mark.asyncio
async def test_watchdog_recovers_and_passes_on_next_attempt(monkeypatch):
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_ENABLED", True, raising=False)
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_MAX_RETRIES", 2, raising=False)
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_RETRY_INTERVAL_SEC", 0.0, raising=False)

    calls = {"check": 0, "recover": 0}

    async def _check() -> bool:
        calls["check"] += 1
        return calls["check"] >= 2

    async def _recover(_attempt: int) -> bool:
        calls["recover"] += 1
        return True

    result = await auth_watchdog.run_auth_watchdog(
        platform="xhs",
        check_auth_fn=_check,
        recover_auth_fn=_recover,
        check_label="xhs login state",
    )

    assert result.enabled is True
    assert result.success is True
    assert result.recovered is True
    assert result.attempts == 2
    assert calls["recover"] == 1


@pytest.mark.asyncio
async def test_watchdog_returns_failure_after_retries_exhausted(monkeypatch):
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_ENABLED", True, raising=False)
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_MAX_RETRIES", 1, raising=False)
    monkeypatch.setattr(auth_watchdog.config, "AUTH_WATCHDOG_RETRY_INTERVAL_SEC", 0.0, raising=False)

    calls = {"check": 0, "recover": 0}

    async def _check() -> bool:
        calls["check"] += 1
        return False

    async def _recover(_attempt: int) -> bool:
        calls["recover"] += 1
        return False

    result = await auth_watchdog.run_auth_watchdog(
        platform="x",
        check_auth_fn=_check,
        recover_auth_fn=_recover,
        check_label="x auth state",
    )

    assert result.success is False
    assert result.attempts == 2
    assert calls["check"] == 2
    assert calls["recover"] == 1
