# -*- coding: utf-8 -*-
"""Unified API response helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


def success_response(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """Build a unified success payload."""
    return {
        "success": True,
        "data": data,
        "message": message,
    }


def error_response(
    code: str,
    message: str,
    *,
    details: Any = None,
) -> dict[str, Any]:
    """Build a unified error payload."""
    payload: dict[str, Any] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


@dataclass(slots=True)
class ApiError(Exception):
    """Application-level API exception."""

    status_code: int
    code: str
    message: str
    details: Optional[Any] = None


def status_to_error_code(status_code: int) -> str:
    """Map HTTP status code to a stable error code."""
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT",
    }
    return mapping.get(status_code, f"HTTP_{status_code}")
