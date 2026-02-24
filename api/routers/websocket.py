# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/api/routers/websocket.py
# GitHub: https://github.com/EnergyCrawler
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import asyncio
import os
import re
import time
from typing import Any, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ..services import crawler_manager, scheduler_service

router = APIRouter(tags=["websocket"])
_TASK_ID_PATTERN = re.compile(r"\btask-[a-zA-Z0-9_-]+\b")
_TASK_TO_RUN_ID_CACHE: dict[str, int] = {}
_TASK_TO_RUN_ID_CACHE_SYNC_AT_MONOTONIC = 0.0
_TASK_TO_RUN_ID_CACHE_TTL_SEC = 5.0
_RUN_LOOKUP_LIMIT = 500
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "y", "on"}
_DEFAULT_MAX_WS_CONNECTIONS = 200

_WS_CONNECTIONS_LOCK = asyncio.Lock()
_WS_ACTIVE_CONNECTIONS = 0


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in _TRUTHY_ENV_VALUES


def _env_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw_value = (os.getenv(name, str(default)) or "").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _extract_admin_token(websocket: WebSocket) -> str:
    header_token = (websocket.headers.get("x-admin-token") or "").strip()
    if header_token:
        return header_token

    authorization = (websocket.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
        if bearer:
            return bearer

    query_token = (
        websocket.query_params.get("token")
        or websocket.query_params.get("admin_token")
        or ""
    ).strip()
    return query_token


def _is_websocket_authorized(websocket: WebSocket) -> bool:
    if not _env_flag("WEBSOCKET_REQUIRE_AUTH", default=False):
        return True

    expected_token = (os.getenv("WEBSOCKET_ADMIN_TOKEN", "") or "").strip()
    if not expected_token:
        return False

    return _extract_admin_token(websocket) == expected_token


def _max_ws_connections() -> int:
    return _env_int(
        "WEBSOCKET_MAX_CONNECTIONS",
        default=_DEFAULT_MAX_WS_CONNECTIONS,
        minimum=1,
        maximum=10_000,
    )


async def _try_acquire_ws_slot() -> bool:
    global _WS_ACTIVE_CONNECTIONS

    max_connections = _max_ws_connections()
    async with _WS_CONNECTIONS_LOCK:
        if _WS_ACTIVE_CONNECTIONS >= max_connections:
            return False
        _WS_ACTIVE_CONNECTIONS += 1
        return True


async def _release_ws_slot() -> None:
    global _WS_ACTIVE_CONNECTIONS

    async with _WS_CONNECTIONS_LOCK:
        _WS_ACTIVE_CONNECTIONS = max(0, _WS_ACTIVE_CONNECTIONS - 1)


async def _reject_connection(websocket: WebSocket, *, code: int, reason: str) -> None:
    await websocket.accept()
    await websocket.close(code=code, reason=reason)


def _extract_task_id(message: str) -> Optional[str]:
    match = _TASK_ID_PATTERN.search(message or "")
    return match.group(0) if match else None


async def _refresh_task_to_run_cache(*, force: bool = False) -> None:
    global _TASK_TO_RUN_ID_CACHE, _TASK_TO_RUN_ID_CACHE_SYNC_AT_MONOTONIC

    now = time.monotonic()
    if not force and (now - _TASK_TO_RUN_ID_CACHE_SYNC_AT_MONOTONIC) < _TASK_TO_RUN_ID_CACHE_TTL_SEC:
        return

    try:
        runs = await scheduler_service.list_runs(job_id=None, limit=_RUN_LOOKUP_LIMIT)
    except Exception:
        return

    mapping: dict[str, int] = {}
    for run in runs:
        task_id = str(run.get("task_id") or "").strip()
        run_id = run.get("run_id")
        if task_id and isinstance(run_id, int) and task_id not in mapping:
            mapping[task_id] = run_id

    _TASK_TO_RUN_ID_CACHE = mapping
    _TASK_TO_RUN_ID_CACHE_SYNC_AT_MONOTONIC = now


async def _resolve_run_id(task_id: str) -> Optional[int]:
    if not task_id:
        return None
    cached = _TASK_TO_RUN_ID_CACHE.get(task_id)
    if cached is not None:
        return cached

    await _refresh_task_to_run_cache(force=True)
    return _TASK_TO_RUN_ID_CACHE.get(task_id)


async def _enrich_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    task_id = _extract_task_id(str(enriched.get("message", "")))
    if not task_id:
        return enriched

    enriched["task_id"] = task_id
    run_id = await _resolve_run_id(task_id)
    if run_id is not None:
        enriched["run_id"] = run_id
    return enriched


class ConnectionManager:
    """WebSocket connection manager"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        if not self.active_connections:
            return

        disconnected = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected connections
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


async def log_broadcaster():
    """Background task: read logs from queue and broadcast"""
    queue = crawler_manager.get_log_queue()
    while True:
        try:
            # Get log entry from queue
            entry = await queue.get()
            # Broadcast to all WebSocket connections
            await manager.broadcast(await _enrich_log_payload(entry.model_dump()))
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Log broadcaster error: {e}")
            await asyncio.sleep(0.1)


# Global broadcast task
_broadcaster_task: Optional[asyncio.Task] = None


def start_broadcaster():
    """Start broadcast task"""
    global _broadcaster_task
    if _broadcaster_task is None or _broadcaster_task.done():
        _broadcaster_task = asyncio.create_task(log_broadcaster())


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket log stream"""
    print("[WS] New connection attempt")

    if not _is_websocket_authorized(websocket):
        await _reject_connection(
            websocket,
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Unauthorized",
        )
        return

    if not await _try_acquire_ws_slot():
        await _reject_connection(
            websocket,
            code=status.WS_1013_TRY_AGAIN_LATER,
            reason="Too many websocket connections",
        )
        return

    try:
        # Ensure broadcast task is running
        start_broadcaster()

        await manager.connect(websocket)
        print(f"[WS] Connected, active connections: {len(manager.active_connections)}")

        # Send existing logs
        await _refresh_task_to_run_cache()
        for log in crawler_manager.logs:
            try:
                await websocket.send_json(await _enrich_log_payload(log.model_dump()))
            except Exception as e:
                print(f"[WS] Error sending existing log: {e}")
                break

        print(f"[WS] Sent {len(crawler_manager.logs)} existing logs, entering main loop")

        while True:
            # Keep connection alive, receive heartbeat or any message
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_text("ping")
                except Exception as e:
                    print(f"[WS] Error sending ping: {e}")
                    break

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {type(e).__name__}: {e}")
    finally:
        manager.disconnect(websocket)
        await _release_ws_slot()
        print(f"[WS] Cleanup done, active connections: {len(manager.active_connections)}")


@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket status stream"""
    if not _is_websocket_authorized(websocket):
        await _reject_connection(
            websocket,
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Unauthorized",
        )
        return

    if not await _try_acquire_ws_slot():
        await _reject_connection(
            websocket,
            code=status.WS_1013_TRY_AGAIN_LATER,
            reason="Too many websocket connections",
        )
        return

    await websocket.accept()

    try:
        while True:
            # Send status every second
            status = crawler_manager.get_status()
            await websocket.send_json(status)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await _release_ws_slot()
