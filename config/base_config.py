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
# Whether to enable IP proxy
ENABLE_IP_PROXY = _getenv_bool("ENABLE_IP_PROXY", False)

# Number of proxy IP pools
IP_PROXY_POOL_COUNT = _getenv_int("IP_PROXY_POOL_COUNT", 2)

# Proxy IP provider name
IP_PROXY_PROVIDER_NAME = os.getenv("IP_PROXY_PROVIDER_NAME", "kuaidaili").strip() or "kuaidaili"
# kuaidaili | wandouhttp

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

# word cloud related
# Whether to enable generating comment word clouds
ENABLE_GET_WORDCLOUD = _getenv_bool("ENABLE_GET_WORDCLOUD", False)
# Custom words and their groups
# Add rule: xx:yy where xx is a custom-added phrase, and yy is the group name to which the phrase xx is assigned.
CUSTOM_WORDS = {
    "零几": "年份",  # Recognize "zero points" as a whole
    "高频词": "专业术语",  # Example custom words
}

# Deactivate (disabled) word file path
STOP_WORDS_FILE = "./docs/hit_stopwords.txt"

# Chinese font file path
FONT_PATH = "./docs/STZHONGS.TTF"

# Crawl interval
CRAWLER_MAX_SLEEP_SEC = _getenv_float("CRAWLER_MAX_SLEEP_SEC", 10)

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

from .xhs_config import *
