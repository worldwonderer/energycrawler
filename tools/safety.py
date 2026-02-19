# -*- coding: utf-8 -*-
"""Crawler safety controls for low-volume, low-risk execution."""

from __future__ import annotations

import asyncio
import random

import config
from tools import utils


def enforce_runtime_safety() -> None:
    """Clamp runtime config to conservative anti-risk bounds."""
    hard_max_notes = max(1, int(getattr(config, "CRAWLER_HARD_MAX_NOTES_COUNT", 20)))
    hard_max_concurrency = max(1, int(getattr(config, "CRAWLER_HARD_MAX_CONCURRENCY", 2)))
    min_sleep = max(0.0, float(getattr(config, "CRAWLER_MIN_SLEEP_SEC", 6.0)))

    before_notes = int(getattr(config, "CRAWLER_MAX_NOTES_COUNT", 1))
    before_concurrency = int(getattr(config, "MAX_CONCURRENCY_NUM", 1))
    before_sleep = float(getattr(config, "CRAWLER_MAX_SLEEP_SEC", 1.0))

    config.CRAWLER_MAX_NOTES_COUNT = max(1, min(before_notes, hard_max_notes))
    config.MAX_CONCURRENCY_NUM = max(1, min(before_concurrency, hard_max_concurrency))
    config.CRAWLER_MAX_SLEEP_SEC = max(before_sleep, min_sleep)

    if (
        before_notes != config.CRAWLER_MAX_NOTES_COUNT
        or before_concurrency != config.MAX_CONCURRENCY_NUM
        or before_sleep != config.CRAWLER_MAX_SLEEP_SEC
    ):
        utils.log_event(
            "safety.clamped",
            level="warning",
            requested_max_notes=before_notes,
            applied_max_notes=config.CRAWLER_MAX_NOTES_COUNT,
            requested_concurrency=before_concurrency,
            applied_concurrency=config.MAX_CONCURRENCY_NUM,
            requested_sleep=before_sleep,
            applied_sleep=config.CRAWLER_MAX_SLEEP_SEC,
        )


def _sleep_jitter() -> float:
    jitter = max(0.0, float(getattr(config, "CRAWLER_SLEEP_JITTER_SEC", 0.8)))
    return random.uniform(0, jitter)


async def safe_sleep(base_delay: float | None = None) -> None:
    """Sleep with minimum delay floor and random jitter for anti-fingerprinting."""
    min_sleep = max(0.0, float(getattr(config, "CRAWLER_MIN_SLEEP_SEC", 6.0)))
    configured = float(getattr(config, "CRAWLER_MAX_SLEEP_SEC", min_sleep))
    delay = max(base_delay if base_delay is not None else configured, min_sleep)
    await asyncio.sleep(delay + _sleep_jitter())


def calc_backoff_delay(attempt: int) -> float:
    """Exponential backoff delay with jitter, capped by config."""
    base = max(0.1, float(getattr(config, "CRAWLER_RETRY_BASE_DELAY_SEC", 2.0)))
    max_delay = max(base, float(getattr(config, "CRAWLER_RETRY_MAX_DELAY_SEC", 30.0)))
    delay = min(max_delay, base * (2 ** max(0, attempt - 1)))
    return delay + _sleep_jitter()
