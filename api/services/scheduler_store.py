# -*- coding: utf-8 -*-
"""SQLite-backed persistence for scheduler jobs/runs."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


_RUN_STATUS_OPEN = {"queued", "running"}
_RUN_STATUS_TERMINAL = {"completed", "failed", "cancelled"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_scheduler_db_path() -> Path:
    configured = (os.getenv("SCHEDULER_DB_PATH", "") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "scheduler" / "scheduler.db"


def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    payload_raw = row["payload_json"] or "{}"
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        payload = {}
    return {
        "job_id": row["job_id"],
        "name": row["name"],
        "job_type": row["job_type"],
        "platform": row["platform"],
        "interval_minutes": row["interval_minutes"],
        "enabled": bool(row["enabled"]),
        "payload": payload,
        "next_run_at": row["next_run_at"],
        "last_run_at": row["last_run_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    details_raw = row["details_json"] or "{}"
    try:
        details = json.loads(details_raw)
    except json.JSONDecodeError:
        details = {}
    row_keys = set(row.keys())
    status = row["status"]
    if status == "accepted":
        status = "queued"
    elif status == "rejected":
        status = "failed"
    payload: dict[str, Any] = {
        "run_id": row["run_id"],
        "job_id": row["job_id"],
        "triggered_at": row["triggered_at"],
        "started_at": row["started_at"] if "started_at" in row_keys else None,
        "finished_at": row["finished_at"] if "finished_at" in row_keys else None,
        "updated_at": row["updated_at"] if "updated_at" in row_keys else row["triggered_at"],
        "status": status,
        "task_id": row["task_id"],
        "message": row["message"],
        "details": details,
    }
    if "platform" in row.keys():
        payload["platform"] = row["platform"]
    return payload


@dataclass(slots=True)
class SchedulerStore:
    """SQLite store for scheduler state."""

    db_path: Path

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _default_scheduler_db_path()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_jobs (
                    job_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    payload_json TEXT NOT NULL,
                    next_run_at TEXT NOT NULL,
                    last_run_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    triggered_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    task_id TEXT,
                    message TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            run_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info('scheduler_runs')").fetchall()
            }
            if "started_at" not in run_columns:
                conn.execute("ALTER TABLE scheduler_runs ADD COLUMN started_at TEXT")
            if "finished_at" not in run_columns:
                conn.execute("ALTER TABLE scheduler_runs ADD COLUMN finished_at TEXT")
            if "updated_at" not in run_columns:
                conn.execute("ALTER TABLE scheduler_runs ADD COLUMN updated_at TEXT")

            conn.execute(
                "UPDATE scheduler_runs SET updated_at = COALESCE(updated_at, triggered_at)"
            )
            conn.execute(
                """
                UPDATE scheduler_runs
                SET status = 'queued'
                WHERE status = 'accepted'
                """
            )
            conn.execute(
                """
                UPDATE scheduler_runs
                SET
                    status = 'failed',
                    finished_at = COALESCE(finished_at, triggered_at),
                    updated_at = COALESCE(updated_at, triggered_at)
                WHERE status = 'rejected'
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_next_run ON scheduler_jobs(next_run_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job_id ON scheduler_runs(job_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status ON scheduler_runs(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scheduler_runs_task_id ON scheduler_runs(task_id)"
            )
            conn.commit()

    def create_job(self, job: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO scheduler_jobs (
                    job_id, name, job_type, platform, interval_minutes, enabled,
                    payload_json, next_run_at, last_run_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["job_id"],
                    job["name"],
                    job["job_type"],
                    job["platform"],
                    int(job["interval_minutes"]),
                    1 if job.get("enabled", True) else 0,
                    json.dumps(job.get("payload", {}), ensure_ascii=False),
                    job["next_run_at"],
                    job.get("last_run_at"),
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get_job(job["job_id"]) or job

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM scheduler_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_job(row)

    def list_jobs(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM scheduler_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    def get_jobs_by_ids(self, job_ids: list[str]) -> list[dict[str, Any]]:
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for job_id in job_ids:
            candidate = str(job_id).strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized_ids.append(candidate)
        if not normalized_ids:
            return []

        placeholders = ", ".join(["?"] * len(normalized_ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM scheduler_jobs WHERE job_id IN ({placeholders})",
                tuple(normalized_ids),
            ).fetchall()

        by_id = {str(row["job_id"]): _row_to_job(row) for row in rows}
        return [by_id[job_id] for job_id in normalized_ids if job_id in by_id]

    def list_due_jobs(self, now_iso: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM scheduler_jobs
                WHERE enabled = 1 AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (now_iso,),
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    def update_job(self, job_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_job(job_id)
        allowed_fields = {
            "name",
            "interval_minutes",
            "enabled",
            "payload",
            "next_run_at",
            "last_run_at",
        }
        pairs: list[tuple[str, Any]] = []
        for key, value in updates.items():
            if key not in allowed_fields:
                continue
            if key == "payload":
                pairs.append(("payload_json", json.dumps(value or {}, ensure_ascii=False)))
            elif key == "enabled":
                pairs.append(("enabled", 1 if value else 0))
            else:
                pairs.append((key, value))
        if not pairs:
            return self.get_job(job_id)

        set_clause = ", ".join([f"{field} = ?" for field, _ in pairs] + ["updated_at = ?"])
        values = [value for _, value in pairs] + [_utc_now_iso(), job_id]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE scheduler_jobs SET {set_clause} WHERE job_id = ?",
                values,
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self.get_job(job_id)

    def delete_job(self, job_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM scheduler_jobs WHERE job_id = ?", (job_id,))
            conn.commit()
        return cursor.rowcount > 0

    def set_jobs_enabled(self, *, job_ids: list[str], enabled: bool) -> list[dict[str, Any]]:
        jobs = self.get_jobs_by_ids(job_ids)
        if not jobs:
            return []

        normalized_ids = [str(job["job_id"]) for job in jobs]
        placeholders = ", ".join(["?"] * len(normalized_ids))
        now_iso = _utc_now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""
                UPDATE scheduler_jobs
                SET enabled = ?, updated_at = ?
                WHERE job_id IN ({placeholders})
                """,
                (1 if enabled else 0, now_iso, *normalized_ids),
            )
            conn.commit()
        return self.get_jobs_by_ids(normalized_ids)

    def create_run(
        self,
        *,
        job_id: str,
        status: str,
        message: str,
        task_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        triggered_at: Optional[str] = None,
    ) -> int:
        normalized_status = (status or "").strip().lower() or "queued"
        if normalized_status == "accepted":
            normalized_status = "queued"
        elif normalized_status == "rejected":
            normalized_status = "failed"
        timestamp = triggered_at or _utc_now_iso()
        started_at = timestamp if normalized_status == "running" else None
        finished_at = timestamp if normalized_status in _RUN_STATUS_TERMINAL else None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO scheduler_runs (
                    job_id, triggered_at, started_at, finished_at, updated_at,
                    status, task_id, message, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    timestamp,
                    started_at,
                    finished_at,
                    timestamp,
                    normalized_status,
                    task_id,
                    message,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_run(self, run_id: int) -> Optional[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT r.*, j.platform AS platform
                FROM scheduler_runs AS r
                LEFT JOIN scheduler_jobs AS j ON j.job_id = r.job_id
                WHERE r.run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_run(row)

    def list_runs(
        self,
        *,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        platform: Optional[str] = None,
        triggered_from: Optional[str] = None,
        triggered_to: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if job_id:
            clauses.append("r.job_id = ?")
            params.append(job_id)
        if status:
            clauses.append("r.status = ?")
            params.append(status)
        if platform:
            clauses.append("j.platform = ?")
            params.append(platform)
        if triggered_from:
            clauses.append("r.triggered_at >= ?")
            params.append(triggered_from)
        if triggered_to:
            clauses.append("r.triggered_at <= ?")
            params.append(triggered_to)

        where_clause = ""
        if clauses:
            where_clause = f"WHERE {' AND '.join(clauses)}"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT r.*, j.platform AS platform
                FROM scheduler_runs AS r
                LEFT JOIN scheduler_jobs AS j ON j.job_id = r.job_id
                {where_clause}
                ORDER BY r.run_id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [_row_to_run(row) for row in rows]

    def list_open_runs(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT r.*, j.platform AS platform
                FROM scheduler_runs AS r
                LEFT JOIN scheduler_jobs AS j ON j.job_id = r.job_id
                WHERE r.status IN (?, ?)
                ORDER BY r.run_id ASC
                """,
                tuple(sorted(_RUN_STATUS_OPEN)),
            ).fetchall()
        return [_row_to_run(row) for row in rows]

    def update_run_status(
        self,
        *,
        run_id: int,
        status: str,
        message: Optional[str] = None,
        details_patch: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        existing = self.get_run(run_id)
        if existing is None:
            return None

        normalized_status = (status or "").strip().lower() or existing["status"]
        if normalized_status == "accepted":
            normalized_status = "queued"
        elif normalized_status == "rejected":
            normalized_status = "failed"
        now_iso = _utc_now_iso()

        merged_details = {
            **(existing.get("details") or {}),
            **(details_patch or {}),
        }

        started_at = existing.get("started_at")
        finished_at = existing.get("finished_at")

        if normalized_status == "running" and not started_at:
            started_at = now_iso
        if normalized_status in _RUN_STATUS_TERMINAL:
            if not started_at:
                started_at = existing.get("triggered_at") or now_iso
            if not finished_at:
                finished_at = now_iso

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE scheduler_runs
                SET
                    status = ?,
                    message = ?,
                    details_json = ?,
                    started_at = ?,
                    finished_at = ?,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    normalized_status,
                    existing["message"] if message is None else message,
                    json.dumps(merged_details, ensure_ascii=False),
                    started_at,
                    finished_at,
                    now_iso,
                    run_id,
                ),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self.get_run(run_id)
