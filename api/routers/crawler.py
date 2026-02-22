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

from fastapi import APIRouter, HTTPException

from ..schemas import CrawlerStartRequest, CrawlerStartResponse, CrawlerStatusResponse
from ..services import crawler_manager

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.post("/start", response_model=CrawlerStartResponse)
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

    return {
        "status": "ok",
        "message": "Crawler task accepted",
        "task_id": result["task_id"],
        "queued_tasks": result["queued_tasks"],
        "running_workers": result["running_workers"],
    }


@router.post("/stop")
async def stop_crawler():
    """Stop all running crawler tasks and clear queue"""
    success = await crawler_manager.stop()
    if not success:
        raise HTTPException(status_code=400, detail="No crawler task is running")

    return {"status": "ok", "message": "Crawler cluster stopped successfully"}


@router.get("/status", response_model=CrawlerStatusResponse)
async def get_crawler_status():
    """Get crawler cluster status"""
    return crawler_manager.get_status()


@router.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    logs = crawler_manager.logs[-limit:] if limit > 0 else crawler_manager.logs
    return {"logs": [log.model_dump() for log in logs]}


@router.get("/cluster")
async def get_cluster_status():
    """Get detailed cluster runtime snapshot"""
    return crawler_manager.get_cluster_status()
