# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/media_platform/twitter/core.py
# GitHub: https://github.com/EnergyCrawler
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

"""
Twitter/X.com Crawler Core

Implements AbstractCrawler for Twitter platform using Energy browser service
for authentication and x-client-transaction-id generation.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

import config
from base.base_crawler import AbstractCrawler
from store import twitter as twitter_store
from tools.crawl_checkpoint import CrawlCheckpointManager
from tools.auth_watchdog import run_auth_watchdog
from tools.cookiecloud_sync import sync_cookiecloud_login_state
from tools import utils
from tools.safety import safe_sleep, calc_backoff_delay
from var import crawler_type_var, source_keyword_var

try:
    from .client import TwitterClient
    from .energy_adapter import TwitterEnergyAdapter, create_twitter_energy_adapter
    from .dom_extractor import TwitterDOMExtractor, TweetData
    from .field import TwitterCrawlerMode, TwitterSearchType
    from .exception import TwitterError, TwitterAuthError
    from .models import TwitterTweet, TwitterUser
except ImportError:
    from media_platform.twitter.client import TwitterClient
    from media_platform.twitter.energy_adapter import TwitterEnergyAdapter, create_twitter_energy_adapter
    from media_platform.twitter.dom_extractor import TwitterDOMExtractor, TweetData
    from media_platform.twitter.field import TwitterCrawlerMode, TwitterSearchType
    from media_platform.twitter.exception import TwitterError, TwitterAuthError
    from media_platform.twitter.models import TwitterTweet, TwitterUser


class TwitterCrawler(AbstractCrawler):
    """
    Twitter/X.com Crawler

    Supported modes:
    - SEARCH: Search tweets by keyword
    - USER_TWEETS: Get user's tweets
    - TWEET_DETAIL: Get tweet details and replies
    - USER_INFO: Get user information

    This crawler uses the Energy browser service for authentication
    and x-client-transaction-id generation.
    """

    twitter_client: TwitterClient
    energy_adapter: TwitterEnergyAdapter
    dom_extractor: TwitterDOMExtractor

    def __init__(self) -> None:
        """Initialize Twitter crawler."""
        self.index_url = "https://x.com"
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.twitter_client = None
        self.energy_adapter = None
        self.dom_extractor = None

        # Configuration
        self._auth_token = getattr(config, 'TWITTER_AUTH_TOKEN', '')
        self._ct0 = getattr(config, 'TWITTER_CT0', '')
        self._cookie_header = getattr(config, 'TWITTER_COOKIE', '')
        self._headless = getattr(config, 'TWITTER_HEADLESS', True)
        self._search_type = getattr(config, 'TWITTER_SEARCH_TYPE', 'Latest')

        # Crawl parameters
        self._keywords: List[str] = []
        self._user_ids: List[str] = []
        self._tweet_ids: List[str] = []
        self._max_count: int = getattr(config, 'CRAWLER_MAX_NOTES_COUNT', 50)
        self._checkpoint = CrawlCheckpointManager()
        self._runtime_auth_recovery_count = 0

    async def start(self) -> None:
        """Start the Twitter crawler."""
        utils.logger.info("[TwitterCrawler.start] Starting Twitter crawler...")
        utils.log_event(
            "crawler.twitter.start",
            platform="x",
            crawler_type=config.CRAWLER_TYPE,
        )

        # Parse configuration
        self._parse_config()

        # Initialize Energy browser adapter
        utils.logger.info("[TwitterCrawler.start] Initializing Energy browser adapter...")
        await self._init_energy_adapter()

        # Create Twitter client
        utils.logger.info("[TwitterCrawler.start] Creating Twitter client...")
        self.twitter_client = await self._create_twitter_client()

        # Check authentication
        watchdog_result = await run_auth_watchdog(
            platform="x",
            check_auth_fn=self._watchdog_check_x_auth,
            recover_auth_fn=self._watchdog_recover_x_auth,
            check_label="x auth state",
        )
        if not watchdog_result.success:
            utils.logger.warning("[TwitterCrawler.start] Authentication required. Please set TWITTER_AUTH_TOKEN.")
            utils.logger.warning(f"[TwitterCrawler.start] Auth watchdog failed: {watchdog_result.message}")
            await self.close()
            return

        # Set crawler type context
        crawler_type_var.set(config.CRAWLER_TYPE)

        # Execute crawler based on mode
        crawler_mode = self._get_crawler_mode()

        if crawler_mode == TwitterCrawlerMode.SEARCH:
            await self.search()
        elif crawler_mode == TwitterCrawlerMode.USER_TWEETS:
            await self.get_user_tweets()
        elif crawler_mode == TwitterCrawlerMode.TWEET_DETAIL:
            await self.get_tweet_detail()
        elif crawler_mode == TwitterCrawlerMode.USER_INFO:
            await self.get_user_info()
        else:
            utils.logger.error(f"[TwitterCrawler.start] Unknown crawler mode: {crawler_mode}")

        # Cleanup
        await self.close()
        utils.logger.info("[TwitterCrawler.start] Twitter crawler finished.")
        utils.log_event(
            "crawler.twitter.complete",
            platform="x",
            crawler_type=config.CRAWLER_TYPE,
        )

    def _get_crawler_mode(self) -> TwitterCrawlerMode:
        """Get crawler mode from configuration."""
        crawler_type = config.CRAWLER_TYPE.lower()

        mode_map = {
            "search": TwitterCrawlerMode.SEARCH,
            "user_tweets": TwitterCrawlerMode.USER_TWEETS,
            "user": TwitterCrawlerMode.USER_TWEETS,
            "tweet_detail": TwitterCrawlerMode.TWEET_DETAIL,
            "detail": TwitterCrawlerMode.TWEET_DETAIL,
            "user_info": TwitterCrawlerMode.USER_INFO,
            "creator": TwitterCrawlerMode.USER_TWEETS,
        }

        return mode_map.get(crawler_type, TwitterCrawlerMode.SEARCH)

    def _parse_config(self) -> None:
        """Parse configuration from config module."""
        # Parse keywords
        keywords_str = getattr(config, 'KEYWORDS', '')
        if keywords_str:
            self._keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

        # Parse user IDs
        self._user_ids = getattr(config, 'TWITTER_USER_IDS', [])

        # Parse tweet IDs
        self._tweet_ids = getattr(config, 'TWITTER_TWEET_IDS', [])

        # Max count
        self._max_count = getattr(config, 'CRAWLER_MAX_NOTES_COUNT', 50)

        utils.logger.info(
            f"[TwitterCrawler._parse_config] Keywords: {self._keywords}, "
            f"User IDs: {self._user_ids}, Tweet IDs: {self._tweet_ids}, Max: {self._max_count}"
        )

    @staticmethod
    def _scope_key_search(keyword: str, search_type: str) -> str:
        return f"x:search:{search_type}:{keyword}"

    @staticmethod
    def _scope_key_user_tweets(user_id: str) -> str:
        return f"x:user_tweets:{user_id}"

    @staticmethod
    def _split_new_tweets_before_marker(
        tweets: List[TwitterTweet],
        known_latest_tweet_id: str,
    ) -> tuple[List[TwitterTweet], bool]:
        if not known_latest_tweet_id:
            return tweets, False

        new_tweets: List[TwitterTweet] = []
        marker_found = False
        for tweet in tweets:
            tweet_id = str(tweet.id or "").strip()
            if tweet_id and tweet_id == known_latest_tweet_id:
                marker_found = True
                break
            new_tweets.append(tweet)
        return new_tweets, marker_found

    @staticmethod
    def _incremental_enabled() -> bool:
        return bool(getattr(config, "ENABLE_INCREMENTAL_CRAWL", False))

    @staticmethod
    def _resume_checkpoint_enabled() -> bool:
        return bool(getattr(config, "RESUME_FROM_CHECKPOINT", True))

    async def _watchdog_recover_x_auth(self, attempt: int) -> bool:
        """
        Try to recover X auth state for watchdog retries.

        Recovery path:
          1) Force refresh from CookieCloud (optional by config)
          2) Rebuild Energy adapter + Twitter client with latest cookies
        """
        force_cookiecloud_sync = bool(getattr(config, "AUTH_WATCHDOG_FORCE_COOKIECLOUD_SYNC", True))
        sync_result = await asyncio.to_thread(
            sync_cookiecloud_login_state,
            "x",
            "",
            force_cookiecloud_sync,
        )

        self._cookie_header = getattr(config, "TWITTER_COOKIE", "").strip()
        self._auth_token = getattr(config, "TWITTER_AUTH_TOKEN", "").strip()
        self._ct0 = getattr(config, "TWITTER_CT0", "").strip()

        utils.logger.warning(
            "[TwitterCrawler] Auth watchdog recovery attempt %s: %s",
            attempt,
            sync_result.message or "no cookiecloud update",
        )

        await self.close()
        await self._init_energy_adapter()
        self.twitter_client = await self._create_twitter_client()
        return bool(sync_result.applied) or bool(self._auth_token and self._ct0)

    async def _watchdog_check_x_auth(self) -> bool:
        """Validate X auth state with both token pair and page login signal."""
        if not await self.twitter_client.pong():
            return False

        auth_token = str(self._auth_token or "").strip()
        ct0 = str(self._ct0 or "").strip()
        if not (auth_token and ct0):
            cookies = {}
            if self.energy_adapter:
                cookies = self.energy_adapter.get_auth_cookies()
            auth_token = auth_token or str(cookies.get("auth_token", "")).strip()
            ct0 = ct0 or str(cookies.get("ct0", "")).strip()
            if not (auth_token and ct0):
                return False

        if self.energy_adapter:
            try:
                if not await self.energy_adapter.verify_login_via_page():
                    return False
            except Exception:
                return False
        return True

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        if isinstance(exc, TwitterAuthError):
            return True
        message = str(exc).lower()
        return "authentication failed" in message or "401" in message

    async def _recover_runtime_auth_if_needed(self, exc: Exception, context: str, attempt: int) -> bool:
        """
        Trigger watchdog recovery when runtime API request returns auth errors.
        """
        if not bool(getattr(config, "AUTH_WATCHDOG_ENABLED", True)):
            return False
        if not self._is_auth_error(exc):
            return False

        max_runtime_recoveries = max(0, int(getattr(config, "AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES", 1)))
        if self._runtime_auth_recovery_count >= max_runtime_recoveries:
            utils.logger.warning(
                "[TwitterCrawler.%s] Runtime auth recovery budget exhausted (%s/%s)",
                context,
                self._runtime_auth_recovery_count,
                max_runtime_recoveries,
            )
            return False

        self._runtime_auth_recovery_count += 1
        utils.logger.warning(
            "[TwitterCrawler.%s] Detected auth error on attempt %s, running watchdog recovery (%s/%s)",
            context,
            attempt,
            self._runtime_auth_recovery_count,
            max_runtime_recoveries,
        )
        recovered = await self._watchdog_recover_x_auth(attempt)
        return recovered

    async def _init_energy_adapter(self) -> None:
        """Initialize Energy browser adapter."""
        address_parts = config.ENERGY_SERVICE_ADDRESS.split(":")
        host = address_parts[0] if len(address_parts) > 0 else "localhost"
        port = int(address_parts[1]) if len(address_parts) > 1 else 50051
        browser_id = config.ENERGY_BROWSER_ID

        self.energy_adapter = create_twitter_energy_adapter(
            host=host,
            port=port,
            browser_id=browser_id,
            headless=self._headless,
        )

        # Inject full cookie jar into browser session when provided.
        if self._cookie_header:
            cookie_dict = utils.convert_str_cookie_to_dict(self._cookie_header)
            if cookie_dict:
                ok_primary = self.energy_adapter.set_cookies_from_dict(cookie_dict, domain=".x.com")
                ok_host = self.energy_adapter.set_cookies_from_dict(cookie_dict, domain="x.com")
                browser_all_cookies = self.energy_adapter.get_all_cookies()
                browser_cookie_dict = {
                    item.get("name", ""): item.get("value", "")
                    for item in browser_all_cookies
                    if item.get("name")
                }
                has_auth = bool(browser_cookie_dict.get("auth_token"))
                has_ct0 = bool(browser_cookie_dict.get("ct0"))

                # Fallback: inject via page context when service-level SetCookies
                # does not materialize auth cookies in browser storage.
                ok_js = False
                if not (has_auth and has_ct0):
                    ok_js = self.energy_adapter.set_cookies_via_js(cookie_dict, domain="x.com")
                    await asyncio.sleep(1)
                    browser_all_cookies = self.energy_adapter.get_all_cookies()
                    browser_cookie_dict = {
                        item.get("name", ""): item.get("value", "")
                        for item in browser_all_cookies
                        if item.get("name")
                    }
                    has_auth = bool(browser_cookie_dict.get("auth_token"))
                    has_ct0 = bool(browser_cookie_dict.get("ct0"))

                utils.logger.info(
                    f"[TwitterCrawler._init_energy_adapter] Injected {len(cookie_dict)} cookies into Energy browser "
                    f"(service_domains: .x.com={ok_primary}, x.com={ok_host}, js_fallback={ok_js}, "
                    f"browser_has_auth_token={has_auth}, browser_has_ct0={has_ct0}, "
                    f"browser_cookie_count={len(browser_all_cookies)})"
                )

                page_login_ok = await self.energy_adapter.verify_login_via_page(navigate_if_needed=False)
                if page_login_ok:
                    utils.logger.info("[TwitterCrawler._init_energy_adapter] Browser login state verified via page")
                else:
                    utils.logger.warning(
                        "[TwitterCrawler._init_energy_adapter] Cookie injected but page still looks logged out "
                        "(cookie may be invalid/expired or blocked by risk controls)"
                    )
            else:
                utils.logger.warning("[TwitterCrawler._init_energy_adapter] TWITTER_COOKIE provided but parsing returned empty")

        # Wait for page to load
        await asyncio.sleep(3)

        # Initialize DOM extractor
        self.dom_extractor = TwitterDOMExtractor(self.energy_adapter.browser, browser_id)

        utils.logger.info(f"[TwitterCrawler._init_energy_adapter] Energy adapter initialized (browser_id: {browser_id})")

    async def _create_twitter_client(self) -> TwitterClient:
        """Create Twitter client with authentication."""
        # Get cookies from Energy adapter if available
        if self.energy_adapter:
            cookies = self.energy_adapter.get_cookies()
            if not self._cookie_header and cookies:
                self._cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            if not self._auth_token and 'auth_token' in cookies:
                self._auth_token = cookies['auth_token']
            if not self._ct0 and 'ct0' in cookies:
                self._ct0 = cookies['ct0']

        client = TwitterClient(
            timeout=30,
            proxies=None,
            auth_token=self._auth_token,
            ct0=self._ct0,
            cookie_header=self._cookie_header,
            energy_adapter=self.energy_adapter,
        )

        return client

    async def search(self) -> None:
        """Search tweets by keywords."""
        utils.logger.info("[TwitterCrawler.search] Begin searching Twitter tweets")

        if not self._keywords:
            utils.logger.warning("[TwitterCrawler.search] No keywords configured")
            return

        search_type = TwitterSearchType(self._search_type) if self._search_type in ["Latest", "Top"] else TwitterSearchType.LATEST

        for keyword in self._keywords:
            source_keyword_var.set(keyword)
            utils.logger.info(f"[TwitterCrawler.search] Searching for: {keyword}")

            scope_key = self._scope_key_search(keyword, search_type.value)
            known_latest_tweet_id = ""
            newest_tweet_id_this_run = ""
            cursor = None
            if self._incremental_enabled():
                scope_state = self._checkpoint.get_scope(scope_key)
                known_latest_tweet_id = str(scope_state.get("latest_item_id", "")).strip()
                if self._resume_checkpoint_enabled() and scope_state.get("in_progress"):
                    cursor = scope_state.get("cursor") or None
                self._checkpoint.mark_scope_started(
                    scope_key,
                    platform="x",
                    crawler_type="search",
                    cursor=cursor or "",
                    meta={"keyword": keyword, "search_type": search_type.value},
                )
                if known_latest_tweet_id:
                    utils.logger.info(
                        f"[TwitterCrawler.search] Incremental marker for '{keyword}': {known_latest_tweet_id}"
                    )

            total_count = 0
            attempt = 0
            interrupted_by_error = False

            while total_count < self._max_count:
                try:
                    result = await self.twitter_client.search_tweets(
                        query=keyword,
                        search_type=search_type.value,
                        cursor=cursor,
                        count=min(20, self._max_count - total_count),
                    )

                    tweets: List[TwitterTweet] = result.get("tweets", [])
                    marker_found = False
                    if known_latest_tweet_id:
                        tweets, marker_found = self._split_new_tweets_before_marker(
                            tweets,
                            known_latest_tweet_id,
                        )

                    if not tweets:
                        utils.logger.info("[TwitterCrawler.search] No more tweets found")
                        break

                    remaining = self._max_count - total_count
                    tweets_to_process = tweets[:remaining]
                    if not tweets_to_process:
                        break

                    # Process tweets
                    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self._process_tweet_async_task(tweet, semaphore)
                        for tweet in tweets_to_process
                    ]
                    await asyncio.gather(*task_list)

                    if tweets_to_process and not newest_tweet_id_this_run:
                        newest_tweet_id_this_run = str(tweets_to_process[0].id or "").strip()

                    total_count += len(tweets_to_process)
                    attempt = 0

                    # Check for more results
                    next_cursor = result.get("cursor")
                    if self._incremental_enabled():
                        self._checkpoint.mark_scope_progress(
                            scope_key,
                            cursor=next_cursor or "",
                            latest_item_id=newest_tweet_id_this_run or known_latest_tweet_id,
                        )

                    if marker_found:
                        utils.logger.info(
                            f"[TwitterCrawler.search] Reached incremental marker for '{keyword}', stop pagination"
                        )
                        break

                    if not result.get("has_more", False):
                        utils.logger.info("[TwitterCrawler.search] No more results")
                        break

                    cursor = next_cursor
                    if not cursor:
                        break

                    # Rate limiting
                    await safe_sleep()

                except TwitterError as e:
                    attempt += 1
                    utils.logger.error(
                        f"[TwitterCrawler.search] Error searching tweets (attempt={attempt}): {e}"
                    )
                    if await self._recover_runtime_auth_if_needed(e, context="search", attempt=attempt):
                        attempt = 0
                        continue
                    if attempt >= 3:
                        interrupted_by_error = True
                        break
                    await safe_sleep(calc_backoff_delay(attempt))

            if self._incremental_enabled():
                if interrupted_by_error:
                    self._checkpoint.mark_scope_progress(
                        scope_key,
                        cursor=cursor or "",
                        latest_item_id=newest_tweet_id_this_run or known_latest_tweet_id,
                    )
                else:
                    self._checkpoint.mark_scope_completed(
                        scope_key,
                        latest_item_id=newest_tweet_id_this_run or known_latest_tweet_id,
                    )

            utils.logger.info(f"[TwitterCrawler.search] Total tweets collected for '{keyword}': {total_count}")

    async def get_user_tweets(self) -> None:
        """Get tweets from specified users."""
        utils.logger.info("[TwitterCrawler.get_user_tweets] Begin fetching user tweets")

        if not self._user_ids:
            utils.logger.warning("[TwitterCrawler.get_user_tweets] No user IDs configured")
            return

        for user_id in self._user_ids:
            requested_user_id = str(user_id).strip()
            resolved_user_id = requested_user_id

            if requested_user_id.startswith("@"):
                requested_user_id = requested_user_id[1:]
                resolved_user_id = requested_user_id

            if requested_user_id and not requested_user_id.isdigit():
                try:
                    user = await self.twitter_client.get_user_by_screen_name(requested_user_id)
                    if not user or not user.id:
                        utils.logger.warning(
                            f"[TwitterCrawler.get_user_tweets] User not found: {requested_user_id}"
                        )
                        continue
                    resolved_user_id = user.id
                    await self._store_user(user)
                except TwitterError as e:
                    utils.logger.error(
                        f"[TwitterCrawler.get_user_tweets] Error resolving user {requested_user_id}: {e}"
                    )
                    await self._recover_runtime_auth_if_needed(
                        e,
                        context="get_user_tweets.resolve_user",
                        attempt=1,
                    )
                    continue

            utils.logger.info(
                f"[TwitterCrawler.get_user_tweets] Fetching tweets for user: {requested_user_id} "
                f"(resolved_id={resolved_user_id})"
            )

            scope_key = self._scope_key_user_tweets(resolved_user_id)
            known_latest_tweet_id = ""
            newest_tweet_id_this_run = ""
            cursor = None
            if self._incremental_enabled():
                scope_state = self._checkpoint.get_scope(scope_key)
                known_latest_tweet_id = str(scope_state.get("latest_item_id", "")).strip()
                if self._resume_checkpoint_enabled() and scope_state.get("in_progress"):
                    cursor = scope_state.get("cursor") or None
                self._checkpoint.mark_scope_started(
                    scope_key,
                    platform="x",
                    crawler_type="creator",
                    cursor=cursor or "",
                    meta={"requested_user_id": requested_user_id, "resolved_user_id": resolved_user_id},
                )
                if known_latest_tweet_id:
                    utils.logger.info(
                        f"[TwitterCrawler.get_user_tweets] Incremental marker for {requested_user_id}: "
                        f"{known_latest_tweet_id}"
                    )

            total_count = 0
            attempt = 0
            interrupted_by_error = False

            while total_count < self._max_count:
                try:
                    result = await self.twitter_client.get_user_tweets(
                        user_id=resolved_user_id,
                        count=min(20, self._max_count - total_count),
                        cursor=cursor,
                        include_replies=False,
                    )

                    tweets: List[TwitterTweet] = result.get("tweets", [])
                    marker_found = False
                    if known_latest_tweet_id:
                        tweets, marker_found = self._split_new_tweets_before_marker(
                            tweets,
                            known_latest_tweet_id,
                        )

                    if not tweets:
                        utils.logger.info("[TwitterCrawler.get_user_tweets] No more tweets found")
                        break

                    remaining = self._max_count - total_count
                    tweets_to_process = tweets[:remaining]
                    if not tweets_to_process:
                        break

                    # Process tweets
                    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self._process_tweet_async_task(tweet, semaphore)
                        for tweet in tweets_to_process
                    ]
                    await asyncio.gather(*task_list)

                    if tweets_to_process and not newest_tweet_id_this_run:
                        newest_tweet_id_this_run = str(tweets_to_process[0].id or "").strip()

                    total_count += len(tweets_to_process)
                    attempt = 0

                    # Check for more results
                    next_cursor = result.get("cursor")
                    if self._incremental_enabled():
                        self._checkpoint.mark_scope_progress(
                            scope_key,
                            cursor=next_cursor or "",
                            latest_item_id=newest_tweet_id_this_run or known_latest_tweet_id,
                        )

                    if marker_found:
                        utils.logger.info(
                            f"[TwitterCrawler.get_user_tweets] Reached incremental marker for {requested_user_id}, "
                            "stop pagination"
                        )
                        break

                    if not result.get("has_more", False):
                        utils.logger.info("[TwitterCrawler.get_user_tweets] No more results")
                        break

                    cursor = next_cursor
                    if not cursor:
                        break

                    # Rate limiting
                    await safe_sleep()

                except TwitterError as e:
                    attempt += 1
                    utils.logger.error(
                        f"[TwitterCrawler.get_user_tweets] Error fetching tweets (attempt={attempt}): {e}"
                    )
                    if await self._recover_runtime_auth_if_needed(
                        e,
                        context="get_user_tweets",
                        attempt=attempt,
                    ):
                        attempt = 0
                        continue
                    if attempt >= 3:
                        interrupted_by_error = True
                        break
                    await safe_sleep(calc_backoff_delay(attempt))

            if self._incremental_enabled():
                if interrupted_by_error:
                    self._checkpoint.mark_scope_progress(
                        scope_key,
                        cursor=cursor or "",
                        latest_item_id=newest_tweet_id_this_run or known_latest_tweet_id,
                    )
                else:
                    self._checkpoint.mark_scope_completed(
                        scope_key,
                        latest_item_id=newest_tweet_id_this_run or known_latest_tweet_id,
                    )

            utils.logger.info(
                f"[TwitterCrawler.get_user_tweets] Total tweets for user {requested_user_id} "
                f"(resolved_id={resolved_user_id}): {total_count}"
            )

    async def get_tweet_detail(self) -> None:
        """Get tweet details."""
        utils.logger.info("[TwitterCrawler.get_tweet_detail] Begin fetching tweet details")

        if not self._tweet_ids:
            utils.logger.warning("[TwitterCrawler.get_tweet_detail] No tweet IDs configured")
            return

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self._get_tweet_detail_async_task(tweet_id, semaphore)
            for tweet_id in self._tweet_ids
        ]
        await asyncio.gather(*task_list)

    async def _get_tweet_detail_async_task(self, tweet_id: str, semaphore: asyncio.Semaphore) -> None:
        """Get tweet detail in async task."""
        async with semaphore:
            try:
                tweet = await self.twitter_client.get_tweet_by_id(tweet_id)
                if tweet:
                    await self._store_tweet(tweet)
                    await self._get_tweet_media(tweet)

                    # Get comments if enabled
                    if config.ENABLE_GET_COMMENTS:
                        await self._fetch_tweet_replies(tweet)

            except TwitterError as e:
                utils.logger.error(f"[TwitterCrawler._get_tweet_detail_async_task] Error: {e}")
            finally:
                # Keep low request rate for account safety.
                await safe_sleep()

    async def get_user_info(self) -> None:
        """Get user information."""
        utils.logger.info("[TwitterCrawler.get_user_info] Begin fetching user info")

        if not self._user_ids:
            utils.logger.warning("[TwitterCrawler.get_user_info] No user IDs configured")
            return

        for user_id in self._user_ids:
            try:
                # Try to get user by screen name first
                user = await self.twitter_client.get_user_by_screen_name(user_id)

                if user:
                    await self._store_user(user)
                    utils.logger.info(f"[TwitterCrawler.get_user_info] Stored user: {user.screen_name}")
                else:
                    utils.logger.warning(f"[TwitterCrawler.get_user_info] User not found: {user_id}")

                await safe_sleep()

            except TwitterError as e:
                utils.logger.error(f"[TwitterCrawler.get_user_info] Error fetching user {user_id}: {e}")

    async def _process_tweet_async_task(self, tweet: TwitterTweet, semaphore: asyncio.Semaphore) -> None:
        """Process a tweet in async task."""
        async with semaphore:
            try:
                # Store tweet
                await self._store_tweet(tweet)

                # Get media if enabled
                await self._get_tweet_media(tweet)

            except Exception as e:
                utils.logger.error(f"[TwitterCrawler._process_tweet_async_task] Error: {e}")
            finally:
                # Keep low request rate for account safety.
                await safe_sleep()

    async def _store_tweet(self, tweet: TwitterTweet) -> None:
        """
        Store tweet data.

        Args:
            tweet: TwitterTweet to store
        """
        if not tweet or not tweet.id:
            return

        tweet_item = self._tweet_to_store_item(tweet)
        await twitter_store.update_twitter_tweet(tweet_item)

    async def _store_user(self, user: TwitterUser) -> None:
        """
        Store user data.

        Args:
            user: TwitterUser to store
        """
        if not user or not user.id:
            return
        await twitter_store.save_twitter_creator(user.id, self._user_to_store_item(user))

    async def _get_tweet_media(self, tweet: TwitterTweet) -> None:
        """
        Download and store tweet media.

        Args:
            tweet: TwitterTweet with media
        """
        if not config.ENABLE_GET_MEIDAS:
            return

        if not tweet.media:
            return

        for idx, media in enumerate(tweet.media):
            try:
                use_video_url = media.media_type in {"video", "animated_gif"}
                url = media.video_url if use_video_url else media.media_url
                if not url:
                    continue

                content = await self.twitter_client.get_media(url)
                if content:
                    saved_file = await self._save_tweet_media_bytes(
                        tweet_id=tweet.id,
                        media_index=idx,
                        media_type=media.media_type or "file",
                        source_url=url,
                        content=content,
                    )
                    utils.logger.info(
                        f"[TwitterCrawler._get_tweet_media] Downloaded media {idx} "
                        f"for tweet {tweet.id}: {media.media_type}, saved={saved_file}"
                    )

                await safe_sleep(1.0)

            except Exception as e:
                utils.logger.error(f"[TwitterCrawler._get_tweet_media] Error downloading media: {e}")

    async def _fetch_tweet_replies(self, tweet: TwitterTweet) -> None:
        if not tweet or not tweet.id:
            return
        max_comments = max(0, int(config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES))
        if max_comments <= 0:
            return

        cursor = None
        fetched = 0
        attempt = 0
        while fetched < max_comments:
            try:
                result = await self.twitter_client.get_tweet_replies(
                    tweet_id=tweet.id,
                    cursor=cursor,
                    count=min(20, max_comments - fetched),
                )
                replies: List[TwitterTweet] = result.get("tweets", [])
                if not replies:
                    break

                replies_to_store = replies[: max_comments - fetched]
                for reply in replies_to_store:
                    comment_item = self._tweet_to_comment_item(reply, parent_comment_id=tweet.id)
                    await twitter_store.update_twitter_tweet_comment(tweet.id, comment_item)
                fetched += len(replies_to_store)
                attempt = 0

                if not result.get("has_more", False):
                    break
                cursor = result.get("cursor")
                if not cursor:
                    break
                await safe_sleep()
            except TwitterError as exc:
                attempt += 1
                utils.logger.error(
                    f"[TwitterCrawler._fetch_tweet_replies] Error fetching replies for {tweet.id} "
                    f"(attempt={attempt}): {exc}"
                )
                if attempt >= 3:
                    break
                await safe_sleep(calc_backoff_delay(attempt))

    def _tweet_to_store_item(self, tweet: TwitterTweet) -> Dict[str, Any]:
        media_list = [
            {
                "media_key": media.media_key,
                "media_id": media.media_id,
                "media_type": media.media_type,
                "media_url": media.media_url,
                "video_url": media.video_url,
                "display_url": media.display_url,
                "expanded_url": media.expanded_url,
                "width": media.width,
                "height": media.height,
                "duration_ms": media.duration_ms,
                "view_count": media.view_count,
            }
            for media in (tweet.media or [])
        ]
        return {
            "id": tweet.id,
            "id_str": tweet.id_str,
            "text": tweet.text or "",
            "created_at": tweet.created_at,
            "user_id": tweet.user_id,
            "screen_name": tweet.screen_name,
            "name": tweet.name,
            "reply_count": tweet.reply_count,
            "retweet_count": tweet.retweet_count,
            "favorite_count": tweet.favorite_count,
            "bookmark_count": tweet.bookmark_count,
            "quote_count": tweet.quote_count,
            "view_count": tweet.view_count,
            "lang": tweet.lang,
            "source": tweet.source,
            "in_reply_to_status_id": tweet.in_reply_to_status_id,
            "in_reply_to_user_id": tweet.in_reply_to_user_id,
            "in_reply_to_screen_name": tweet.in_reply_to_screen_name,
            "is_quote_status": tweet.is_quote_status,
            "quoted_status_id": tweet.quoted_status_id,
            "retweeted_status_id": tweet.retweeted_status_id,
            "possibly_sensitive": tweet.possibly_sensitive,
            "tweet_url": tweet.tweet_url,
            "hashtags": tweet.hashtags or [],
            "urls": tweet.urls or [],
            "user_mentions": tweet.user_mentions or [],
            "media": media_list,
        }

    def _user_to_store_item(self, user: TwitterUser) -> Dict[str, Any]:
        return {
            "screen_name": user.screen_name,
            "name": user.name,
            "description": user.description,
            "profile_image_url": user.profile_image_url,
            "profile_banner_url": user.profile_banner_url,
            "followers_count": user.followers_count,
            "friends_count": user.friends_count,
            "statuses_count": user.statuses_count,
            "media_count": user.media_count,
            "created_at": user.created_at,
            "location": user.location,
            "url": user.url,
            "verified": user.verified,
            "verified_type": user.verified_type,
            "is_blue_verified": user.is_blue_verified,
            "protected": user.protected,
        }

    def _tweet_to_comment_item(self, tweet: TwitterTweet, parent_comment_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "id": tweet.id,
            "text": tweet.text or "",
            "created_at": tweet.created_at,
            "reply_count": tweet.reply_count,
            "favorite_count": tweet.favorite_count,
            "parent_comment_id": parent_comment_id,
            "user": {
                "id": tweet.user_id,
                "screen_name": tweet.screen_name,
                "name": tweet.name,
            },
        }

    async def _save_tweet_media_bytes(
        self,
        tweet_id: str,
        media_index: int,
        media_type: str,
        source_url: str,
        content: bytes,
    ) -> str:
        ext = self._guess_media_extension(source_url, media_type)
        base_dir = Path(config.SAVE_DATA_PATH) if config.SAVE_DATA_PATH else Path("data")
        target_dir = base_dir / "twitter" / "media" / tweet_id
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{media_index}_{media_type}{ext}"
        file_path = target_dir / filename
        await asyncio.to_thread(file_path.write_bytes, content)
        return str(file_path)

    @staticmethod
    def _guess_media_extension(source_url: str, media_type: str) -> str:
        parsed = urlparse(source_url or "")
        suffix = Path(parsed.path).suffix.lower()
        if suffix:
            return suffix
        if media_type in {"video", "animated_gif"}:
            return ".mp4"
        return ".jpg"

    def get_search_keywords(self) -> List[str]:
        """Get search keywords from config."""
        return self._keywords

    def get_user_ids(self) -> List[str]:
        """Get user IDs from config."""
        return self._user_ids

    def get_tweet_ids(self) -> List[str]:
        """Get tweet IDs from config."""
        return self._tweet_ids

    async def launch_browser(self, chromium, browser_proxy, user_agent, headless=True):
        """
        Not used - Energy browser handles browser automation.

        Raises:
            NotImplementedError: Always, as legacy browser mode is not supported.
        """
        raise NotImplementedError("Use Energy browser adapter instead of legacy browser mode.")

    async def close(self) -> None:
        """Close crawler and cleanup resources."""
        # Close Twitter client
        if self.twitter_client:
            try:
                self.twitter_client.close()
                utils.logger.info("[TwitterCrawler.close] Twitter client closed")
            except Exception as e:
                utils.logger.error(f"[TwitterCrawler.close] Error closing Twitter client: {e}")
            finally:
                self.twitter_client = None

        # Disconnect Energy adapter
        if self.energy_adapter:
            try:
                browser_client = getattr(self.energy_adapter, "browser", None)
                browser_id = getattr(self.energy_adapter, "browser_id", None)
                if browser_client and browser_id:
                    browser_client.close_browser(browser_id)
            except Exception as e:
                utils.logger.warning(f"[TwitterCrawler.close] Error closing Energy browser: {e}")
            try:
                self.energy_adapter.disconnect()
                utils.logger.info("[TwitterCrawler.close] Energy adapter disconnected")
            except Exception as e:
                utils.logger.error(f"[TwitterCrawler.close] Error disconnecting Energy adapter: {e}")
            finally:
                self.energy_adapter = None

    # ==================== DOM Extraction Methods (No Login Required) ====================

    async def get_user_timeline_dom(
        self,
        screen_name: str,
        count: int = 20,
        scroll_times: int = 3
    ) -> List[TweetData]:
        """
        Get user timeline using DOM extraction (no login required).

        This method can be used as a fallback when API authentication is not available.
        It extracts tweets directly from the page DOM.

        Args:
            screen_name: Twitter username (without @)
            count: Maximum number of tweets to return
            scroll_times: Number of times to scroll for more tweets

        Returns:
            List of TweetData objects extracted from DOM
        """
        if not self.dom_extractor:
            utils.logger.error("[TwitterCrawler.get_user_timeline_dom] DOM extractor not initialized")
            return []

        try:
            tweets = await self.dom_extractor.get_user_timeline(
                screen_name=screen_name,
                count=count,
                scroll_times=scroll_times
            )
            utils.logger.info(
                f"[TwitterCrawler.get_user_timeline_dom] Extracted {len(tweets)} tweets "
                f"from @{screen_name} via DOM"
            )
            return tweets
        except Exception as e:
            utils.logger.error(
                f"[TwitterCrawler.get_user_timeline_dom] Error extracting tweets: {e}"
            )
            return []

    async def get_tweet_detail_dom(
        self,
        screen_name: str,
        tweet_id: str
    ) -> Optional[TweetData]:
        """
        Get tweet details using DOM extraction (no login required).

        Args:
            screen_name: Twitter username
            tweet_id: Tweet ID

        Returns:
            TweetData object or None if not found
        """
        if not self.dom_extractor:
            utils.logger.error("[TwitterCrawler.get_tweet_detail_dom] DOM extractor not initialized")
            return None

        try:
            tweet = await self.dom_extractor.get_tweet_detail(
                screen_name=screen_name,
                tweet_id=tweet_id
            )
            if tweet:
                utils.logger.info(
                    f"[TwitterCrawler.get_tweet_detail_dom] Extracted tweet {tweet_id} via DOM"
                )
            return tweet
        except Exception as e:
            utils.logger.error(
                f"[TwitterCrawler.get_tweet_detail_dom] Error extracting tweet: {e}"
            )
            return None

    async def get_user_profile_dom(self, screen_name: str) -> Optional[Dict[str, Any]]:
        """
        Get user profile using DOM extraction (no login required).

        Args:
            screen_name: Twitter username (without @)

        Returns:
            User profile dictionary or None if not found
        """
        if not self.dom_extractor:
            utils.logger.error("[TwitterCrawler.get_user_profile_dom] DOM extractor not initialized")
            return None

        try:
            profile = await self.dom_extractor.get_user_profile(screen_name=screen_name)
            if profile:
                utils.logger.info(
                    f"[TwitterCrawler.get_user_profile_dom] Extracted profile for @{screen_name} via DOM"
                )
            return profile
        except Exception as e:
            utils.logger.error(
                f"[TwitterCrawler.get_user_profile_dom] Error extracting profile: {e}"
            )
            return None

    async def get_tweet_replies_dom(
        self,
        screen_name: str,
        tweet_id: str,
        count: int = 20
    ) -> List[TweetData]:
        """
        Get tweet replies using DOM extraction (no login required).

        Args:
            screen_name: Tweet author's username
            tweet_id: Tweet ID
            count: Maximum number of replies to return

        Returns:
            List of TweetData objects (replies)
        """
        if not self.dom_extractor:
            utils.logger.error("[TwitterCrawler.get_tweet_replies_dom] DOM extractor not initialized")
            return []

        try:
            replies = await self.dom_extractor.get_tweet_replies(
                screen_name=screen_name,
                tweet_id=tweet_id,
                count=count
            )
            utils.logger.info(
                f"[TwitterCrawler.get_tweet_replies_dom] Extracted {len(replies)} replies "
                f"for tweet {tweet_id} via DOM"
            )
            return replies
        except Exception as e:
            utils.logger.error(
                f"[TwitterCrawler.get_tweet_replies_dom] Error extracting replies: {e}"
            )
            return []
