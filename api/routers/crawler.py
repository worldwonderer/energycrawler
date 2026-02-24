# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/api/routers/crawler.py
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

import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..response import success_response
from ..schemas import CrawlerStartRequest
from ..services import crawler_manager, scheduler_service

router = APIRouter(prefix="/crawler", tags=["crawler"])
_TASK_ID_PATTERN = re.compile(r"\btask-[a-zA-Z0-9_-]+\b")


def _extract_task_id(message: str) -> Optional[str]:
    match = _TASK_ID_PATTERN.search(message or "")
    return match.group(0) if match else None


def _parse_levels(raw_level: Optional[str]) -> set[str]:
    if not raw_level:
        return set()
    return {
        chunk.strip().lower()
        for chunk in str(raw_level).split(",")
        if chunk and chunk.strip()
    }


async def _build_task_to_run_map(task_ids: set[str]) -> dict[str, int]:
    if not task_ids:
        return {}

    try:
        # list_runs returns latest-first; keep first match per task_id.
        runs = await scheduler_service.list_runs(job_id=None, limit=500)
    except Exception:
        return {}

    mapping: dict[str, int] = {}
    for run in runs:
        candidate_task_id = str(run.get("task_id") or "").strip()
        candidate_run_id = run.get("run_id")
        if (
            candidate_task_id
            and candidate_task_id in task_ids
            and candidate_task_id not in mapping
            and isinstance(candidate_run_id, int)
        ):
            mapping[candidate_task_id] = candidate_run_id
    return mapping


async def _enrich_logs_with_context(logs: list[dict]) -> list[dict]:
    task_ids = {
        task_id
        for task_id in (_extract_task_id(str(log.get("message", ""))) for log in logs)
        if task_id
    }
    task_to_run_id = await _build_task_to_run_map(task_ids)

    enriched: list[dict] = []
    for log in logs:
        item = dict(log)
        task_id = _extract_task_id(str(item.get("message", "")))
        if task_id:
            item["task_id"] = task_id
            run_id = task_to_run_id.get(task_id)
            if run_id is not None:
                item["run_id"] = run_id
        enriched.append(item)
    return enriched


@router.post("/start")
async def start_crawler(request: CrawlerStartRequest):
    """Enqueue crawler task"""
    result = await crawler_manager.start(request)
    if not result.get("accepted"):
        error = result.get("error", "Failed to enqueue crawler task")
        error_lower = str(error).lower()
        if "queue is full" in error_lower:
            raise HTTPException(status_code=429, detail=error)
        if "stopping" in error_lower:
            raise HTTPException(status_code=409, detail=error)
        raise HTTPException(status_code=400, detail=error)

    return success_response({
        "status": "ok",
        "task_id": result["task_id"],
        "queued_tasks": result["queued_tasks"],
        "running_workers": result["running_workers"],
    }, message="Crawler task accepted")


@router.post("/stop")
async def stop_crawler():
    """Stop all running crawler tasks and clear queue"""
    success = await crawler_manager.stop()
    if not success:
        raise HTTPException(status_code=400, detail="No crawler task is running")

    return success_response({"status": "ok"}, message="Crawler cluster stopped successfully")


@router.get("/status")
async def get_crawler_status():
    """Get crawler cluster status"""
    return success_response(crawler_manager.get_status(), message="Crawler cluster status")


@router.get("/logs")
async def get_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    task_id: Optional[str] = None,
    run_id: Optional[int] = Query(default=None, ge=1),
    level: Optional[str] = Query(default=None, description="Comma-separated log levels, e.g. warning,error"),
):
    """Get recent logs"""
    logs = crawler_manager.logs[-limit:]
    raw_items = [log.model_dump() for log in logs]
    enriched_items = await _enrich_logs_with_context(raw_items)
    level_filters = _parse_levels(level)

    if task_id:
        enriched_items = [item for item in enriched_items if item.get("task_id") == task_id]
    if run_id is not None:
        enriched_items = [item for item in enriched_items if item.get("run_id") == run_id]
    if level_filters:
        enriched_items = [
            item
            for item in enriched_items
            if str(item.get("level", "")).strip().lower() in level_filters
        ]

    return success_response({"logs": enriched_items}, message="Crawler logs")


@router.get("/cluster")
async def get_cluster_status():
    """Get detailed cluster runtime snapshot"""
    return success_response(crawler_manager.get_cluster_status(), message="Crawler cluster snapshot")
