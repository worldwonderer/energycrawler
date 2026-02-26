# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/api/services/crawler_manager.py
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
import signal
import subprocess
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Deque, List, Optional

from ..schemas import CrawlerStartRequest, LogEntry, SafetyProfileEnum
from tools.cookiecloud_sync import sync_cookiecloud_login_state
from tools import utils
from tools.preflight import build_preflight_failure_hint, preflight_for_platform


class CrawlerManager:
    """Simplified crawler cluster manager (queue + worker pool)."""

    _SENSITIVE_CLI_FLAGS = {"--cookies"}

    _SAFETY_PROFILE_DEFAULTS = {
        SafetyProfileEnum.SAFE: {"max_notes_count": 5, "crawl_sleep_sec": 10.0},
        SafetyProfileEnum.BALANCED: {"max_notes_count": 10, "crawl_sleep_sec": 8.0},
        SafetyProfileEnum.AGGRESSIVE: {"max_notes_count": 20, "crawl_sleep_sec": 6.0},
    }

    def __init__(
        self,
        max_workers: Optional[int] = None,
        max_queue_size: Optional[int] = None,
        max_spawn_retries: Optional[int] = None,
        log_buffer_capacity: Optional[int] = None,
        process_factory: Optional[Callable[..., subprocess.Popen]] = None,
        enable_output_reader: bool = True,
    ):
        self._lock = asyncio.Lock()
        self._process_factory = process_factory or subprocess.Popen
        self._enable_output_reader = enable_output_reader
        self.max_workers = self._resolve_max_workers(max_workers)
        self.max_queue_size = self._resolve_max_queue_size(max_queue_size)
        self.max_spawn_retries = self._resolve_max_spawn_retries(max_spawn_retries)
        self.log_buffer_capacity = self._resolve_log_buffer_capacity(log_buffer_capacity)

        self._workers: List["_WorkerSlot"] = [
            _WorkerSlot(worker_id=index + 1) for index in range(self.max_workers)
        ]
        self._pending_tasks: Deque["_QueuedTask"] = deque()
        self._task_seq = 0
        self._stopping = False

        self.status = "idle"
        self.started_at: Optional[datetime] = None
        self.current_config: Optional[CrawlerStartRequest] = None
        self._last_error: Optional[str] = None

        self._log_id = 0
        self._logs: List[LogEntry] = []
        # Project root directory
        self._project_root = Path(__file__).parent.parent.parent
        # Log queue - for pushing to WebSocket
        self._log_queue: Optional[asyncio.Queue] = None
        self._dispatch_retry_task: Optional[asyncio.Task] = None
        self._dispatch_retry_delay_sec = self._resolve_dispatch_retry_delay()

    @property
    def logs(self) -> List[LogEntry]:
        return self._logs

    @property
    def process(self) -> Optional[subprocess.Popen]:
        """Compatibility shim for legacy code paths."""
        for worker in self._workers:
            if worker.process and worker.process.poll() is None:
                return worker.process
        return None

    def get_log_queue(self) -> asyncio.Queue:
        """Get or create log queue"""
        if self._log_queue is None:
            self._log_queue = asyncio.Queue()
        return self._log_queue

    def _create_log_entry(self, message: str, level: str = "info") -> LogEntry:
        """Create log entry"""
        self._log_id += 1
        entry = LogEntry(
            id=self._log_id,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level,
            message=message
        )
        self._logs.append(entry)
        # Keep the most recent N logs
        if len(self._logs) > self.log_buffer_capacity:
            self._logs = self._logs[-self.log_buffer_capacity:]
        return entry

    async def _push_log(self, entry: LogEntry):
        """Push log to queue"""
        if self._log_queue is not None:
            try:
                self._log_queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def _parse_log_level(self, line: str) -> str:
        """Parse log level"""
        line_upper = line.upper()
        if "ERROR" in line_upper or "FAILED" in line_upper:
            return "error"
        elif "WARNING" in line_upper or "WARN" in line_upper:
            return "warning"
        elif "SUCCESS" in line_upper or "完成" in line or "成功" in line:
            return "success"
        elif "DEBUG" in line_upper:
            return "debug"
        return "info"

    async def start(self, config: CrawlerStartRequest) -> dict:
        """Enqueue crawler task and dispatch to idle workers."""
        cookiecloud_result = await asyncio.to_thread(
            sync_cookiecloud_login_state,
            config.platform.value,
            config.cookies,
        )
        if cookiecloud_result.applied and not config.cookies and cookiecloud_result.cookie_header:
            config.cookies = cookiecloud_result.cookie_header
            entry = self._create_log_entry(
                (
                    "[AUTH] CookieCloud synced runtime cookies "
                    f"(platform={config.platform.value}, count={cookiecloud_result.cookie_count})"
                ),
                "info",
            )
            await self._push_log(entry)
        elif cookiecloud_result.attempted and not cookiecloud_result.applied:
            entry = self._create_log_entry(
                f"[AUTH] CookieCloud sync failed: {cookiecloud_result.message}",
                "warning",
            )
            await self._push_log(entry)

        ok, preflight_message = preflight_for_platform(config.platform.value, config.cookies)
        if not ok:
            hint_message = build_preflight_failure_hint(config.platform.value, preflight_message)
            self._last_error = hint_message
            entry = self._create_log_entry(
                f"[PREFLIGHT] rejected task: {hint_message}",
                "error",
            )
            await self._push_log(entry)
            utils.log_event(
                "crawler_manager.preflight.failed",
                level="warning",
                platform=config.platform.value,
                crawler_type=config.crawler_type.value,
                message=hint_message,
            )
            return {"accepted": False, "error": hint_message}

        async with self._lock:
            if self._stopping:
                error = "Crawler cluster is stopping, reject new tasks"
                entry = self._create_log_entry(f"[QUEUE] rejected task: {error}", "warning")
                await self._push_log(entry)
                return {"accepted": False, "error": error}

            if len(self._pending_tasks) >= self.max_queue_size:
                error = f"Crawler queue is full ({self.max_queue_size}), please retry later"
                entry = self._create_log_entry(f"[QUEUE] rejected task: {error}", "warning")
                await self._push_log(entry)
                utils.log_event(
                    "crawler_manager.queue.full",
                    level="warning",
                    platform=config.platform.value,
                    crawler_type=config.crawler_type.value,
                    queue_size=len(self._pending_tasks),
                    max_queue_size=self.max_queue_size,
                )
                return {"accepted": False, "error": error}

            task = _QueuedTask(
                task_id=self._next_task_id(),
                config=config,
                enqueued_at=datetime.now(),
            )
            self._pending_tasks.append(task)
            self._last_error = None
            if self.started_at is None:
                self.started_at = datetime.now()

            entry = self._create_log_entry(
                f"[QUEUE] Task accepted: {task.task_id} (platform={config.platform.value}, type={config.crawler_type.value})",
                "info",
            )
            await self._push_log(entry)
            utils.log_event(
                "crawler_manager.task.accepted",
                task_id=task.task_id,
                platform=config.platform.value,
                crawler_type=config.crawler_type.value,
            )

            await self._dispatch_pending_locked()
            snapshot = self._compose_status_locked()

            if (
                self._last_error
                and task.task_id in snapshot["pending_task_ids"]
                and task.spawn_attempts >= self.max_spawn_retries
            ):
                self._remove_pending_task_locked(task.task_id)
                error = f"Failed to start task {task.task_id}: {self._last_error}"
                entry = self._create_log_entry(f"[QUEUE] {error}", "error")
                await self._push_log(entry)
                self._refresh_runtime_status_locked()
                snapshot = self._compose_status_locked()
                return {
                    "accepted": False,
                    "error": error,
                    "queued_tasks": snapshot["queued_tasks"],
                    "running_workers": snapshot["running_workers"],
                }

            if (
                self._last_error
                and snapshot["running_workers"] == 0
                and task.task_id not in snapshot["active_task_ids"]
                and task.task_id not in snapshot["pending_task_ids"]
                and task.spawn_attempts >= self.max_spawn_retries
            ):
                error = f"Failed to start task {task.task_id}: {self._last_error}"
                entry = self._create_log_entry(f"[QUEUE] {error}", "error")
                await self._push_log(entry)
                return {
                    "accepted": False,
                    "error": error,
                    "queued_tasks": snapshot["queued_tasks"],
                    "running_workers": snapshot["running_workers"],
                }

            return {
                "accepted": True,
                "task_id": task.task_id,
                "queued_tasks": snapshot["queued_tasks"],
                "running_workers": snapshot["running_workers"],
            }

    async def stop(self) -> bool:
        """Stop running workers and clear pending queue."""
        async with self._lock:
            running_workers = [
                worker for worker in self._workers
                if worker.process and worker.process.poll() is None
            ]
            pending_count = len(self._pending_tasks)
            if not running_workers and pending_count == 0:
                return False

            self._stopping = True
            self.status = "stopping"
            self.current_config = None
            if self._dispatch_retry_task and not self._dispatch_retry_task.done():
                self._dispatch_retry_task.cancel()
            self._dispatch_retry_task = None
            if pending_count:
                self._pending_tasks.clear()
                entry = self._create_log_entry(
                    f"[QUEUE] Cleared {pending_count} pending task(s)",
                    "warning",
                )
                await self._push_log(entry)

            process_refs = [
                (worker.worker_id, worker.task_id or "", worker.process, worker.read_task)
                for worker in running_workers
            ]

        for worker_id, task_id, process, _ in process_refs:
            try:
                entry = self._create_log_entry(
                    f"[W{worker_id}] Sending SIGTERM for task {task_id}",
                    "warning",
                )
                await self._push_log(entry)
                process.send_signal(signal.SIGTERM)
            except Exception as exc:
                entry = self._create_log_entry(
                    f"[W{worker_id}] Failed to send SIGTERM: {exc}",
                    "error",
                )
                await self._push_log(entry)

        for _ in range(30):
            if all(process.poll() is not None for _, _, process, _ in process_refs):
                break
            await asyncio.sleep(0.5)

        for worker_id, _, process, _ in process_refs:
            if process.poll() is None:
                try:
                    process.kill()
                    entry = self._create_log_entry(
                        f"[W{worker_id}] SIGKILL sent (graceful shutdown timeout)",
                        "warning",
                    )
                    await self._push_log(entry)
                except Exception as exc:
                    entry = self._create_log_entry(
                        f"[W{worker_id}] Failed to SIGKILL process: {exc}",
                        "error",
                    )
                    await self._push_log(entry)

        async with self._lock:
            for worker_id, _, process, read_task in process_refs:
                worker = self._workers[worker_id - 1]
                if worker.process is process:
                    worker.process = None
                    worker.task_id = None
                    worker.config = None
                    worker.started_at = None
                if read_task and not read_task.done():
                    read_task.cancel()
                if worker.read_task is read_task:
                    worker.read_task = None

            self._stopping = False
            self.started_at = None
            self._refresh_runtime_status_locked()

            return True

    def get_status(self) -> dict:
        """Get current status."""
        return self._compose_status_unlocked()

    def get_cluster_status(self) -> dict:
        """Return detailed cluster runtime state."""
        return self._compose_status_unlocked()

    def _build_command(self, config: CrawlerStartRequest) -> list:
        """Build main.py command line arguments"""
        cmd = ["uv", "run", "python", "main.py"]

        cmd.extend(["--platform", config.platform.value])
        cmd.extend(["--lt", config.login_type.value])
        cmd.extend(["--type", config.crawler_type.value])
        cmd.extend(["--save_data_option", config.save_option.value])

        # Pass different arguments based on crawler type
        if config.crawler_type.value == "search" and config.keywords:
            cmd.extend(["--keywords", config.keywords])
        elif config.crawler_type.value == "detail" and config.specified_ids:
            cmd.extend(["--specified_id", config.specified_ids])
        elif config.crawler_type.value == "creator" and config.creator_ids:
            cmd.extend(["--creator_id", config.creator_ids])

        if config.start_page != 1:
            cmd.extend(["--start", str(config.start_page)])

        cmd.extend(["--get_comment", "true" if config.enable_comments else "false"])
        cmd.extend(["--get_sub_comment", "true" if config.enable_sub_comments else "false"])

        if config.cookies:
            cmd.extend(["--cookies", config.cookies])

        resolved_limits = self._resolve_safety_limits(config)

        if resolved_limits["max_notes_count"] is not None:
            cmd.extend(["--max_notes_count", str(resolved_limits["max_notes_count"])])

        if resolved_limits["crawl_sleep_sec"] is not None:
            cmd.extend(["--crawl_sleep_sec", str(resolved_limits["crawl_sleep_sec"])])

        cmd.extend(["--headless", "true" if config.headless else "false"])

        return cmd

    def _sanitize_command_for_log(self, cmd: list[str]) -> str:
        """Mask sensitive CLI argument values before logging command text."""
        sanitized: list[str] = []
        redact_next = False

        for token in cmd:
            if redact_next:
                sanitized.append("<redacted>")
                redact_next = False
                continue

            if token in self._SENSITIVE_CLI_FLAGS:
                sanitized.append(token)
                redact_next = True
                continue

            masked_token = token
            for flag in self._SENSITIVE_CLI_FLAGS:
                prefix = f"{flag}="
                if token.startswith(prefix):
                    masked_token = f"{flag}=<redacted>"
                    break
            sanitized.append(masked_token)

        return " ".join(sanitized)

    def _resolve_safety_limits(self, config: CrawlerStartRequest) -> dict:
        max_notes_count = config.max_notes_count
        crawl_sleep_sec = config.crawl_sleep_sec

        if config.safety_profile is None:
            return {
                "max_notes_count": max_notes_count,
                "crawl_sleep_sec": crawl_sleep_sec,
            }

        defaults = self._resolve_profile_defaults(config.safety_profile)
        if max_notes_count is None:
            max_notes_count = defaults["max_notes_count"]
        if crawl_sleep_sec is None:
            crawl_sleep_sec = defaults["crawl_sleep_sec"]

        return {
            "max_notes_count": max_notes_count,
            "crawl_sleep_sec": crawl_sleep_sec,
        }

    def _resolve_profile_defaults(self, profile: SafetyProfileEnum) -> dict:
        hard_max_notes_count = self._read_int_env("CRAWLER_HARD_MAX_NOTES_COUNT", default=20, minimum=1)
        min_sleep_sec = self._read_float_env("CRAWLER_MIN_SLEEP_SEC", default=6.0, minimum=0.1)

        base = self._SAFETY_PROFILE_DEFAULTS.get(profile, self._SAFETY_PROFILE_DEFAULTS[SafetyProfileEnum.SAFE])
        return {
            "max_notes_count": min(max(1, int(base["max_notes_count"])), hard_max_notes_count),
            "crawl_sleep_sec": max(float(base["crawl_sleep_sec"]), min_sleep_sec),
        }

    def _read_int_env(self, key: str, *, default: int, minimum: int) -> int:
        raw_value = os.getenv(key, str(default))
        try:
            candidate = int(raw_value)
        except ValueError:
            candidate = default
        return max(minimum, candidate)

    def _read_float_env(self, key: str, *, default: float, minimum: float) -> float:
        raw_value = os.getenv(key, str(default))
        try:
            candidate = float(raw_value)
        except ValueError:
            candidate = default
        return max(minimum, candidate)

    async def _read_output(self, worker_id: int, process: subprocess.Popen, task_id: str):
        """Asynchronously read worker process output."""
        loop = asyncio.get_event_loop()
        task_tag = f"[W{worker_id}][{task_id}]"

        try:
            while process.poll() is None and process.stdout:
                line = await loop.run_in_executor(
                    None, process.stdout.readline
                )
                if not line:
                    await asyncio.sleep(0.05)
                    continue

                output = line.strip()
                if not output:
                    continue

                level = self._parse_log_level(output)
                entry = self._create_log_entry(f"{task_tag} {output}", level)
                await self._push_log(entry)

            if process.stdout:
                remaining = await loop.run_in_executor(
                    None, process.stdout.read
                )
                if remaining:
                    for line in remaining.strip().split('\n'):
                        output = line.strip()
                        if output:
                            level = self._parse_log_level(output)
                            entry = self._create_log_entry(f"{task_tag} {output}", level)
                            await self._push_log(entry)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            entry = self._create_log_entry(
                f"{task_tag} Error reading output: {exc}",
                "error",
            )
            await self._push_log(entry)
        finally:
            await self._on_worker_exit(
                worker_id=worker_id,
                process=process,
                task_id=task_id,
                exit_code=process.returncode if process.returncode is not None else -1,
            )

    async def _dispatch_pending_locked(self):
        while self._pending_tasks:
            worker = self._find_idle_worker_locked()
            if worker is None:
                break

            task = self._pending_tasks.popleft()
            cmd = self._build_command(task.config)
            worker_env = self._build_worker_env(task, worker.worker_id)
            try:
                process = self._process_factory(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    cwd=str(self._project_root),
                    env=worker_env,
                )
            except Exception as exc:
                task.spawn_attempts += 1
                self._last_error = str(exc)
                self.status = "error"
                retryable = task.spawn_attempts < self.max_spawn_retries
                if retryable:
                    self._pending_tasks.append(task)
                    entry = self._create_log_entry(
                        (
                            f"[QUEUE] Failed to start task {task.task_id}: {exc}; "
                            f"scheduled retry {task.spawn_attempts}/{self.max_spawn_retries}"
                        ),
                        "warning",
                    )
                    self._schedule_dispatch_retry_locked()
                else:
                    entry = self._create_log_entry(
                        (
                            f"[QUEUE] Failed to start task {task.task_id}: {exc}; "
                            f"retries exhausted ({task.spawn_attempts}/{self.max_spawn_retries})"
                        ),
                        "error",
                    )
                await self._push_log(entry)
                utils.log_event(
                    "crawler_manager.worker.spawn_failed",
                    level="warning" if retryable else "error",
                    task_id=task.task_id,
                    platform=task.config.platform.value,
                    crawler_type=task.config.crawler_type.value,
                    worker_id=worker.worker_id,
                    error=str(exc),
                    retryable=retryable,
                    spawn_attempts=task.spawn_attempts,
                    max_spawn_retries=self.max_spawn_retries,
                )
                if retryable:
                    break
                continue

            worker.process = process
            worker.task_id = task.task_id
            worker.config = task.config
            worker.started_at = datetime.now()
            self.current_config = task.config
            self.status = "running"

            safe_cmd_for_log = self._sanitize_command_for_log(cmd)
            entry = self._create_log_entry(
                f"[W{worker.worker_id}] Started task {task.task_id}: {safe_cmd_for_log}",
                "success",
            )
            await self._push_log(entry)
            utils.log_event(
                "crawler_manager.worker.started",
                task_id=task.task_id,
                platform=task.config.platform.value,
                crawler_type=task.config.crawler_type.value,
                worker_id=worker.worker_id,
            )

            if self._enable_output_reader:
                worker.read_task = asyncio.create_task(
                    self._read_output(worker.worker_id, process, task.task_id)
                )

        self._refresh_runtime_status_locked()

    async def _on_worker_exit(
        self,
        worker_id: int,
        process: subprocess.Popen,
        task_id: str,
        exit_code: int,
    ):
        async with self._lock:
            worker = self._workers[worker_id - 1]
            if worker.process is not process:
                return

            worker_config = worker.config
            worker.process = None
            worker.task_id = None
            worker.config = None
            worker.started_at = None
            worker.read_task = None

            if not self._stopping:
                if exit_code == 0:
                    entry = self._create_log_entry(
                        f"[W{worker_id}] Task {task_id} completed successfully",
                        "success",
                    )
                else:
                    entry = self._create_log_entry(
                        f"[W{worker_id}] Task {task_id} exited with code {exit_code}",
                        "warning",
                    )
                await self._push_log(entry)
                utils.log_event(
                    "crawler_manager.worker.exited",
                    level="warning" if exit_code != 0 else "info",
                    task_id=task_id,
                    worker_id=worker_id,
                    exit_code=exit_code,
                    platform=worker_config.platform.value if worker_config else "",
                    crawler_type=worker_config.crawler_type.value if worker_config else "",
                )
                await self._dispatch_pending_locked()

            self._refresh_runtime_status_locked()

    def _find_idle_worker_locked(self) -> Optional["_WorkerSlot"]:
        for worker in self._workers:
            if worker.process is None:
                return worker
            if worker.process.poll() is not None:
                worker.process = None
                worker.task_id = None
                worker.config = None
                worker.started_at = None
                if worker.read_task and worker.read_task.done():
                    worker.read_task = None
                return worker
        return None

    def _remove_pending_task_locked(self, task_id: str) -> None:
        self._pending_tasks = deque(
            task for task in self._pending_tasks if task.task_id != task_id
        )

    def _schedule_dispatch_retry_locked(self) -> None:
        if self._dispatch_retry_task and not self._dispatch_retry_task.done():
            return
        self._dispatch_retry_task = asyncio.create_task(self._retry_dispatch_after_delay())

    async def _retry_dispatch_after_delay(self) -> None:
        try:
            await asyncio.sleep(self._dispatch_retry_delay_sec)
            async with self._lock:
                if self._stopping:
                    return
                await self._dispatch_pending_locked()
        except asyncio.CancelledError:
            return

    def _refresh_runtime_status_locked(self):
        running_workers = self._running_workers_count_locked()
        pending_tasks = len(self._pending_tasks)

        if self._stopping:
            self.status = "stopping" if running_workers > 0 else "idle"
            return

        if running_workers > 0 or pending_tasks > 0:
            self.status = "running"
        elif self._last_error:
            self.status = "error"
        else:
            self.status = "idle"

        if self.status == "idle":
            self.started_at = None
            self.current_config = None
            return

        active_config = self._resolve_active_config_locked()
        if active_config is not None:
            self.current_config = active_config

    def _running_workers_count_locked(self) -> int:
        return sum(
            1
            for worker in self._workers
            if worker.process is not None and worker.process.poll() is None
        )

    def _resolve_active_config_locked(self) -> Optional[CrawlerStartRequest]:
        for worker in self._workers:
            if worker.process and worker.process.poll() is None and worker.config:
                return worker.config
        if self._pending_tasks:
            return self._pending_tasks[0].config
        return None

    def _compose_status_locked(self) -> dict:
        active_config = self._resolve_active_config_locked()
        running_task_ids = [
            worker.task_id
            for worker in self._workers
            if worker.process and worker.process.poll() is None and worker.task_id
        ]
        pending_task_ids = [task.task_id for task in self._pending_tasks]

        return {
            "status": self.status,
            "platform": active_config.platform.value if active_config else None,
            "crawler_type": active_config.crawler_type.value if active_config else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "error_message": self._last_error,
            "running_workers": len(running_task_ids),
            "total_workers": self.max_workers,
            "max_queue_size": self.max_queue_size,
            "queued_tasks": len(pending_task_ids),
            "active_task_ids": running_task_ids,
            "pending_task_ids": pending_task_ids,
        }

    def _compose_status_unlocked(self) -> dict:
        # Best effort snapshot; lockless for lightweight status reads.
        running_task_ids = [
            worker.task_id
            for worker in self._workers
            if worker.process and worker.process.poll() is None and worker.task_id
        ]
        pending_task_ids = [task.task_id for task in self._pending_tasks]
        active_config = self._resolve_active_config_locked()

        status = self.status
        if status != "stopping":
            if running_task_ids or pending_task_ids:
                status = "running"
            elif self._last_error:
                status = "error"
            else:
                status = "idle"

        return {
            "status": status,
            "platform": active_config.platform.value if active_config else None,
            "crawler_type": active_config.crawler_type.value if active_config else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "error_message": self._last_error,
            "running_workers": len(running_task_ids),
            "total_workers": self.max_workers,
            "max_queue_size": self.max_queue_size,
            "queued_tasks": len(pending_task_ids),
            "active_task_ids": running_task_ids,
            "pending_task_ids": pending_task_ids,
        }

    def _resolve_max_workers(self, max_workers: Optional[int]) -> int:
        if max_workers is not None:
            candidate = max_workers
        else:
            raw_value = os.getenv("CRAWLER_MAX_WORKERS", "2")
            try:
                candidate = int(raw_value)
            except ValueError:
                candidate = 2

        return max(1, min(candidate, 16))

    def _resolve_max_queue_size(self, max_queue_size: Optional[int]) -> int:
        if max_queue_size is not None:
            candidate = max_queue_size
        else:
            raw_value = os.getenv("CRAWLER_MAX_QUEUE_SIZE", "100")
            try:
                candidate = int(raw_value)
            except ValueError:
                candidate = 100

        return max(1, min(candidate, 10000))

    def _resolve_max_spawn_retries(self, max_spawn_retries: Optional[int]) -> int:
        if max_spawn_retries is not None:
            candidate = max_spawn_retries
        else:
            raw_value = os.getenv("CRAWLER_WORKER_SPAWN_MAX_RETRIES", "2")
            try:
                candidate = int(raw_value)
            except ValueError:
                candidate = 2
        return max(1, min(candidate, 10))

    def _resolve_dispatch_retry_delay(self) -> float:
        raw_value = os.getenv("CRAWLER_DISPATCH_RETRY_DELAY_SEC", "2")
        try:
            candidate = float(raw_value)
        except ValueError:
            candidate = 2.0
        return max(0.1, min(candidate, 60.0))

    def _resolve_log_buffer_capacity(self, log_buffer_capacity: Optional[int]) -> int:
        if log_buffer_capacity is not None:
            candidate = log_buffer_capacity
        else:
            raw_value = os.getenv("CRAWLER_LOG_BUFFER_CAPACITY", "2000")
            try:
                candidate = int(raw_value)
            except ValueError:
                candidate = 2000
        return max(1, min(candidate, 50000))

    def _next_task_id(self) -> str:
        self._task_seq += 1
        return f"task-{self._task_seq:06d}"

    def _build_worker_env(self, task: "_QueuedTask", worker_id: int) -> dict:
        prefix = os.getenv("ENERGY_BROWSER_ID_PREFIX", "energycrawler").strip() or "energycrawler"
        browser_id = (
            f"{prefix}_{task.config.platform.value}_w{worker_id}_{task.task_id}"
        )
        return {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "ENERGYCRAWLER_TASK_ID": task.task_id,
            "ENERGYCRAWLER_PLATFORM": task.config.platform.value,
            "ENERGYCRAWLER_CRAWLER_TYPE": task.config.crawler_type.value,
            "ENERGYCRAWLER_WORKER_ID": str(worker_id),
            "ENERGYCRAWLER_BROWSER_ID": browser_id,
        }


@dataclass
class _QueuedTask:
    task_id: str
    config: CrawlerStartRequest
    enqueued_at: datetime
    spawn_attempts: int = 0


@dataclass
class _WorkerSlot:
    worker_id: int
    process: Optional[subprocess.Popen] = None
    task_id: Optional[str] = None
    config: Optional[CrawlerStartRequest] = None
    started_at: Optional[datetime] = None
    read_task: Optional[asyncio.Task] = None


# Global singleton
crawler_manager = CrawlerManager()
