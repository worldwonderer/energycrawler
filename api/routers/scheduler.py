# -*- coding: utf-8 -*-
"""Scheduler APIs for periodic keyword/KOL crawl jobs."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from ..response import ApiError, success_response
from ..schemas.scheduler import (
    SchedulerJobCloneRequest,
    SchedulerJobCreateRequest,
    SchedulerJobPatchRequest,
    SchedulerJobsBatchEnableRequest,
)
from ..services import scheduler_service


router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def _raise_http_from_api_error(exc: ApiError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    ) from exc


@router.post("/jobs")
async def create_job(request: SchedulerJobCreateRequest):
    try:
        job = await scheduler_service.create_job(request)
        return success_response(job, message="Scheduler job created")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ApiError as exc:
        _raise_http_from_api_error(exc)


@router.get("/jobs")
async def list_jobs():
    jobs = await scheduler_service.list_jobs()
    return success_response({"jobs": jobs}, message="Scheduler jobs")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    try:
        job = await scheduler_service.get_job(job_id)
        return success_response(job, message="Scheduler job")
    except ApiError as exc:
        _raise_http_from_api_error(exc)


@router.patch("/jobs/{job_id}")
async def patch_job(job_id: str, request: SchedulerJobPatchRequest):
    try:
        job = await scheduler_service.update_job(job_id, request)
        return success_response(job, message="Scheduler job updated")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ApiError as exc:
        _raise_http_from_api_error(exc)


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    deleted = await scheduler_service.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scheduler job not found")
    return success_response({"deleted": True, "job_id": job_id}, message="Scheduler job deleted")


@router.post("/jobs/{job_id}/run-now")
async def run_now(job_id: str):
    try:
        result = await scheduler_service.run_now(job_id)
        return success_response(result, message="Scheduler job triggered")
    except ApiError as exc:
        _raise_http_from_api_error(exc)


@router.post("/jobs/{job_id}/clone")
async def clone_job(job_id: str, request: Optional[SchedulerJobCloneRequest] = None):
    try:
        cloned = await scheduler_service.clone_job(job_id, name=(request.name if request else None))
        return success_response(cloned, message="Scheduler job cloned")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ApiError as exc:
        _raise_http_from_api_error(exc)


@router.post("/jobs/batch-enable")
async def batch_enable_jobs(request: SchedulerJobsBatchEnableRequest):
    try:
        result = await scheduler_service.batch_set_enabled(job_ids=request.job_ids, enabled=request.enabled)
        return success_response(result, message="Scheduler jobs updated")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ApiError as exc:
        _raise_http_from_api_error(exc)


@router.get("/runs/{run_id}")
async def get_run(run_id: int):
    try:
        run = await scheduler_service.get_run(run_id)
        return success_response(run, message="Scheduler run")
    except ApiError as exc:
        _raise_http_from_api_error(exc)


@router.get("/runs")
async def list_runs(
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    platform: Optional[str] = None,
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=500),
):
    try:
        runs = await scheduler_service.list_runs(
            job_id=job_id,
            status=status,
            platform=platform,
            triggered_from=from_,
            triggered_to=to,
            limit=limit,
        )
        return success_response({"runs": runs}, message="Scheduler runs")
    except ApiError as exc:
        _raise_http_from_api_error(exc)


@router.get("/status")
async def scheduler_status():
    return success_response(scheduler_service.get_status(), message="Scheduler status")
