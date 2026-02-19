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
import random
from typing import Dict, List, Optional, Any

import config
from base.base_crawler import AbstractCrawler
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from tools import utils
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
    ip_proxy_pool: Optional[Any]

    def __init__(self) -> None:
        """Initialize Twitter crawler."""
        self.index_url = "https://x.com"
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.ip_proxy_pool = None
        self.energy_adapter = None
        self.dom_extractor = None

        # Configuration
        self._auth_token = getattr(config, 'TWITTER_AUTH_TOKEN', '')
        self._ct0 = getattr(config, 'TWITTER_CT0', '')
        self._headless = getattr(config, 'TWITTER_HEADLESS', True)
        self._enable_login = getattr(config, 'TWITTER_ENABLE_LOGIN', False)
        self._search_type = getattr(config, 'TWITTER_SEARCH_TYPE', 'Latest')

        # Crawl parameters
        self._keywords: List[str] = []
        self._user_ids: List[str] = []
        self._tweet_ids: List[str] = []
        self._max_count: int = getattr(config, 'CRAWLER_MAX_NOTES_COUNT', 50)

    async def start(self) -> None:
        """Start the Twitter crawler."""
        utils.logger.info("[TwitterCrawler.start] Starting Twitter crawler...")

        # Parse configuration
        self._parse_config()

        # Set up proxy if enabled
        httpx_proxy_format = None
        if config.ENABLE_IP_PROXY:
            self.ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()
            _, httpx_proxy_format = utils.format_proxy_info(ip_proxy_info)

        # Initialize Energy browser adapter
        utils.logger.info("[TwitterCrawler.start] Initializing Energy browser adapter...")
        await self._init_energy_adapter()

        # Create Twitter client
        utils.logger.info("[TwitterCrawler.start] Creating Twitter client...")
        self.twitter_client = await self._create_twitter_client(httpx_proxy_format)

        # Check authentication
        if not await self.twitter_client.pong():
            utils.logger.warning("[TwitterCrawler.start] Authentication required. Please set TWITTER_AUTH_TOKEN.")
            if self._enable_login:
                utils.logger.info("[TwitterCrawler.start] Login enabled but not yet implemented.")
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
            "creator": TwitterCrawlerMode.USER_INFO,
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

    async def _init_energy_adapter(self) -> None:
        """Initialize Energy browser adapter."""
        address_parts = config.ENERGY_SERVICE_ADDRESS.split(":")
        host = address_parts[0] if len(address_parts) > 0 else "localhost"
        port = int(address_parts[1]) if len(address_parts) > 1 else 50051
        browser_id = f"{config.ENERGY_BROWSER_ID_PREFIX}_twitter"

        self.energy_adapter = create_twitter_energy_adapter(
            host=host,
            port=port,
            browser_id=browser_id,
            headless=self._headless,
        )

        # Connect to Energy service
        self.energy_adapter.connect()

        # Navigate to Twitter
        self.energy_adapter.browser.navigate(browser_id, "https://x.com", 30000)

        # Wait for page to load
        await asyncio.sleep(3)

        # Initialize DOM extractor
        self.dom_extractor = TwitterDOMExtractor(self.energy_adapter.browser, browser_id)

        utils.logger.info(f"[TwitterCrawler._init_energy_adapter] Energy adapter initialized (browser_id: {browser_id})")

    async def _create_twitter_client(self, httpx_proxy_format: Optional[str] = None) -> TwitterClient:
        """Create Twitter client with authentication."""
        # Get cookies from Energy adapter if available
        if self.energy_adapter:
            cookies = self.energy_adapter.get_cookies()
            if not self._auth_token and 'auth_token' in cookies:
                self._auth_token = cookies['auth_token']
            if not self._ct0 and 'ct0' in cookies:
                self._ct0 = cookies['ct0']

        client = TwitterClient(
            timeout=30,
            proxies={"http://": httpx_proxy_format, "https://": httpx_proxy_format} if httpx_proxy_format else None,
            auth_token=self._auth_token,
            ct0=self._ct0,
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

            cursor = None
            total_count = 0

            while total_count < self._max_count:
                try:
                    result = await self.twitter_client.search_tweets(
                        query=keyword,
                        search_type=search_type.value,
                        cursor=cursor,
                        count=min(20, self._max_count - total_count),
                    )

                    tweets: List[TwitterTweet] = result.get("tweets", [])

                    if not tweets:
                        utils.logger.info("[TwitterCrawler.search] No more tweets found")
                        break

                    # Process tweets
                    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self._process_tweet_async_task(tweet, semaphore)
                        for tweet in tweets
                    ]
                    await asyncio.gather(*task_list)

                    total_count += len(tweets)

                    # Check for more results
                    if not result.get("has_more", False):
                        utils.logger.info("[TwitterCrawler.search] No more results")
                        break

                    cursor = result.get("cursor")
                    if not cursor:
                        break

                    # Rate limiting
                    await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

                except TwitterError as e:
                    utils.logger.error(f"[TwitterCrawler.search] Error searching tweets: {e}")
                    break

            utils.logger.info(f"[TwitterCrawler.search] Total tweets collected for '{keyword}': {total_count}")

    async def get_user_tweets(self) -> None:
        """Get tweets from specified users."""
        utils.logger.info("[TwitterCrawler.get_user_tweets] Begin fetching user tweets")

        if not self._user_ids:
            utils.logger.warning("[TwitterCrawler.get_user_tweets] No user IDs configured")
            return

        for user_id in self._user_ids:
            utils.logger.info(f"[TwitterCrawler.get_user_tweets] Fetching tweets for user: {user_id}")

            cursor = None
            total_count = 0

            while total_count < self._max_count:
                try:
                    result = await self.twitter_client.get_user_tweets(
                        user_id=user_id,
                        count=min(20, self._max_count - total_count),
                        cursor=cursor,
                        include_replies=False,
                    )

                    tweets: List[TwitterTweet] = result.get("tweets", [])

                    if not tweets:
                        utils.logger.info("[TwitterCrawler.get_user_tweets] No more tweets found")
                        break

                    # Process tweets
                    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self._process_tweet_async_task(tweet, semaphore)
                        for tweet in tweets
                    ]
                    await asyncio.gather(*task_list)

                    total_count += len(tweets)

                    # Check for more results
                    if not result.get("has_more", False):
                        utils.logger.info("[TwitterCrawler.get_user_tweets] No more results")
                        break

                    cursor = result.get("cursor")
                    if not cursor:
                        break

                    # Rate limiting
                    await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

                except TwitterError as e:
                    utils.logger.error(f"[TwitterCrawler.get_user_tweets] Error fetching tweets: {e}")
                    break

            utils.logger.info(f"[TwitterCrawler.get_user_tweets] Total tweets for user {user_id}: {total_count}")

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
                        # TODO: Implement tweet reply fetching
                        pass

            except TwitterError as e:
                utils.logger.error(f"[TwitterCrawler._get_tweet_detail_async_task] Error: {e}")
            finally:
                # Keep low request rate for account safety.
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

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

                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

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
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

    async def _store_tweet(self, tweet: TwitterTweet) -> None:
        """
        Store tweet data.

        Args:
            tweet: TwitterTweet to store
        """
        # TODO: Implement actual storage using store module
        # For now, just log the tweet
        utils.logger.info(
            f"[TwitterCrawler._store_tweet] Tweet: {tweet.id} by @{tweet.screen_name}: "
            f"{tweet.text[:50]}... (likes: {tweet.favorite_count}, retweets: {tweet.retweet_count})"
        )

    async def _store_user(self, user: TwitterUser) -> None:
        """
        Store user data.

        Args:
            user: TwitterUser to store
        """
        # TODO: Implement actual storage using store module
        # For now, just log the user
        utils.logger.info(
            f"[TwitterCrawler._store_user] User: @{user.screen_name} ({user.name}) - "
            f"followers: {user.followers_count}, tweets: {user.statuses_count}"
        )

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
                url = media.video_url if media.media_type == "video" else media.media_url
                if not url:
                    continue

                content = await self.twitter_client.get_media(url)
                if content:
                    # TODO: Implement actual media storage
                    utils.logger.info(
                        f"[TwitterCrawler._get_tweet_media] Downloaded media {idx} "
                        f"for tweet {tweet.id}: {media.media_type}"
                    )

                await asyncio.sleep(random.random())

            except Exception as e:
                utils.logger.error(f"[TwitterCrawler._get_tweet_media] Error downloading media: {e}")

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

        # Disconnect Energy adapter
        if self.energy_adapter:
            try:
                self.energy_adapter.disconnect()
                utils.logger.info("[TwitterCrawler.close] Energy adapter disconnected")
            except Exception as e:
                utils.logger.error(f"[TwitterCrawler.close] Error disconnecting Energy adapter: {e}")

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
