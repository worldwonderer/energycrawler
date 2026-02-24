# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/config/base_config.py
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

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - fallback when dotenv is unavailable
    load_dotenv = None


def _load_project_env() -> None:
    """Load .env from project root if python-dotenv is available."""
    if load_dotenv is None:
        return
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env", override=False)


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookie_dict: dict[str, str] = {}
    for item in cookie_header.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            cookie_dict[key] = value
    return cookie_dict


def _getenv_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _getenv_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _getenv_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


_load_project_env()

# Basic configuration
PLATFORM = os.getenv("PLATFORM", "xhs").strip() or "xhs"  # Platform, xhs | x
KEYWORDS = os.getenv("KEYWORDS", "编程副业,编程兼职").strip() or "编程副业,编程兼职"
LOGIN_TYPE = os.getenv("LOGIN_TYPE", "cookie").strip() or "cookie"  # cookie only
COOKIES = os.getenv("COOKIES", "").strip()
CRAWLER_TYPE = os.getenv("CRAWLER_TYPE", "search").strip() or "search"
# Crawling type: search (keyword search) | detail (post details) | creator (creator homepage data)
# Setting to True will not open the browser (headless browser)
# Setting False will open a browser
# If Xiaohongshu keeps scanning the code to log in but fails, open the browser and manually pass the sliding verification code.
HEADLESS = _getenv_bool("HEADLESS", False)

# Whether to save login status
SAVE_LOGIN_STATE = _getenv_bool("SAVE_LOGIN_STATE", True)

# ==================== Energy Browser Configuration ====================
# Whether to enable Energy browser mode - use Energy gRPC service for browser automation
# When enabled, signature generation will use the Energy browser service instead of legacy browser drivers
# This provides a centralized browser service that can be shared across multiple crawler instances
ENABLE_ENERGY_BROWSER = _getenv_bool("ENABLE_ENERGY_BROWSER", True)

# Energy service address (host:port)
ENERGY_SERVICE_ADDRESS = os.getenv("ENERGY_SERVICE_ADDRESS", "localhost:50051").strip() or "localhost:50051"

# Whether to run Energy browser in headless mode
ENERGY_HEADLESS = _getenv_bool("ENERGY_HEADLESS", True)

# Browser instance ID prefix for Energy service (will be appended with platform name)
ENERGY_BROWSER_ID_PREFIX = os.getenv("ENERGY_BROWSER_ID_PREFIX", "energycrawler").strip() or "energycrawler"


def resolve_energy_browser_id(platform: str | None = None) -> str:
    """
    Resolve Energy browser ID for current runtime.

    Priority:
    1) `ENERGYCRAWLER_BROWSER_ID` (worker/task-scoped override from cluster manager)
    2) `{ENERGY_BROWSER_ID_PREFIX}_{platform}`
    """

    runtime_override = os.getenv("ENERGYCRAWLER_BROWSER_ID", "").strip()
    if runtime_override:
        return runtime_override

    normalized_platform = (platform or PLATFORM or "xhs").strip() or "xhs"
    return f"{ENERGY_BROWSER_ID_PREFIX}_{normalized_platform}"


# Runtime browser ID used by crawler processes.
ENERGY_BROWSER_ID = resolve_energy_browser_id(PLATFORM)

# ==================== Per-Platform Energy Configuration ====================
# These settings allow fine-grained control over which supported platforms use Energy browser.
XHS_ENABLE_ENERGY = ENABLE_ENERGY_BROWSER
TWITTER_ENABLE_ENERGY = ENABLE_ENERGY_BROWSER

# Data saving type option configuration, supports six types: csv, db, json, sqlite, excel, postgres. It is best to save to DB, with deduplication function.
SAVE_DATA_OPTION = os.getenv("SAVE_DATA_OPTION", "json").strip() or "json"
# csv or db or json or sqlite or excel or postgres

# Data saving path, if not specified by default, it will be saved to the data folder.
SAVE_DATA_PATH = os.getenv("SAVE_DATA_PATH", "").strip()

# Browser file configuration cached by the user's browser
USER_DATA_DIR = "%s_user_data_dir"  # %s will be replaced by platform name

# The number of pages to start crawling starts from the first page by default
START_PAGE = _getenv_int("START_PAGE", 1)

# Control the number of crawled videos/posts
CRAWLER_MAX_NOTES_COUNT = _getenv_int("CRAWLER_MAX_NOTES_COUNT", 5)

# Controlling the number of concurrent crawlers
MAX_CONCURRENCY_NUM = _getenv_int("MAX_CONCURRENCY_NUM", 1)

# Whether to enable crawling media mode (including image or video resources), crawling media is not enabled by default
ENABLE_GET_MEIDAS = _getenv_bool("ENABLE_GET_MEIDAS", False)

# Whether to enable comment crawling mode. Comment crawling is enabled by default.
ENABLE_GET_COMMENTS = _getenv_bool("ENABLE_GET_COMMENTS", True)

# Control the number of crawled first-level comments (single video/post)
CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = _getenv_int("CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES", 3)

# Whether to enable the mode of crawling second-level comments. By default, crawling of second-level comments is not enabled.
# If the old version of the project uses db, you need to refer to schema/tables.sql line 287 to add table fields.
ENABLE_GET_SUB_COMMENTS = _getenv_bool("ENABLE_GET_SUB_COMMENTS", False)

# Crawl interval
CRAWLER_MAX_SLEEP_SEC = _getenv_float("CRAWLER_MAX_SLEEP_SEC", 10)

# ==================== Incremental Crawl / Resume ====================
# Enable incremental crawling (fetch newly added content only where supported).
ENABLE_INCREMENTAL_CRAWL = _getenv_bool("ENABLE_INCREMENTAL_CRAWL", False)

# Resume from last checkpoint after interruption.
RESUME_FROM_CHECKPOINT = _getenv_bool("RESUME_FROM_CHECKPOINT", True)

# Optional custom checkpoint file path.
CRAWLER_CHECKPOINT_PATH = os.getenv("CRAWLER_CHECKPOINT_PATH", "").strip()

# ==================== CookieCloud Sync ====================
# Pull latest cookies from CookieCloud before crawl starts.
COOKIECLOUD_ENABLED = _getenv_bool("COOKIECLOUD_ENABLED", False)

# Force overwrite local COOKIES even when COOKIES is already configured.
COOKIECLOUD_FORCE_SYNC = _getenv_bool("COOKIECLOUD_FORCE_SYNC", False)

# CookieCloud server settings.
COOKIECLOUD_SERVER = os.getenv("COOKIECLOUD_SERVER", "").strip()
COOKIECLOUD_UUID = os.getenv("COOKIECLOUD_UUID", "").strip()
COOKIECLOUD_PASSWORD = os.getenv("COOKIECLOUD_PASSWORD", "").strip()
COOKIECLOUD_TIMEOUT_SEC = _getenv_float("COOKIECLOUD_TIMEOUT_SEC", 10.0)

# ==================== Auth Watchdog ====================
# Auto-recover login state on auth failure (e.g. expired cookies).
AUTH_WATCHDOG_ENABLED = _getenv_bool("AUTH_WATCHDOG_ENABLED", True)
AUTH_WATCHDOG_MAX_RETRIES = max(0, _getenv_int("AUTH_WATCHDOG_MAX_RETRIES", 1))
AUTH_WATCHDOG_RETRY_INTERVAL_SEC = max(0.0, _getenv_float("AUTH_WATCHDOG_RETRY_INTERVAL_SEC", 2.0))
# When recovery runs, force CookieCloud refresh even if local cookie is already present.
AUTH_WATCHDOG_FORCE_COOKIECLOUD_SYNC = _getenv_bool("AUTH_WATCHDOG_FORCE_COOKIECLOUD_SYNC", True)
# Runtime auth recovery budget when API returns auth errors (e.g. 401).
AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES = max(0, _getenv_int("AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES", 1))

# ==================== Safety Controls ====================
# Hard safety ceilings to reduce account risk for small-batch crawling.
CRAWLER_HARD_MAX_NOTES_COUNT = int(os.getenv("CRAWLER_HARD_MAX_NOTES_COUNT", "20"))
CRAWLER_HARD_MAX_CONCURRENCY = int(os.getenv("CRAWLER_HARD_MAX_CONCURRENCY", "2"))
CRAWLER_MIN_SLEEP_SEC = float(os.getenv("CRAWLER_MIN_SLEEP_SEC", "6"))
CRAWLER_SLEEP_JITTER_SEC = float(os.getenv("CRAWLER_SLEEP_JITTER_SEC", "1.2"))
CRAWLER_RETRY_BASE_DELAY_SEC = float(os.getenv("CRAWLER_RETRY_BASE_DELAY_SEC", "2"))
CRAWLER_RETRY_MAX_DELAY_SEC = float(os.getenv("CRAWLER_RETRY_MAX_DELAY_SEC", "30"))

# ==================== XHS Signature Runtime Controls ====================
XHS_SIGNATURE_CANARY_ENABLED = os.getenv("XHS_SIGNATURE_CANARY_ENABLED", "false").lower() == "true"
XHS_SIGNATURE_CANARY_TIMEOUT_SEC = float(os.getenv("XHS_SIGNATURE_CANARY_TIMEOUT_SEC", "8"))
XHS_SIGNATURE_CANARY_BASELINE_PATH = os.getenv("XHS_SIGNATURE_CANARY_BASELINE_PATH", "").strip()
XHS_SIGNATURE_SESSION_TTL_SEC = int(os.getenv("XHS_SIGNATURE_SESSION_TTL_SEC", "1800"))
XHS_SIGNATURE_FAILURE_THRESHOLD = int(os.getenv("XHS_SIGNATURE_FAILURE_THRESHOLD", "3"))

# =================================== Twitter/X.com Configuration ===================================

# Twitter auth_token cookie (required for crawling)
# Priority: TWITTER_AUTH_TOKEN > TWITTER_COOKIE(auth_token=...)
TWITTER_COOKIE = os.getenv("TWITTER_COOKIE", "").strip()
_twitter_cookie_dict = _parse_cookie_header(TWITTER_COOKIE)
_twitter_auth_token = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
if not _twitter_auth_token:
    _twitter_auth_token = _twitter_cookie_dict.get("auth_token", "").strip()
TWITTER_AUTH_TOKEN = _twitter_auth_token

# Twitter ct0 cookie (required for API auth)
# Priority: TWITTER_CT0 > TWITTER_COOKIE(ct0=...)
_twitter_ct0 = os.getenv("TWITTER_CT0", "").strip()
if not _twitter_ct0:
    _twitter_ct0 = _twitter_cookie_dict.get("ct0", "").strip()
TWITTER_CT0 = _twitter_ct0

# Headless mode for browser
TWITTER_HEADLESS = os.getenv("TWITTER_HEADLESS", "true").lower() == "true"

# Twitter user IDs to crawl (for USER_TWEETS mode)
TWITTER_USER_IDS = os.getenv("TWITTER_USER_IDS", "").split(",") if os.getenv("TWITTER_USER_IDS") else []

# Twitter tweet IDs to get details (for TWEET_DETAIL mode)
TWITTER_TWEET_IDS = os.getenv("TWITTER_TWEET_IDS", "").split(",") if os.getenv("TWITTER_TWEET_IDS") else []

# Twitter search type: "Latest", "Top"
TWITTER_SEARCH_TYPE = os.getenv("TWITTER_SEARCH_TYPE", "Latest")

# ==================== Config Layering Metadata ====================
# Purpose:
# - minimal: onboarding required fields (<= 6)
# - core: commonly tuned runtime controls
# - advanced: diagnostics / performance / rarely needed knobs
CONFIG_LAYER_ORDER = ("minimal", "core", "advanced")
CONFIG_LAYER_DEFAULT = "minimal"

CONFIG_LAYER_ENV_KEYS: dict[str, list[str]] = {
    "minimal": [
        "PLATFORM",
        "CRAWLER_TYPE",
        "KEYWORDS",
        "SAVE_DATA_OPTION",
        "ENERGY_SERVICE_ADDRESS",
        "COOKIES",
    ],
    "core": [
        "LOGIN_TYPE",
        "HEADLESS",
        "START_PAGE",
        "SAVE_DATA_PATH",
        "ENABLE_ENERGY_BROWSER",
        "ENERGY_HEADLESS",
        "ENERGY_BROWSER_ID_PREFIX",
        "CRAWLER_MAX_NOTES_COUNT",
        "MAX_CONCURRENCY_NUM",
        "CRAWLER_MAX_SLEEP_SEC",
        "ENABLE_GET_COMMENTS",
        "ENABLE_GET_SUB_COMMENTS",
        "ENABLE_GET_MEIDAS",
        "ENABLE_INCREMENTAL_CRAWL",
        "RESUME_FROM_CHECKPOINT",
        "TWITTER_AUTH_TOKEN",
        "TWITTER_CT0",
    ],
    "advanced": [
        "TWITTER_COOKIE",
        "COOKIECLOUD_ENABLED",
        "COOKIECLOUD_FORCE_SYNC",
        "COOKIECLOUD_SERVER",
        "COOKIECLOUD_UUID",
        "COOKIECLOUD_PASSWORD",
        "COOKIECLOUD_TIMEOUT_SEC",
        "AUTH_WATCHDOG_ENABLED",
        "AUTH_WATCHDOG_MAX_RETRIES",
        "AUTH_WATCHDOG_RETRY_INTERVAL_SEC",
        "AUTH_WATCHDOG_FORCE_COOKIECLOUD_SYNC",
        "AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES",
        "CRAWLER_HARD_MAX_NOTES_COUNT",
        "CRAWLER_HARD_MAX_CONCURRENCY",
        "CRAWLER_MIN_SLEEP_SEC",
        "CRAWLER_SLEEP_JITTER_SEC",
        "CRAWLER_RETRY_BASE_DELAY_SEC",
        "CRAWLER_RETRY_MAX_DELAY_SEC",
        "XHS_SIGNATURE_CANARY_ENABLED",
        "XHS_SIGNATURE_CANARY_TIMEOUT_SEC",
        "XHS_SIGNATURE_CANARY_BASELINE_PATH",
        "XHS_SIGNATURE_SESSION_TTL_SEC",
        "XHS_SIGNATURE_FAILURE_THRESHOLD",
    ],
}

CONFIG_SENSITIVE_KEYS = {
    "COOKIES",
    "TWITTER_COOKIE",
    "TWITTER_AUTH_TOKEN",
    "TWITTER_CT0",
    "COOKIECLOUD_PASSWORD",
    "COOKIECLOUD_UUID",
}

CONFIG_FIELD_METADATA: dict[str, dict[str, str]] = {
    "PLATFORM": {"label": "Platform", "description": "目标平台（xhs/x）"},
    "CRAWLER_TYPE": {"label": "Crawler Type", "description": "抓取模式（search/detail/creator）"},
    "KEYWORDS": {"label": "Keywords", "description": "关键词（search 模式）"},
    "SAVE_DATA_OPTION": {"label": "Save Option", "description": "结果存储格式"},
    "ENERGY_SERVICE_ADDRESS": {"label": "Energy Address", "description": "Energy 服务地址（host:port）"},
    "COOKIES": {"label": "XHS Cookies", "description": "小红书 Cookie（含 a1）"},
    "LOGIN_TYPE": {"label": "Login Type", "description": "登录方式（默认 cookie）"},
    "HEADLESS": {"label": "Headless", "description": "是否无头运行"},
    "START_PAGE": {"label": "Start Page", "description": "起始页码"},
    "SAVE_DATA_PATH": {"label": "Save Path", "description": "数据导出目录"},
    "ENABLE_ENERGY_BROWSER": {"label": "Energy Enabled", "description": "启用 Energy 浏览器模式"},
    "ENERGY_HEADLESS": {"label": "Energy Headless", "description": "Energy 浏览器无头模式"},
    "ENERGY_BROWSER_ID_PREFIX": {"label": "Browser ID Prefix", "description": "Energy 浏览器实例前缀"},
    "CRAWLER_MAX_NOTES_COUNT": {"label": "Max Notes", "description": "单次最大抓取数量"},
    "MAX_CONCURRENCY_NUM": {"label": "Concurrency", "description": "并发 worker 数"},
    "CRAWLER_MAX_SLEEP_SEC": {"label": "Sleep Seconds", "description": "请求间隔上限（秒）"},
    "ENABLE_GET_COMMENTS": {"label": "Comments", "description": "抓取一级评论"},
    "ENABLE_GET_SUB_COMMENTS": {"label": "Sub Comments", "description": "抓取二级评论"},
    "ENABLE_GET_MEIDAS": {"label": "Media", "description": "抓取图片/视频资源"},
    "ENABLE_INCREMENTAL_CRAWL": {"label": "Incremental", "description": "增量抓取模式"},
    "RESUME_FROM_CHECKPOINT": {"label": "Resume", "description": "从断点继续"},
    "TWITTER_AUTH_TOKEN": {"label": "Twitter auth_token", "description": "X/Twitter auth_token"},
    "TWITTER_CT0": {"label": "Twitter ct0", "description": "X/Twitter ct0"},
    "TWITTER_COOKIE": {"label": "Twitter Cookie", "description": "X/Twitter cookie header"},
    "COOKIECLOUD_ENABLED": {"label": "CookieCloud", "description": "启用 CookieCloud 同步"},
    "COOKIECLOUD_FORCE_SYNC": {"label": "Force Sync", "description": "强制覆盖本地 Cookie"},
    "COOKIECLOUD_SERVER": {"label": "CookieCloud Server", "description": "CookieCloud 服务地址"},
    "COOKIECLOUD_UUID": {"label": "CookieCloud UUID", "description": "CookieCloud UUID"},
    "COOKIECLOUD_PASSWORD": {"label": "CookieCloud Password", "description": "CookieCloud 密钥"},
    "COOKIECLOUD_TIMEOUT_SEC": {"label": "CookieCloud Timeout", "description": "CookieCloud 超时（秒）"},
    "AUTH_WATCHDOG_ENABLED": {"label": "Auth Watchdog", "description": "认证失败自动恢复"},
    "AUTH_WATCHDOG_MAX_RETRIES": {"label": "Watchdog Retries", "description": "认证恢复重试次数"},
    "AUTH_WATCHDOG_RETRY_INTERVAL_SEC": {"label": "Retry Interval", "description": "认证恢复重试间隔"},
    "AUTH_WATCHDOG_FORCE_COOKIECLOUD_SYNC": {
        "label": "Force CookieCloud Sync",
        "description": "恢复时强制刷新 CookieCloud",
    },
    "AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES": {
        "label": "Runtime Recoveries",
        "description": "运行期最大自动恢复次数",
    },
    "CRAWLER_HARD_MAX_NOTES_COUNT": {"label": "Hard Max Notes", "description": "抓取硬上限（数量）"},
    "CRAWLER_HARD_MAX_CONCURRENCY": {"label": "Hard Concurrency", "description": "并发硬上限"},
    "CRAWLER_MIN_SLEEP_SEC": {"label": "Min Sleep", "description": "请求最小间隔"},
    "CRAWLER_SLEEP_JITTER_SEC": {"label": "Sleep Jitter", "description": "请求间隔随机抖动"},
    "CRAWLER_RETRY_BASE_DELAY_SEC": {"label": "Retry Base Delay", "description": "重试基础延迟"},
    "CRAWLER_RETRY_MAX_DELAY_SEC": {"label": "Retry Max Delay", "description": "重试最大延迟"},
    "XHS_SIGNATURE_CANARY_ENABLED": {"label": "Signature Canary", "description": "签名链路 canary 开关"},
    "XHS_SIGNATURE_CANARY_TIMEOUT_SEC": {"label": "Canary Timeout", "description": "签名 canary 超时"},
    "XHS_SIGNATURE_CANARY_BASELINE_PATH": {"label": "Canary Baseline", "description": "签名基准文件路径"},
    "XHS_SIGNATURE_SESSION_TTL_SEC": {"label": "Signature TTL", "description": "签名会话 TTL"},
    "XHS_SIGNATURE_FAILURE_THRESHOLD": {"label": "Failure Threshold", "description": "签名失败阈值"},
}


def get_config_layer_env_keys(mode: str, *, cumulative: bool = True) -> list[str]:
    normalized = (mode or CONFIG_LAYER_DEFAULT).strip().lower()
    if normalized == "all":
        normalized = "advanced"
    if normalized not in CONFIG_LAYER_ENV_KEYS:
        raise ValueError(f"Unsupported config layer: {mode}")

    if not cumulative:
        return list(CONFIG_LAYER_ENV_KEYS[normalized])

    keys: list[str] = []
    seen: set[str] = set()
    target_index = CONFIG_LAYER_ORDER.index(normalized)
    for index, layer in enumerate(CONFIG_LAYER_ORDER):
        if index > target_index:
            break
        for key in CONFIG_LAYER_ENV_KEYS.get(layer, []):
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def get_config_field_metadata(key: str) -> dict[str, object]:
    layer = "advanced"
    for candidate in CONFIG_LAYER_ORDER:
        if key in CONFIG_LAYER_ENV_KEYS.get(candidate, []):
            layer = candidate
            break
    base = CONFIG_FIELD_METADATA.get(key, {})
    return {
        "key": key,
        "layer": layer,
        "label": base.get("label", key),
        "description": base.get("description", ""),
        "sensitive": key in CONFIG_SENSITIVE_KEYS,
    }


from .xhs_config import *
