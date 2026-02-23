# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/tools/crawl_checkpoint.py
# GitHub: https://github.com/EnergyCrawler
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

"""Incremental crawl checkpoint manager."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import config
from tools import utils


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class CrawlCheckpointManager:
    """JSON-backed checkpoint store for incremental crawling and resume."""

    def __init__(self, checkpoint_path: str = "") -> None:
        self._lock = threading.Lock()
        self._path = self._resolve_path(checkpoint_path)

    @staticmethod
    def _resolve_path(checkpoint_path: str) -> Path:
        custom_path = (checkpoint_path or getattr(config, "CRAWLER_CHECKPOINT_PATH", "")).strip()
        if custom_path:
            return Path(custom_path)

        save_data_path = (getattr(config, "SAVE_DATA_PATH", "") or "").strip()
        if save_data_path:
            return Path(save_data_path) / "checkpoints" / "crawl_state.json"

        return Path("data") / "checkpoints" / "crawl_state.json"

    @staticmethod
    def _empty_data() -> Dict[str, Any]:
        return {"version": 1, "updated_at": "", "scopes": {}}

    def _read_data_unlocked(self) -> Dict[str, Any]:
        if not self._path.exists():
            return self._empty_data()

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return self._empty_data()
            payload.setdefault("version", 1)
            payload.setdefault("updated_at", "")
            payload.setdefault("scopes", {})
            if not isinstance(payload["scopes"], dict):
                payload["scopes"] = {}
            return payload
        except Exception as exc:
            utils.logger.warning(
                f"[CrawlCheckpointManager] Failed to read checkpoint file {self._path}: {exc}"
            )
            return self._empty_data()

    def _write_data_unlocked(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = _utc_now_iso()
        temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self._path)

    def get_scope(self, scope_key: str) -> Dict[str, Any]:
        with self._lock:
            data = self._read_data_unlocked()
            scope = data.get("scopes", {}).get(scope_key, {})
            if not isinstance(scope, dict):
                return {}
            return dict(scope)

    def mark_scope_started(
        self,
        scope_key: str,
        *,
        platform: str,
        crawler_type: str,
        cursor: str = "",
        next_page: int = 1,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            data = self._read_data_unlocked()
            scopes = data.setdefault("scopes", {})
            scope = dict(scopes.get(scope_key, {}) or {})
            scope.update(
                {
                    "platform": platform,
                    "crawler_type": crawler_type,
                    "in_progress": True,
                    "cursor": cursor or "",
                    "next_page": int(next_page or 1),
                    "last_started_at": _utc_now_iso(),
                }
            )
            if meta:
                scope["meta"] = meta
            scopes[scope_key] = scope
            self._write_data_unlocked(data)
            return dict(scope)

    def mark_scope_progress(
        self,
        scope_key: str,
        *,
        cursor: Optional[str] = None,
        next_page: Optional[int] = None,
        latest_item_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            data = self._read_data_unlocked()
            scopes = data.setdefault("scopes", {})
            scope = dict(scopes.get(scope_key, {}) or {})
            scope["in_progress"] = True
            if cursor is not None:
                scope["cursor"] = cursor
            if next_page is not None:
                scope["next_page"] = int(next_page)
            if latest_item_id:
                scope["latest_item_id"] = str(latest_item_id)
            scope["last_progress_at"] = _utc_now_iso()
            scopes[scope_key] = scope
            self._write_data_unlocked(data)
            return dict(scope)

    def mark_scope_completed(self, scope_key: str, *, latest_item_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            data = self._read_data_unlocked()
            scopes = data.setdefault("scopes", {})
            scope = dict(scopes.get(scope_key, {}) or {})
            scope["in_progress"] = False
            scope["cursor"] = ""
            scope["next_page"] = 1
            scope["last_success_at"] = _utc_now_iso()
            if latest_item_id:
                scope["latest_item_id"] = str(latest_item_id)
            scopes[scope_key] = scope
            self._write_data_unlocked(data)
            return dict(scope)
