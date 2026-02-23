# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/main.py
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

import sys
import io
import os

# Force UTF-8 encoding for stdout/stderr to prevent encoding errors
# when outputting Chinese characters in non-UTF-8 terminals
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import asyncio
from typing import Optional, Type

import cmd_arg
import config
from database import db
from base.base_crawler import AbstractCrawler
from tools import utils
from tools.cookiecloud_sync import sync_cookiecloud_login_state
from tools.preflight import ensure_energy_service_or_raise
from tools.safety import enforce_runtime_safety


class CrawlerFactory:
    CRAWLER_IMPORTS: dict[str, tuple[str, str]] = {
        "xhs": ("media_platform.xhs", "XiaoHongShuCrawler"),
        "x": ("media_platform.twitter", "TwitterCrawler"),
        "twitter": ("media_platform.twitter", "TwitterCrawler"),
    }

    @staticmethod
    def create_crawler(platform: str) -> AbstractCrawler:
        import_path = CrawlerFactory.CRAWLER_IMPORTS.get(platform)
        if not import_path:
            supported = ", ".join(sorted(CrawlerFactory.CRAWLER_IMPORTS))
            raise ValueError(f"Invalid media platform: {platform!r}. Supported: {supported}")
        module_name, class_name = import_path
        module = __import__(module_name, fromlist=[class_name])
        crawler_class: Type[AbstractCrawler] = getattr(module, class_name)
        return crawler_class()


crawler: Optional[AbstractCrawler] = None


def _is_ignorable_close_error(exc: Exception) -> bool:
    error_msg = str(exc).lower()
    return "closed" in error_msg or "disconnected" in error_msg


def _flush_excel_if_needed() -> None:
    if config.SAVE_DATA_OPTION != "excel":
        return

    try:
        from store.excel_store_base import ExcelStoreBase

        ExcelStoreBase.flush_all()
        print("[Main] Excel files saved successfully")
    except Exception as e:
        print(f"[Main] Error flushing Excel data: {e}")


async def main() -> None:
    global crawler

    args = await cmd_arg.parse_cmd()
    enforce_runtime_safety()

    cookiecloud_result = sync_cookiecloud_login_state(config.PLATFORM)
    if cookiecloud_result.applied:
        utils.logger.info(f"[Main] {cookiecloud_result.message}")
    elif cookiecloud_result.attempted and not cookiecloud_result.applied:
        utils.logger.warning(f"[Main] {cookiecloud_result.message}")

    utils.log_event(
        "crawler.run.begin",
        platform=config.PLATFORM,
        crawler_type=config.CRAWLER_TYPE,
        pid=os.getpid(),
    )
    if args.init_db:
        await db.init_db(args.init_db)
        print(f"Database {args.init_db} initialized successfully.")
        utils.log_event("crawler.run.init_db.complete", db=args.init_db)
        return

    ensure_energy_service_or_raise(config.PLATFORM)
    crawler = CrawlerFactory.create_crawler(platform=config.PLATFORM)
    await crawler.start()

    _flush_excel_if_needed()

    utils.log_event("crawler.run.complete", platform=config.PLATFORM, crawler_type=config.CRAWLER_TYPE)


async def async_cleanup() -> None:
    global crawler
    if crawler:
        close_method = getattr(crawler, "close", None)
        if callable(close_method):
            try:
                await close_method()
            except Exception as e:
                if not _is_ignorable_close_error(e):
                    print(f"[Main] Error closing crawler resources: {e}")

        if getattr(crawler, "browser_context", None):
            try:
                await crawler.browser_context.close()
            except Exception as e:
                if not _is_ignorable_close_error(e):
                    print(f"[Main] Error closing browser context: {e}")

    if config.SAVE_DATA_OPTION in ("db", "sqlite"):
        await db.close()

if __name__ == "__main__":
    from tools.app_runner import run

    run(main, async_cleanup, cleanup_timeout_seconds=15.0)
