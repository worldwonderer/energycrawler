# -*- coding: utf-8 -*-
"""Schemas for scheduler jobs and runs."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .crawler import (
    LoginTypeEnum,
    PlatformEnum,
    SaveDataOptionEnum,
    SafetyProfileEnum,
)


class SchedulerJobTypeEnum(str, Enum):
    """Supported scheduler job types."""

    KEYWORD = "keyword"
    KOL = "kol"


class SchedulerKeywordPayload(BaseModel):
    """Payload for keyword (search) scheduler jobs."""

    keywords: str = Field(min_length=1)
    login_type: LoginTypeEnum = LoginTypeEnum.COOKIE
    save_option: SaveDataOptionEnum = SaveDataOptionEnum.JSON
    headless: bool = False
    start_page: int = Field(default=1, ge=1)
    enable_comments: bool = True
    enable_sub_comments: bool = False
    cookies: str = ""
    safety_profile: Optional[SafetyProfileEnum] = None
    max_notes_count: Optional[int] = Field(default=None, ge=1, le=200)
    crawl_sleep_sec: Optional[float] = Field(default=None, ge=0.1, le=120.0)


class SchedulerKolPayload(BaseModel):
    """Payload for KOL (creator) scheduler jobs."""

    creator_ids: str = Field(min_length=1)
    login_type: LoginTypeEnum = LoginTypeEnum.COOKIE
    save_option: SaveDataOptionEnum = SaveDataOptionEnum.JSON
    headless: bool = False
    start_page: int = Field(default=1, ge=1)
    enable_comments: bool = True
    enable_sub_comments: bool = False
    cookies: str = ""
    safety_profile: Optional[SafetyProfileEnum] = None
    max_notes_count: Optional[int] = Field(default=None, ge=1, le=200)
    crawl_sleep_sec: Optional[float] = Field(default=None, ge=0.1, le=120.0)


class SchedulerJobCreateRequest(BaseModel):
    """Create scheduler job request."""

    name: str = Field(min_length=1, max_length=120)
    job_type: SchedulerJobTypeEnum
    platform: PlatformEnum
    interval_minutes: int = Field(ge=5, le=7 * 24 * 60)
    enabled: bool = True
    payload: dict[str, Any]


class SchedulerJobPatchRequest(BaseModel):
    """Update scheduler job request."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    interval_minutes: Optional[int] = Field(default=None, ge=5, le=7 * 24 * 60)
    enabled: Optional[bool] = None
    payload: Optional[dict[str, Any]] = None


class SchedulerJobCloneRequest(BaseModel):
    """Clone scheduler job request."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)


class SchedulerJobsBatchEnableRequest(BaseModel):
    """Batch enable/disable scheduler jobs request."""

    job_ids: list[str] = Field(min_length=1)
    enabled: bool


class SchedulerRunNowResponse(BaseModel):
    """Run-now response payload."""

    accepted: bool
    task_id: Optional[str] = None
    message: str
    run_id: int
