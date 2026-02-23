# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/api/schemas/crawler.py
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

from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class PlatformEnum(str, Enum):
    """Supported media platforms"""
    XHS = "xhs"
    X = "x"


class LoginTypeEnum(str, Enum):
    """Login method"""
    COOKIE = "cookie"


class CrawlerTypeEnum(str, Enum):
    """Crawler type"""
    SEARCH = "search"
    DETAIL = "detail"
    CREATOR = "creator"


class SaveDataOptionEnum(str, Enum):
    """Data save option"""
    CSV = "csv"
    DB = "db"
    JSON = "json"
    SQLITE = "sqlite"
    MONGODB = "mongodb"
    EXCEL = "excel"
    POSTGRES = "postgres"


class SafetyProfileEnum(str, Enum):
    """Safety profile presets for API-level rate limits."""
    SAFE = "safe"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class CrawlerStartRequest(BaseModel):
    """Crawler start request"""
    platform: PlatformEnum
    login_type: LoginTypeEnum = LoginTypeEnum.COOKIE
    crawler_type: CrawlerTypeEnum = CrawlerTypeEnum.SEARCH
    keywords: str = ""  # Keywords for search mode
    specified_ids: str = ""  # Post/video ID list for detail mode, comma-separated
    creator_ids: str = ""  # Creator ID list for creator mode, comma-separated
    start_page: int = 1
    enable_comments: bool = True
    enable_sub_comments: bool = False
    save_option: SaveDataOptionEnum = SaveDataOptionEnum.JSON
    cookies: str = ""
    headless: bool = False
    safety_profile: Optional[SafetyProfileEnum] = Field(
        default=None,
        description=(
            "Optional safety preset for default API throttling. "
            "When provided, crawler_manager fills missing max_notes_count/crawl_sleep_sec "
            "from profile defaults."
        ),
    )
    max_notes_count: Optional[int] = Field(default=None, ge=1, le=200)
    crawl_sleep_sec: Optional[float] = Field(default=None, ge=0.1, le=120.0)


class CrawlerStatusResponse(BaseModel):
    """Crawler status response"""
    status: Literal["idle", "running", "stopping", "error"]
    platform: Optional[str] = None
    crawler_type: Optional[str] = None
    started_at: Optional[str] = None
    error_message: Optional[str] = None
    running_workers: int = 0
    total_workers: int = 1
    max_queue_size: int = 100
    queued_tasks: int = 0
    active_task_ids: List[str] = Field(default_factory=list)
    pending_task_ids: List[str] = Field(default_factory=list)


class CrawlerStartResponse(BaseModel):
    """Crawler start response"""
    status: Literal["ok"]
    message: str
    task_id: str
    queued_tasks: int
    running_workers: int


class LogEntry(BaseModel):
    """Log entry"""
    id: int
    timestamp: str
    level: Literal["info", "warning", "error", "success", "debug"]
    message: str


class DataFileInfo(BaseModel):
    """Data file information"""
    name: str
    path: str
    size: int
    modified_at: str
    record_count: Optional[int] = None
