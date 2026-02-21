# -*- coding: utf-8 -*-
"""State management for XHS signature sessions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from threading import Lock
from typing import Dict, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class SignatureSessionState:
    """Per-browser runtime state for signature generation."""

    browser_id: str
    session_started_at_ms: int = field(default_factory=_now_ms)
    request_seq: int = 0
    last_x_t: int = 0
    b1_last_refresh_at: float = 0.0
    consecutive_failures: int = 0
    last_success_at: float = 0.0
    last_updated_at: float = field(default_factory=time.time)


class SignatureSessionStore:
    """Thread-safe in-memory session state store with TTL cleanup."""

    def __init__(self, ttl_sec: int = 1800):
        self._ttl_sec = max(60, int(ttl_sec))
        self._states: Dict[str, SignatureSessionState] = {}
        self._lock = Lock()

    def begin_request(self, browser_id: str) -> SignatureSessionState:
        with self._lock:
            self._cleanup_expired_locked()
            state = self._get_or_create_locked(browser_id)
            state.request_seq += 1
            state.last_updated_at = time.time()
            return replace(state)

    def next_monotonic_x_t(self, browser_id: str, candidate_ms: int) -> int:
        with self._lock:
            self._cleanup_expired_locked()
            state = self._get_or_create_locked(browser_id)
            next_value = candidate_ms if candidate_ms > state.last_x_t else state.last_x_t + 1
            state.last_x_t = next_value
            state.last_updated_at = time.time()
            return next_value

    def mark_b1_refreshed(self, browser_id: str) -> SignatureSessionState:
        with self._lock:
            self._cleanup_expired_locked()
            state = self._get_or_create_locked(browser_id)
            state.b1_last_refresh_at = time.time()
            state.last_updated_at = state.b1_last_refresh_at
            return replace(state)

    def record_success(self, browser_id: str) -> SignatureSessionState:
        with self._lock:
            self._cleanup_expired_locked()
            state = self._get_or_create_locked(browser_id)
            state.consecutive_failures = 0
            state.last_success_at = time.time()
            state.last_updated_at = state.last_success_at
            return replace(state)

    def record_failure(self, browser_id: str) -> SignatureSessionState:
        with self._lock:
            self._cleanup_expired_locked()
            state = self._get_or_create_locked(browser_id)
            state.consecutive_failures += 1
            state.last_updated_at = time.time()
            return replace(state)

    def snapshot(self, browser_id: str) -> Optional[SignatureSessionState]:
        with self._lock:
            self._cleanup_expired_locked()
            state = self._states.get(browser_id)
            return replace(state) if state else None

    def cleanup_expired(self) -> int:
        with self._lock:
            return self._cleanup_expired_locked()

    def _get_or_create_locked(self, browser_id: str) -> SignatureSessionState:
        state = self._states.get(browser_id)
        if state is None:
            state = SignatureSessionState(browser_id=browser_id)
            self._states[browser_id] = state
        return state

    def _cleanup_expired_locked(self) -> int:
        now = time.time()
        expired_keys = [
            key
            for key, value in self._states.items()
            if now - value.last_updated_at > self._ttl_sec
        ]
        for key in expired_keys:
            del self._states[key]
        return len(expired_keys)
