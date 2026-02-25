# -*- coding: utf-8 -*-
"""Background scheduler service for keyword/KOL crawl jobs."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from api.response import ApiError

from ..schemas import CrawlerStartRequest
from ..schemas.scheduler import (
    SchedulerJobCreateRequest,
    SchedulerJobPatchRequest,
    SchedulerJobTypeEnum,
    SchedulerKolPayload,
    SchedulerKeywordPayload,
)
from .crawler_manager import crawler_manager
from .scheduler_store import SchedulerStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


class SchedulerService:
    """Periodic scheduler that dispatches jobs into crawler manager."""

    def __init__(
        self,
        *,
        store: Optional[SchedulerStore] = None,
        poll_interval_sec: Optional[float] = None,
        enabled: Optional[bool] = None,
    ):
        self._store = store or SchedulerStore()
        if poll_interval_sec is None:
            raw_poll = os.getenv("SCHEDULER_POLL_INTERVAL_SEC", "10")
            try:
                poll_interval_sec = float(raw_poll)
            except ValueError:
                poll_interval_sec = 10.0
        self._poll_interval_sec = max(1.0, min(float(poll_interval_sec), 300.0))
        if enabled is None:
            enabled = (os.getenv("SCHEDULER_ENABLED", "true") or "true").strip().lower() in {
                "1",
                "true",
                "yes",
                "y",
                "on",
            }
        self._enabled = bool(enabled)
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._running_job_ids: set[str] = set()
        self._last_tick_at: Optional[str] = None
        self._last_error: Optional[str] = None
        raw_grace = os.getenv("SCHEDULER_RUN_TERMINAL_GRACE_SEC", "10")
        try:
            parsed_grace = float(raw_grace)
        except ValueError:
            parsed_grace = 10.0
        self._run_terminal_grace_sec = max(1.0, min(parsed_grace, 600.0))
        raw_backfill_limit = os.getenv("SCHEDULER_RUNTIME_STATE_BACKFILL_LIMIT", "500")
        try:
            parsed_backfill_limit = int(raw_backfill_limit)
        except ValueError:
            parsed_backfill_limit = 500
        self._runtime_state_backfill_limit = max(0, min(parsed_backfill_limit, 5000))
        self._run_statuses = {
            "accepted",
            "rejected",
            "queued",
            "running",
            "completed",
            "failed",
            "cancelled",
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "running": self._task is not None and not self._task.done(),
            "poll_interval_sec": self._poll_interval_sec,
            "last_tick_at": self._last_tick_at,
            "last_error": self._last_error,
        }

    async def initialize(self) -> None:
        await asyncio.to_thread(self._store.initialize)

    async def start(self) -> None:
        if not self._enabled:
            return
        await self.initialize()
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="scheduler-loop")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive runtime fallback
                self._last_error = str(exc)
            await asyncio.sleep(self._poll_interval_sec)

    async def _tick(self) -> None:
        now_iso = _utc_now_iso()
        self._last_tick_at = now_iso
        await self._sync_run_lifecycle()
        due_jobs = await asyncio.to_thread(self._store.list_due_jobs, now_iso)
        for job in due_jobs:
            await self._trigger_job(job, trigger_reason="scheduled")
        await self._sync_run_lifecycle()

    async def list_jobs(self) -> list[dict[str, Any]]:
        await self.initialize()
        return await asyncio.to_thread(self._store.list_jobs)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        await self.initialize()
        job = await asyncio.to_thread(self._store.get_job, job_id)
        if job is None:
            raise ApiError(status_code=404, code="SCHEDULER_JOB_NOT_FOUND", message="Scheduler job not found")
        return job

    async def create_job(self, request: SchedulerJobCreateRequest) -> dict[str, Any]:
        await self.initialize()
        payload = self._validate_payload(request.job_type, request.payload)
        now = _utc_now()
        job = {
            "job_id": f"job-{uuid.uuid4().hex[:12]}",
            "name": request.name.strip(),
            "job_type": request.job_type.value,
            "platform": request.platform.value,
            "interval_minutes": int(request.interval_minutes),
            "enabled": request.enabled,
            "payload": payload,
            "next_run_at": (now + timedelta(minutes=int(request.interval_minutes))).isoformat(),
            "last_run_at": None,
        }
        return await asyncio.to_thread(self._store.create_job, job)

    async def update_job(self, job_id: str, request: SchedulerJobPatchRequest) -> dict[str, Any]:
        await self.initialize()
        existing = await asyncio.to_thread(self._store.get_job, job_id)
        if existing is None:
            raise ApiError(status_code=404, code="SCHEDULER_JOB_NOT_FOUND", message="Scheduler job not found")

        updates: dict[str, Any] = {}
        if request.name is not None:
            updates["name"] = request.name.strip()
        if request.interval_minutes is not None:
            updates["interval_minutes"] = int(request.interval_minutes)
            updates["next_run_at"] = (_utc_now() + timedelta(minutes=int(request.interval_minutes))).isoformat()
        if request.enabled is not None:
            updates["enabled"] = bool(request.enabled)
        if request.payload is not None:
            payload = self._validate_payload(
                SchedulerJobTypeEnum(existing["job_type"]),
                request.payload,
            )
            updates["payload"] = payload

        updated = await asyncio.to_thread(self._store.update_job, job_id, updates)
        if updated is None:
            raise ApiError(status_code=404, code="SCHEDULER_JOB_NOT_FOUND", message="Scheduler job not found")
        return updated

    async def delete_job(self, job_id: str) -> bool:
        await self.initialize()
        return await asyncio.to_thread(self._store.delete_job, job_id)

    async def clone_job(self, job_id: str, *, name: Optional[str] = None) -> dict[str, Any]:
        source = await self.get_job(job_id)
        clone_name = (name or "").strip() or f'{source["name"]} (copy)'
        if len(clone_name) > 120:
            raise ApiError(
                status_code=422,
                code="SCHEDULER_JOB_NAME_TOO_LONG",
                message="Scheduler job name too long",
                details={"max_length": 120},
            )

        request = SchedulerJobCreateRequest(
            name=clone_name,
            job_type=source["job_type"],
            platform=source["platform"],
            interval_minutes=int(source["interval_minutes"]),
            enabled=bool(source["enabled"]),
            payload=dict(source.get("payload", {})),
        )
        return await self.create_job(request)

    async def batch_set_enabled(self, *, job_ids: list[str], enabled: bool) -> dict[str, Any]:
        await self.initialize()
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for raw in job_ids:
            job_id = str(raw).strip()
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            normalized_ids.append(job_id)
        if not normalized_ids:
            raise ApiError(
                status_code=422,
                code="SCHEDULER_JOB_IDS_REQUIRED",
                message="At least one scheduler job id is required",
            )

        existing_jobs = await asyncio.to_thread(self._store.get_jobs_by_ids, normalized_ids)
        existing_ids = {str(item["job_id"]) for item in existing_jobs}
        missing_ids = [job_id for job_id in normalized_ids if job_id not in existing_ids]
        if missing_ids:
            raise ApiError(
                status_code=404,
                code="SCHEDULER_JOB_NOT_FOUND",
                message="One or more scheduler jobs were not found",
                details={"missing_job_ids": missing_ids},
            )

        updated_jobs = await asyncio.to_thread(
            self._store.set_jobs_enabled,
            job_ids=normalized_ids,
            enabled=bool(enabled),
        )
        return {
            "updated": len(updated_jobs),
            "enabled": bool(enabled),
            "jobs": updated_jobs,
        }

    async def run_now(self, job_id: str) -> dict[str, Any]:
        await self.initialize()
        job = await asyncio.to_thread(self._store.get_job, job_id)
        if job is None:
            raise ApiError(status_code=404, code="SCHEDULER_JOB_NOT_FOUND", message="Scheduler job not found")
        return await self._trigger_job(job, trigger_reason="manual")

    async def get_run(self, run_id: int) -> dict[str, Any]:
        await self.initialize()
        await self._sync_run_lifecycle()
        run = await asyncio.to_thread(self._store.get_run, int(run_id))
        if run is None:
            raise ApiError(status_code=404, code="SCHEDULER_RUN_NOT_FOUND", message="Scheduler run not found")
        return run

    async def list_runs(
        self,
        *,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        platform: Optional[str] = None,
        triggered_from: Optional[str] = None,
        triggered_to: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        await self.initialize()
        bounded_limit = max(1, min(limit, 500))
        normalized_status = self._normalize_run_status_filter(status)

        normalized_platform = None
        if platform is not None:
            normalized_platform = platform.strip().lower()
            if normalized_platform == "":
                normalized_platform = None

        from_iso = self._normalize_time_filter(triggered_from, "from")
        to_iso = self._normalize_time_filter(triggered_to, "to")
        if from_iso and to_iso and from_iso > to_iso:
            raise ApiError(
                status_code=422,
                code="SCHEDULER_RUN_TIME_RANGE_INVALID",
                message="Invalid scheduler run time range",
                details={"from": from_iso, "to": to_iso},
            )

        await self._sync_run_lifecycle()

        return await asyncio.to_thread(
            self._store.list_runs,
            job_id=job_id,
            status=normalized_status,
            platform=normalized_platform,
            triggered_from=from_iso,
            triggered_to=to_iso,
            limit=bounded_limit,
        )

    async def _trigger_job(self, job: dict[str, Any], *, trigger_reason: str) -> dict[str, Any]:
        job_id = str(job["job_id"])
        async with self._lock:
            if job_id in self._running_job_ids:
                return {
                    "accepted": False,
                    "task_id": None,
                    "message": f"Job {job_id} is already being triggered",
                    "run_id": 0,
                }
            self._running_job_ids.add(job_id)

        try:
            request = self._job_to_crawler_request(job)
            result = await crawler_manager.start(request)
            accepted = bool(result.get("accepted"))
            task_id = result.get("task_id")
            if accepted:
                message = "Crawler task accepted"
                run_status = self._resolve_task_runtime_status(task_id)
                run_message = "Crawler task running" if run_status == "running" else "Crawler task queued"
            else:
                message = str(result.get("error", "Task rejected"))
                run_status = "failed"
                run_message = message

            run_details = {
                "trigger_reason": trigger_reason,
                "result": result,
            }
            if run_status in {"completed", "failed", "cancelled"}:
                run_details.update(
                    self._build_terminal_fallback_details(
                        terminal_message=run_message,
                        exit_code=None,
                        terminal_source="scheduler",
                    )
                )
                if run_status == "failed":
                    run_details["failure_reason"] = run_message

            run_id = await asyncio.to_thread(
                self._store.create_run,
                job_id=job_id,
                status=run_status,
                message=run_message,
                task_id=task_id,
                details=run_details,
            )
            next_run_at = (_utc_now() + timedelta(minutes=int(job["interval_minutes"]))).isoformat()
            await asyncio.to_thread(
                self._store.update_job,
                job_id,
                {
                    "last_run_at": _utc_now_iso(),
                    "next_run_at": next_run_at,
                },
            )
            await self._sync_run_lifecycle()
            return {
                "accepted": accepted,
                "task_id": task_id,
                "message": message,
                "run_id": run_id,
            }
        finally:
            async with self._lock:
                self._running_job_ids.discard(job_id)

    async def _sync_run_lifecycle(self) -> None:
        await self.initialize()
        open_runs = await asyncio.to_thread(self._store.list_open_runs)

        if open_runs:
            try:
                cluster_snapshot = crawler_manager.get_cluster_status()
            except Exception:  # pragma: no cover - defensive fallback
                cluster_snapshot = {}

            active_task_ids = {
                str(task_id)
                for task_id in (cluster_snapshot.get("active_task_ids") or [])
                if task_id
            }
            pending_task_ids = {
                str(task_id)
                for task_id in (cluster_snapshot.get("pending_task_ids") or [])
                if task_id
            }

            for run in open_runs:
                run_id = int(run["run_id"])
                task_id = str(run.get("task_id") or "").strip()

                if not task_id:
                    if self._is_run_past_grace_period(run):
                        await asyncio.to_thread(
                            self._store.update_run_status,
                            run_id=run_id,
                            status="failed",
                            message="Crawler task missing task_id; marked as failed",
                            details_patch={
                                "failure_reason": "missing_task_id",
                                **self._build_terminal_fallback_details(
                                    terminal_message="Crawler task missing task_id; marked as failed",
                                    exit_code=None,
                                    terminal_source="scheduler_runtime",
                                ),
                            },
                        )
                    continue

                if task_id in active_task_ids:
                    if run.get("status") != "running":
                        await asyncio.to_thread(
                            self._store.update_run_status,
                            run_id=run_id,
                            status="running",
                            message="Crawler task running",
                        )
                    continue

                if task_id in pending_task_ids:
                    if run.get("status") != "queued":
                        await asyncio.to_thread(
                            self._store.update_run_status,
                            run_id=run_id,
                            status="queued",
                            message="Crawler task queued",
                        )
                    continue

                terminal = self._find_terminal_log_for_task(task_id)
                if terminal is not None:
                    terminal_status, terminal_message, terminal_details = terminal
                    await asyncio.to_thread(
                        self._store.update_run_status,
                        run_id=run_id,
                        status=terminal_status,
                        message=terminal_message,
                        details_patch=terminal_details,
                    )
                    continue

                if not self._is_run_past_grace_period(run):
                    continue

                await asyncio.to_thread(
                    self._store.update_run_status,
                    run_id=run_id,
                    status="failed",
                    message="Crawler task left runtime queue unexpectedly",
                    details_patch={
                        "failure_reason": "runtime_state_missing",
                        **self._build_terminal_fallback_details(
                            terminal_message="Crawler task left runtime queue unexpectedly",
                            exit_code=None,
                            terminal_source="scheduler_runtime",
                        ),
                    },
                )

        await self._backfill_runtime_state_missing_runs()

    async def _backfill_runtime_state_missing_runs(self) -> None:
        if self._runtime_state_backfill_limit <= 0:
            return

        runs = await asyncio.to_thread(
            self._store.list_runs,
            job_id=None,
            status="failed",
            platform=None,
            triggered_from=None,
            triggered_to=None,
            limit=self._runtime_state_backfill_limit,
        )

        for run in runs:
            details = run.get("details") or {}
            if details.get("failure_reason") != "runtime_state_missing":
                continue

            task_id = str(run.get("task_id") or "").strip()
            if not task_id:
                continue

            terminal = self._find_terminal_log_for_task(task_id)
            if terminal is None:
                continue

            terminal_status, terminal_message, terminal_details = terminal
            details_patch: dict[str, Any] = {
                **terminal_details,
                "runtime_state_backfilled": True,
                "failure_reason": terminal_details.get("failure_reason"),
            }
            await asyncio.to_thread(
                self._store.update_run_status,
                run_id=int(run["run_id"]),
                status=terminal_status,
                message=terminal_message,
                details_patch=details_patch,
            )

    def _resolve_task_runtime_status(self, task_id: Optional[str]) -> str:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return "queued"
        try:
            cluster_snapshot = crawler_manager.get_cluster_status()
        except Exception:  # pragma: no cover - defensive fallback
            return "queued"

        active_task_ids = {
            str(item)
            for item in (cluster_snapshot.get("active_task_ids") or [])
            if item
        }
        if normalized_task_id in active_task_ids:
            return "running"
        return "queued"

    def _find_terminal_log_for_task(
        self,
        task_id: str,
    ) -> Optional[tuple[str, str, dict[str, Any]]]:
        escaped_task_id = re.escape(task_id)
        exit_pattern = re.compile(rf"Task {escaped_task_id} exited with code\s+(-?\d+)")
        spawn_failure_pattern = re.compile(rf"Failed to start task {escaped_task_id}:\s*(.+)")

        for entry in reversed(getattr(crawler_manager, "logs", [])):
            message = str(getattr(entry, "message", "") or "")
            if not message:
                continue

            if f"Task {task_id} completed successfully" in message:
                return (
                    "completed",
                    "Crawler task completed successfully",
                    self._build_terminal_log_details(
                        entry,
                        exit_code=0,
                    ),
                )

            exit_match = exit_pattern.search(message)
            if exit_match:
                exit_code = int(exit_match.group(1))
                return (
                    "failed",
                    f"Crawler task failed with exit code {exit_code}",
                    self._build_terminal_log_details(
                        entry,
                        exit_code=exit_code,
                    ),
                )

            failure_match = spawn_failure_pattern.search(message)
            if failure_match:
                failure_reason = failure_match.group(1).strip()
                return (
                    "failed",
                    "Crawler task failed to start",
                    self._build_terminal_log_details(
                        entry,
                        exit_code=None,
                        failure_reason=failure_reason,
                    ),
                )

        return None

    def _build_terminal_log_details(
        self,
        entry: Any,
        *,
        exit_code: Optional[int],
        failure_reason: Optional[str] = None,
    ) -> dict[str, Any]:
        message = str(getattr(entry, "message", "") or "")
        details = self._build_terminal_fallback_details(
            terminal_message=message,
            exit_code=exit_code,
            terminal_log_id=self._normalize_terminal_log_id(getattr(entry, "id", None)),
            terminal_source="crawler_log",
        )
        if failure_reason is not None:
            details["failure_reason"] = failure_reason
        return details

    def _build_terminal_fallback_details(
        self,
        *,
        terminal_message: Optional[str],
        exit_code: Optional[int],
        terminal_log_id: Optional[int] = None,
        terminal_source: str = "scheduler",
    ) -> dict[str, Any]:
        return {
            "exit_code": exit_code,
            "terminal_log_id": terminal_log_id,
            "terminal_message_excerpt": self._build_terminal_message_excerpt(terminal_message or ""),
            "terminal_source": terminal_source,
        }

    def _normalize_terminal_log_id(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _build_terminal_message_excerpt(self, message: str) -> str:
        normalized = " ".join(str(message or "").split()).strip()
        if len(normalized) <= 200:
            return normalized
        return f"{normalized[:197]}..."

    def _is_run_past_grace_period(self, run: dict[str, Any]) -> bool:
        reference_iso = str(run.get("started_at") or run.get("triggered_at") or "").strip()
        if not reference_iso:
            return True

        parsed = self._parse_iso_datetime(reference_iso)
        if parsed is None:
            return True

        age_sec = (_utc_now() - parsed).total_seconds()
        return age_sec >= self._run_terminal_grace_sec

    def _parse_iso_datetime(self, value: str) -> Optional[datetime]:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _normalize_run_status_filter(self, status: Optional[str]) -> Optional[str]:
        if status is None:
            return None

        normalized_status = status.strip().lower()
        if normalized_status not in self._run_statuses:
            raise ApiError(
                status_code=422,
                code="SCHEDULER_RUN_STATUS_INVALID",
                message="Invalid scheduler run status filter",
                details={"allowed": sorted(self._run_statuses)},
            )

        if normalized_status == "accepted":
            return "queued"
        if normalized_status == "rejected":
            return "failed"
        return normalized_status

    def _validate_payload(
        self,
        job_type: SchedulerJobTypeEnum,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if job_type == SchedulerJobTypeEnum.KEYWORD:
            return SchedulerKeywordPayload(**payload).model_dump()
        if job_type == SchedulerJobTypeEnum.KOL:
            return SchedulerKolPayload(**payload).model_dump()
        raise ApiError(
            status_code=400,
            code="SCHEDULER_JOB_TYPE_UNSUPPORTED",
            message=f"Unsupported scheduler job type: {job_type}",
        )

    def _job_to_crawler_request(self, job: dict[str, Any]) -> CrawlerStartRequest:
        payload = self._validate_payload(
            SchedulerJobTypeEnum(job["job_type"]),
            job.get("payload", {}),
        )
        job_type = SchedulerJobTypeEnum(job["job_type"])
        if job_type == SchedulerJobTypeEnum.KEYWORD:
            return CrawlerStartRequest(
                platform=job["platform"],
                crawler_type="search",
                login_type=payload["login_type"],
                keywords=payload["keywords"],
                start_page=payload["start_page"],
                enable_comments=payload["enable_comments"],
                enable_sub_comments=payload["enable_sub_comments"],
                save_option=payload["save_option"],
                cookies=payload["cookies"],
                headless=payload["headless"],
                safety_profile=payload["safety_profile"],
                max_notes_count=payload["max_notes_count"],
                crawl_sleep_sec=payload["crawl_sleep_sec"],
            )

        return CrawlerStartRequest(
            platform=job["platform"],
            crawler_type="creator",
            login_type=payload["login_type"],
            creator_ids=payload["creator_ids"],
            start_page=payload["start_page"],
            enable_comments=payload["enable_comments"],
            enable_sub_comments=payload["enable_sub_comments"],
            save_option=payload["save_option"],
            cookies=payload["cookies"],
            headless=payload["headless"],
            safety_profile=payload["safety_profile"],
            max_notes_count=payload["max_notes_count"],
            crawl_sleep_sec=payload["crawl_sleep_sec"],
        )

    def _normalize_time_filter(self, value: Optional[str], field_name: str) -> Optional[str]:
        if value is None:
            return None
        candidate = value.strip()
        if candidate == "":
            return None

        normalized = candidate
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ApiError(
                status_code=422,
                code="SCHEDULER_RUN_TIME_FILTER_INVALID",
                message=f"Invalid scheduler run {field_name} filter",
                details={"field": field_name, "value": value},
            ) from exc

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat()


scheduler_service = SchedulerService()
