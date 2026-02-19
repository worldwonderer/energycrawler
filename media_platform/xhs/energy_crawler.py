# -*- coding: utf-8 -*-
# Energy 模式下的小红书爬虫 - 不依赖旧浏览器驱动
# 当 ENABLE_ENERGY_BROWSER=True 时使用

import asyncio
import random
from typing import Dict, List, Optional, Any

import config
from base.base_crawler import AbstractCrawler
from model.m_xiaohongshu import NoteUrlInfo, CreatorUrlInfo
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import xhs as xhs_store
from tools import utils
from var import crawler_type_var, source_keyword_var

try:
    from .client import XiaoHongShuClient
    from .exception import DataFetchError, NoteNotFoundError
    from .field import SearchSortType
    from .help import parse_note_info_from_note_url, parse_creator_info_from_url, get_search_id
    from .energy_client_adapter import create_xhs_energy_adapter
except ImportError:
    from media_platform.xhs.client import XiaoHongShuClient
    from media_platform.xhs.exception import DataFetchError, NoteNotFoundError
    from media_platform.xhs.field import SearchSortType
    from media_platform.xhs.help import parse_note_info_from_note_url, parse_creator_info_from_url, get_search_id
    from media_platform.xhs.energy_client_adapter import create_xhs_energy_adapter


class XiaoHongShuEnergyCrawler(AbstractCrawler):
    """
    纯 Energy 模式的小红书爬虫
    不依赖旧浏览器驱动，使用 Energy 浏览器服务
    """

    xhs_client: XiaoHongShuClient
    energy_adapter: Any
    ip_proxy_pool: Optional[Any]

    def __init__(self) -> None:
        self.index_url = "https://www.xiaohongshu.com"
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
        self.ip_proxy_pool = None
        self.energy_adapter = None

    async def start(self) -> None:
        """启动爬虫"""
        httpx_proxy_format = None
        if config.ENABLE_IP_PROXY:
            self.ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()
            _, httpx_proxy_format = utils.format_proxy_info(ip_proxy_info)

        # 初始化 Energy 浏览器适配器
        utils.logger.info("[XiaoHongShuEnergyCrawler] Initializing Energy browser adapter...")
        await self._init_energy_adapter()

        # 创建客户端
        utils.logger.info("[XiaoHongShuEnergyCrawler] Creating XHS client...")
        self.xhs_client = await self._create_xhs_client(httpx_proxy_format)

        # 检查登录状态
        if not await self.xhs_client.pong():
            utils.logger.info("[XiaoHongShuEnergyCrawler] Login required, please login via browser first")
            utils.logger.info("[XiaoHongShuEnergyCrawler] Or set COOKIES in config")
            # 在 Energy 模式下，可以手动设置 Cookie 或通过 Energy 浏览器登录
            # 这里暂时跳过登录，假设用户已经通过其他方式登录
            return

        # 执行爬虫任务
        crawler_type_var.set(config.CRAWLER_TYPE)
        if config.CRAWLER_TYPE == "search":
            await self.search()
        elif config.CRAWLER_TYPE == "detail":
            await self.get_specified_notes()
        elif config.CRAWLER_TYPE == "creator":
            await self.get_creators_and_notes()

        utils.logger.info("[XiaoHongShuEnergyCrawler.start] XHS Energy Crawler finished...")

    async def _init_energy_adapter(self) -> None:
        """初始化 Energy 浏览器适配器"""
        address_parts = config.ENERGY_SERVICE_ADDRESS.split(":")
        host = address_parts[0] if len(address_parts) > 0 else "localhost"
        port = int(address_parts[1]) if len(address_parts) > 1 else 50051
        browser_id = f"{config.ENERGY_BROWSER_ID_PREFIX}_xhs"

        self.energy_adapter = create_xhs_energy_adapter(
            host=host,
            port=port,
            browser_id=browser_id,
            headless=config.ENERGY_HEADLESS,
        )

        # 连接到 Energy 服务并初始化浏览器
        self.energy_adapter.connect()
        self.energy_adapter.browser.create_browser(browser_id, headless=config.ENERGY_HEADLESS)
        self.energy_adapter.browser.navigate(browser_id, "https://www.xiaohongshu.com", 30000)

        # 等待页面加载
        await asyncio.sleep(3)

        utils.logger.info(f"[XiaoHongShuEnergyCrawler] Energy adapter initialized (browser_id: {browser_id})")

    async def _create_xhs_client(self, httpx_proxy_format: Optional[str] = None) -> XiaoHongShuClient:
        """创建 XHS 客户端"""
        # 从 Energy 获取 Cookie
        cookie_str, cookie_dict = await self._get_cookies_from_energy()

        client = XiaoHongShuClient(
            proxy=httpx_proxy_format,
            headers={
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://www.xiaohongshu.com",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://www.xiaohongshu.com/",
                "sec-ch-ua": '"Chromium";v="109"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Mac OS X"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": self.user_agent,
                "Cookie": cookie_str,
            },
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,
            energy_adapter=self.energy_adapter,
        )
        return client

    async def _get_cookies_from_energy(self) -> tuple:
        """从 Energy 浏览器获取 Cookie"""
        cookie_dict = self.energy_adapter.get_cookies()
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        return cookie_str, cookie_dict

    async def search(self) -> None:
        """搜索笔记并获取评论"""
        utils.logger.info("[XiaoHongShuEnergyCrawler.search] Begin search XHS keywords")
        target_note_count = max(1, int(config.CRAWLER_MAX_NOTES_COUNT))
        start_page = config.START_PAGE

        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[XiaoHongShuEnergyCrawler.search] Current search keyword: {keyword}")
            page = 1
            search_id = get_search_id()
            fetched_note_count = 0

            while fetched_note_count < target_note_count:
                if page < start_page:
                    utils.logger.info(f"[XiaoHongShuEnergyCrawler.search] Skip page {page}")
                    page += 1
                    continue

                try:
                    utils.logger.info(f"[XiaoHongShuEnergyCrawler.search] Search keyword: {keyword}, page: {page}")
                    note_ids: List[str] = []
                    xsec_tokens: List[str] = []

                    notes_res = await self.xhs_client.get_note_by_keyword(
                        keyword=keyword,
                        search_id=search_id,
                        page=page,
                        sort=(SearchSortType(config.SORT_TYPE) if config.SORT_TYPE != "" else SearchSortType.GENERAL),
                    )

                    if not notes_res:
                        utils.logger.info("[XiaoHongShuEnergyCrawler.search] No more content!")
                        break

                    raw_items = notes_res.get("items", [])
                    valid_items = [item for item in raw_items if item.get("model_type") not in ("rec_query", "hot_query")]
                    remaining = target_note_count - fetched_note_count
                    selected_items = valid_items[:remaining]
                    utils.logger.info(
                        f"[XiaoHongShuEnergyCrawler.search] Search notes count: {len(raw_items)}, "
                        f"selected: {len(selected_items)}, fetched/target: {fetched_note_count}/{target_note_count}"
                    )
                    if not selected_items:
                        utils.logger.info("[XiaoHongShuEnergyCrawler.search] No valid notes in current page")
                        if not notes_res.get("has_more", False):
                            break
                        page += 1
                        continue

                    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self.get_note_detail_async_task(
                            note_id=post_item.get("id"),
                            xsec_source=post_item.get("xsec_source"),
                            xsec_token=post_item.get("xsec_token"),
                            semaphore=semaphore,
                        ) for post_item in selected_items
                    ]
                    note_details = await asyncio.gather(*task_list)

                    for note_detail in note_details:
                        if note_detail:
                            await xhs_store.update_xhs_note(note_detail)
                            await self.get_notice_media(note_detail)
                            note_ids.append(note_detail.get("note_id"))
                            xsec_tokens.append(note_detail.get("xsec_token"))
                    fetched_note_count += len(note_ids)

                    page += 1
                    await self.batch_get_note_comments(note_ids, xsec_tokens)
                    if fetched_note_count >= target_note_count or not notes_res.get("has_more", False):
                        break
                    await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

                except DataFetchError:
                    utils.logger.error("[XiaoHongShuEnergyCrawler.search] Get note detail error")
                    break

    async def get_specified_notes(self) -> None:
        """获取指定笔记"""
        utils.logger.info("[XiaoHongShuEnergyCrawler.get_specified_notes] Begin get specified notes")

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = []

        for note_url in config.XHS_SPECIFIED_ID_LIST:
            note_info: NoteUrlInfo = parse_note_info_from_note_url(note_url)
            task_list.append(
                self.get_note_detail_async_task(
                    note_id=note_info.note_id,
                    xsec_source=note_info.xsec_source,
                    xsec_token=note_info.xsec_token,
                    semaphore=semaphore,
                )
            )

        note_details = await asyncio.gather(*task_list)
        note_ids = []
        xsec_tokens = []

        for note_detail in note_details:
            if note_detail:
                await xhs_store.update_xhs_note(note_detail)
                await self.get_notice_media(note_detail)
                note_ids.append(note_detail.get("note_id"))
                xsec_tokens.append(note_detail.get("xsec_token"))

        await self.batch_get_note_comments(note_ids, xsec_tokens)

    async def get_creators_and_notes(self) -> None:
        """获取创作者及其笔记"""
        utils.logger.info("[XiaoHongShuEnergyCrawler.get_creators_and_notes] Begin get XHS creators")

        for creator_url in config.XHS_CREATOR_ID_LIST:
            try:
                creator_info: CreatorUrlInfo = parse_creator_info_from_url(creator_url)
                user_id = creator_info.user_id

                creator_data = await self.xhs_client.get_creator_info(
                    user_id=user_id,
                    xsec_token=creator_info.xsec_token,
                    xsec_source=creator_info.xsec_source
                )
                if creator_data:
                    await xhs_store.save_creator(user_id, creator=creator_data)

            except ValueError as e:
                utils.logger.error(f"[XiaoHongShuEnergyCrawler.get_creators_and_notes] Failed to parse creator URL: {e}")
                continue

            crawl_interval = config.CRAWLER_MAX_SLEEP_SEC
            all_notes_list = await self.xhs_client.get_all_notes_by_creator(
                user_id=user_id,
                crawl_interval=crawl_interval,
                callback=self.fetch_creator_notes_detail,
                xsec_token=creator_info.xsec_token,
                xsec_source=creator_info.xsec_source,
            )

            note_ids = [n.get("note_id") for n in all_notes_list]
            xsec_tokens = [n.get("xsec_token") for n in all_notes_list]
            await self.batch_get_note_comments(note_ids, xsec_tokens)

    async def fetch_creator_notes_detail(self, note_list: List[Dict]):
        """获取创作者笔记详情"""
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_note_detail_async_task(
                note_id=post_item.get("note_id"),
                xsec_source=post_item.get("xsec_source"),
                xsec_token=post_item.get("xsec_token"),
                semaphore=semaphore,
            ) for post_item in note_list
        ]
        note_details = await asyncio.gather(*task_list)
        for note_detail in note_details:
            if note_detail:
                await xhs_store.update_xhs_note(note_detail)
                await self.get_notice_media(note_detail)
        return note_details

    async def get_note_detail_async_task(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
        semaphore: asyncio.Semaphore,
    ) -> Optional[Dict]:
        """获取笔记详情的异步任务"""
        async with semaphore:
            try:
                note_detail = await self.xhs_client.get_note_by_id(
                    note_id=note_id,
                    xsec_source=xsec_source,
                    xsec_token=xsec_token,
                )
                if note_detail:
                    note_detail["note_id"] = note_id
                    note_detail["xsec_token"] = xsec_token
                return note_detail
            except DataFetchError as ex:
                utils.logger.error(f"[XiaoHongShuEnergyCrawler.get_note_detail_async_task] Get note detail error: {ex}")
                return None
            except Exception as e:
                utils.logger.error(f"[XiaoHongShuEnergyCrawler.get_note_detail_async_task] Unexpected error: {e}")
                return None
            finally:
                # Keep low request rate for account safety.
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

    async def batch_get_note_comments(self, note_ids: List[str], xsec_tokens: List[str]) -> None:
        """批量获取笔记评论"""
        if not config.ENABLE_GET_COMMENTS:
            return

        utils.logger.info(f"[XiaoHongShuEnergyCrawler.batch_get_note_comments] Begin get {len(note_ids)} notes comments")
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_note_comments(note_id=note_id, xsec_token=xsec_token, semaphore=semaphore)
            for note_id, xsec_token in zip(note_ids, xsec_tokens)
        ]
        await asyncio.gather(*task_list)

    async def get_note_comments(self, note_id: str, xsec_token: str, semaphore: asyncio.Semaphore) -> None:
        """获取单篇笔记的评论"""
        async with semaphore:
            try:
                max_comments = max(0, int(config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES))
                if max_comments == 0:
                    return
                cursor = ""
                fetched_count = 0
                while True:
                    comments_res = await self.xhs_client.get_note_comments(
                        note_id=note_id,
                        xsec_token=xsec_token,
                        cursor=cursor,
                    )
                    if not comments_res:
                        break
                    comments = comments_res.get("comments", [])
                    if not comments:
                        break
                    remaining = max_comments - fetched_count
                    comments_to_store = comments[:remaining]
                    for comment in comments_to_store:
                        await xhs_store.update_xhs_note_comment(note_id=note_id, comment_item=comment)
                    fetched_count += len(comments_to_store)

                    if config.ENABLE_GET_SUB_COMMENTS:
                        await self.get_sub_comments(comments_to_store, note_id, xsec_token)

                    if fetched_count >= max_comments or not comments_res.get("has_more", False):
                        break
                    cursor = comments_res.get("cursor", "")
                    if not cursor:
                        break
                    await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
            except DataFetchError as ex:
                utils.logger.error(f"[XiaoHongShuEnergyCrawler.get_note_comments] Get comments error: {ex}")

    async def get_sub_comments(self, comments: List[Dict], note_id: str, xsec_token: str) -> None:
        """获取子评论"""
        for comment in comments:
            root_comment_id = comment.get("id")
            if not root_comment_id:
                continue
            try:
                cursor = ""
                while True:
                    sub_comments_res = await self.xhs_client.get_note_sub_comments(
                        note_id=note_id,
                        root_comment_id=root_comment_id,
                        xsec_token=xsec_token,
                        cursor=cursor,
                    )
                    if not sub_comments_res or not sub_comments_res.get("has_more", False):
                        break
                    cursor = sub_comments_res.get("cursor", "")
                    sub_comments = sub_comments_res.get("comments", [])
                    if not sub_comments:
                        break
                    for sub_comment in sub_comments:
                        await xhs_store.update_xhs_note_sub_comment(
                            note_id=note_id,
                            root_comment_id=root_comment_id,
                            sub_comment=sub_comment,
                        )
            except DataFetchError as ex:
                utils.logger.error(f"[XiaoHongShuEnergyCrawler.get_sub_comments] Get sub comments error: {ex}")

    async def get_notice_media(self, note_detail: Dict) -> None:
        """获取笔记媒体资源"""
        if not config.ENABLE_GET_MEIDAS:
            return
        # TODO: 实现媒体下载
        pass

    async def close(self) -> None:
        """清理资源"""
        if self.energy_adapter:
            try:
                self.energy_adapter.disconnect()
                utils.logger.info("[XiaoHongShuEnergyCrawler.close] Energy adapter disconnected")
            except Exception as e:
                utils.logger.error(f"[XiaoHongShuEnergyCrawler.close] Error disconnecting Energy adapter: {e}")
