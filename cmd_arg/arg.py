# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/cmd_arg/arg.py
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


from __future__ import annotations


import sys
from enum import Enum
from types import SimpleNamespace
from typing import Iterable, Optional, Sequence, Type, TypeVar

import typer
from typing_extensions import Annotated

import config
from tools import utils
from tools.utils import str2bool


EnumT = TypeVar("EnumT", bound=Enum)


class PlatformEnum(str, Enum):
    """Supported media platform enumeration"""

    XHS = "xhs"
    X = "x"


class LoginTypeEnum(str, Enum):
    """Login type enumeration"""

    COOKIE = "cookie"


class CrawlerTypeEnum(str, Enum):
    """Crawler type enumeration"""

    SEARCH = "search"
    DETAIL = "detail"
    CREATOR = "creator"


class SaveDataOptionEnum(str, Enum):
    """Data save option enumeration"""

    CSV = "csv"
    DB = "db"
    JSON = "json"
    SQLITE = "sqlite"
    MONGODB = "mongodb"
    EXCEL = "excel"
    POSTGRES = "postgres"


class InitDbOptionEnum(str, Enum):
    """Database initialization option"""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRES = "postgres"


def _to_bool(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return str2bool(value)


def _coerce_enum(
    enum_cls: Type[EnumT],
    value: EnumT | str,
    default: EnumT,
) -> EnumT:
    """Safely convert a raw config value to an enum member."""

    if isinstance(value, enum_cls):
        return value

    try:
        return enum_cls(value)
    except ValueError:
        typer.secho(
            f"⚠️ Config value '{value}' is not within the supported range of {enum_cls.__name__}, falling back to default value '{default.value}'.",
            fg=typer.colors.YELLOW,
        )
        return default


def _normalize_argv(argv: Optional[Sequence[str]]) -> Iterable[str]:
    if argv is None:
        return list(sys.argv[1:])
    return list(argv)


def _inject_init_db_default(args: Sequence[str]) -> list[str]:
    """Ensure bare --init_db defaults to sqlite for backward compatibility."""

    normalized: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        normalized.append(arg)

        if arg == "--init_db":
            next_arg = args[i + 1] if i + 1 < len(args) else None
            if not next_arg or next_arg.startswith("-"):
                normalized.append(InitDbOptionEnum.SQLITE.value)
        i += 1

    return normalized


async def parse_cmd(argv: Optional[Sequence[str]] = None):
    """Parse command line arguments using Typer."""

    app = typer.Typer(add_completion=False)

    @app.callback(invoke_without_command=True)
    def main(
        platform: Annotated[
            PlatformEnum,
            typer.Option(
                "--platform",
                help="Media platform selection (xhs=XiaoHongShu | x=Twitter/X)",
                rich_help_panel="Basic Configuration",
            ),
        ] = _coerce_enum(PlatformEnum, config.PLATFORM, PlatformEnum.XHS),
        lt: Annotated[
            LoginTypeEnum,
            typer.Option(
                "--lt",
                help="Login type (cookie=Cookie)",
                rich_help_panel="Account Configuration",
            ),
        ] = _coerce_enum(LoginTypeEnum, config.LOGIN_TYPE, LoginTypeEnum.COOKIE),
        crawler_type: Annotated[
            CrawlerTypeEnum,
            typer.Option(
                "--type",
                help="Crawler type (search=Search | detail=Detail | creator=Creator)",
                rich_help_panel="Basic Configuration",
            ),
        ] = _coerce_enum(CrawlerTypeEnum, config.CRAWLER_TYPE, CrawlerTypeEnum.SEARCH),
        start: Annotated[
            int,
            typer.Option(
                "--start",
                help="Starting page number",
                rich_help_panel="Basic Configuration",
            ),
        ] = config.START_PAGE,
        keywords: Annotated[
            str,
            typer.Option(
                "--keywords",
                help="Enter keywords, multiple keywords separated by commas",
                rich_help_panel="Basic Configuration",
            ),
        ] = config.KEYWORDS,
        get_comment: Annotated[
            str,
            typer.Option(
                "--get_comment",
                help="Whether to crawl first-level comments, supports yes/true/t/y/1 or no/false/f/n/0",
                rich_help_panel="Comment Configuration",
                show_default=True,
            ),
        ] = str(config.ENABLE_GET_COMMENTS),
        get_sub_comment: Annotated[
            str,
            typer.Option(
                "--get_sub_comment",
                help="Whether to crawl second-level comments, supports yes/true/t/y/1 or no/false/f/n/0",
                rich_help_panel="Comment Configuration",
                show_default=True,
            ),
        ] = str(config.ENABLE_GET_SUB_COMMENTS),
        headless: Annotated[
            str,
            typer.Option(
                "--headless",
                help="Whether to enable headless mode for browser runtime, supports yes/true/t/y/1 or no/false/f/n/0",
                rich_help_panel="Runtime Configuration",
                show_default=True,
            ),
        ] = str(config.HEADLESS),
        save_data_option: Annotated[
            SaveDataOptionEnum,
            typer.Option(
                "--save_data_option",
                help="Data save option (csv=CSV file | db=MySQL database | json=JSON file | sqlite=SQLite database | mongodb=MongoDB database | excel=Excel file | postgres=PostgreSQL database)",
                rich_help_panel="Storage Configuration",
            ),
        ] = _coerce_enum(
            SaveDataOptionEnum, config.SAVE_DATA_OPTION, SaveDataOptionEnum.JSON
        ),
        init_db: Annotated[
            Optional[InitDbOptionEnum],
            typer.Option(
                "--init_db",
                help="Initialize database table structure (sqlite | mysql | postgres)",
                rich_help_panel="Storage Configuration",
            ),
        ] = None,
        cookies: Annotated[
            str,
            typer.Option(
                "--cookies",
                help="Cookie value used for Cookie login method",
                rich_help_panel="Account Configuration",
            ),
        ] = "",
        specified_id: Annotated[
            str,
            typer.Option(
                "--specified_id",
                help="Post/video ID list in detail mode, multiple IDs separated by commas (supports full URL or ID)",
                rich_help_panel="Basic Configuration",
            ),
        ] = "",
        creator_id: Annotated[
            str,
            typer.Option(
                "--creator_id",
                help="Creator ID list in creator mode, multiple IDs separated by commas (supports full URL or ID)",
                rich_help_panel="Basic Configuration",
            ),
        ] = "",
        max_comments_count_singlenotes: Annotated[
            int,
            typer.Option(
                "--max_comments_count_singlenotes",
                help="Maximum number of first-level comments to crawl per post/video",
                rich_help_panel="Comment Configuration",
            ),
        ] = config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
        max_concurrency_num: Annotated[
            int,
            typer.Option(
                "--max_concurrency_num",
                help="Maximum number of concurrent crawlers",
                rich_help_panel="Performance Configuration",
            ),
        ] = config.MAX_CONCURRENCY_NUM,
        max_notes_count: Annotated[
            int,
            typer.Option(
                "--max_notes_count",
                help="Maximum content count per task",
                rich_help_panel="Performance Configuration",
            ),
        ] = config.CRAWLER_MAX_NOTES_COUNT,
        crawl_sleep_sec: Annotated[
            float,
            typer.Option(
                "--crawl_sleep_sec",
                help="Base interval (seconds) between crawl requests",
                rich_help_panel="Performance Configuration",
            ),
        ] = float(config.CRAWLER_MAX_SLEEP_SEC),
        incremental: Annotated[
            str,
            typer.Option(
                "--incremental",
                help="Enable incremental crawl (new content only), supports yes/true/t/y/1 or no/false/f/n/0",
                rich_help_panel="Performance Configuration",
                show_default=True,
            ),
        ] = str(config.ENABLE_INCREMENTAL_CRAWL),
        resume_checkpoint: Annotated[
            str,
            typer.Option(
                "--resume_checkpoint",
                help="Resume from checkpoint after interruption, supports yes/true/t/y/1 or no/false/f/n/0",
                rich_help_panel="Performance Configuration",
                show_default=True,
            ),
        ] = str(config.RESUME_FROM_CHECKPOINT),
        checkpoint_path: Annotated[
            str,
            typer.Option(
                "--checkpoint_path",
                help="Custom checkpoint file path (optional)",
                rich_help_panel="Performance Configuration",
            ),
        ] = config.CRAWLER_CHECKPOINT_PATH,
        save_data_path: Annotated[
            str,
            typer.Option(
                "--save_data_path",
                help="Data save path, default is empty and will save to data folder",
                rich_help_panel="Storage Configuration",
            ),
        ] = config.SAVE_DATA_PATH,
    ) -> SimpleNamespace:
        """EnergyCrawler 命令行入口"""

        enable_comment = _to_bool(get_comment)
        enable_sub_comment = _to_bool(get_sub_comment)
        enable_headless = _to_bool(headless)
        enable_incremental = _to_bool(incremental)
        enable_resume_checkpoint = _to_bool(resume_checkpoint)
        init_db_value = init_db.value if init_db else None
        raw_cookies = (cookies or "").strip()

        # Parse specified_id and creator_id into lists
        specified_id_list = [id.strip() for id in specified_id.split(",") if id.strip()] if specified_id else []
        creator_id_list = [id.strip() for id in creator_id.split(",") if id.strip()] if creator_id else []

        # override global config
        config.PLATFORM = platform.value
        config.LOGIN_TYPE = lt.value
        config.CRAWLER_TYPE = crawler_type.value
        config.START_PAGE = start
        config.KEYWORDS = keywords
        config.ENABLE_GET_COMMENTS = enable_comment
        config.ENABLE_GET_SUB_COMMENTS = enable_sub_comment
        config.HEADLESS = enable_headless
        config.ENERGY_HEADLESS = enable_headless
        config.SAVE_DATA_OPTION = save_data_option.value
        if platform == PlatformEnum.XHS:
            if raw_cookies:
                config.COOKIES = raw_cookies
        else:
            # Keep xhs cookie store untouched when crawling X.
            config.COOKIES = (getattr(config, "COOKIES", "") or "").strip()
        config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = max_comments_count_singlenotes
        config.MAX_CONCURRENCY_NUM = max_concurrency_num
        config.CRAWLER_MAX_NOTES_COUNT = max_notes_count
        config.CRAWLER_MAX_SLEEP_SEC = crawl_sleep_sec
        config.ENABLE_INCREMENTAL_CRAWL = enable_incremental
        config.RESUME_FROM_CHECKPOINT = enable_resume_checkpoint
        config.CRAWLER_CHECKPOINT_PATH = checkpoint_path.strip()
        config.SAVE_DATA_PATH = save_data_path
        config.ENERGY_BROWSER_ID = config.resolve_energy_browser_id(config.PLATFORM)

        # Set platform-specific ID lists for detail/creator mode
        if specified_id_list:
            if platform == PlatformEnum.XHS:
                config.XHS_SPECIFIED_NOTE_URL_LIST = specified_id_list
            elif platform == PlatformEnum.X:
                config.TWITTER_TWEET_IDS = specified_id_list

        if creator_id_list:
            if platform == PlatformEnum.XHS:
                config.XHS_CREATOR_ID_LIST = creator_id_list
            elif platform == PlatformEnum.X:
                config.TWITTER_USER_IDS = creator_id_list

        # Keep Twitter auth config in sync when crawling X.
        if platform == PlatformEnum.X:
            if raw_cookies:
                config.TWITTER_COOKIE = raw_cookies
            else:
                config.TWITTER_COOKIE = (getattr(config, "TWITTER_COOKIE", "") or "").strip()

            cookie_map = utils.convert_str_cookie_to_dict(config.TWITTER_COOKIE)
            if cookie_map.get("auth_token"):
                config.TWITTER_AUTH_TOKEN = cookie_map["auth_token"]
            if cookie_map.get("ct0"):
                config.TWITTER_CT0 = cookie_map["ct0"]

        cookie_result = (
            config.TWITTER_COOKIE
            if platform == PlatformEnum.X
            else config.COOKIES
        )

        return SimpleNamespace(
            platform=config.PLATFORM,
            lt=config.LOGIN_TYPE,
            type=config.CRAWLER_TYPE,
            start=config.START_PAGE,
            keywords=config.KEYWORDS,
            get_comment=config.ENABLE_GET_COMMENTS,
            get_sub_comment=config.ENABLE_GET_SUB_COMMENTS,
            headless=config.HEADLESS,
            save_data_option=config.SAVE_DATA_OPTION,
            init_db=init_db_value,
            cookies=cookie_result,
            specified_id=specified_id,
            creator_id=creator_id,
        )

    command = typer.main.get_command(app)

    cli_args = _normalize_argv(argv)
    cli_args = _inject_init_db_default(cli_args)

    try:
        result = command.main(args=cli_args, standalone_mode=False)
        if isinstance(result, int):  # help/options handled by Typer; propagate exit code
            raise SystemExit(result)
        return result
    except typer.Exit as exc:  # pragma: no cover - CLI exit paths
        raise SystemExit(exc.exit_code) from exc
