# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/media_platform/twitter/client.py
# GitHub: https://github.com/EnergyCrawler
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# Declaration: This code is for learning and research purposes only. Users should follow these principles:
# 1. Not for any commercial use.
# 2. Comply with the terms of service and robots.txt rules of the target platform.
# 3. No large-scale crawling or operational disruption to the platform.
# 4. Reasonably control request frequency to avoid unnecessary burden on the target platform.
# 5. Not for any illegal or improper purposes.
#
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# Using this code means you agree to abide by the above principles and all terms in the LICENSE.

"""
Twitter/X.com API Client

Hybrid client using:
- curl_cffi for HTTP requests (TLS fingerprint impersonation)
- Energy browser for x-client-transaction-id generation
"""

import asyncio
import json
from typing import Dict, List, Optional, Any

try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    import requests as curl_requests
    _HAS_CURL_CFFI = False
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type

from tools import utils

from .api import GQL_URL, PUBLIC_BEARER_TOKEN, OPERATIONS, GQL_FEATURES, get_gql_url
from .exception import (
    TwitterError,
    TwitterAuthError,
    TwitterRateLimitError,
    TwitterNotFoundError,
    TwitterAPIError,
    TwitterTransactionIdError,
)
from .models import (
    TwitterUser,
    TwitterTweet,
    TwitterMedia,
    parse_user_from_response,
    parse_tweet_from_response,
    parse_tweets_from_timeline,
)
from .energy_adapter import TwitterEnergyAdapter


class TwitterClient:
    """
    Twitter/X.com API Client

    Hybrid architecture:
    - Energy browser for x-client-transaction-id generation
    - curl_cffi for API requests with TLS fingerprint impersonation
    """

    # Default user agent (will be updated from browser)
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(
        self,
        energy_adapter: TwitterEnergyAdapter,
        auth_token: str = "",
        ct0: str = "",
        cookie_header: str = "",
        timeout: int = 30,
        proxies: Optional[Dict] = None,
    ):
        """
        Initialize Twitter client.

        Args:
            energy_adapter: Energy browser adapter for transaction ID generation
            auth_token: Twitter auth_token cookie value
            ct0: Twitter ct0 (CSRF) cookie value
            cookie_header: Full Twitter cookie header string
            timeout: Request timeout in seconds
            proxies: Proxy configuration for curl_cffi
        """
        self._energy_adapter = energy_adapter
        self._auth_token = auth_token
        self._ct0 = ct0
        self._cookie_map = self._parse_cookie_header(cookie_header)
        if not self._auth_token:
            self._auth_token = self._cookie_map.get("auth_token", "")
        if not self._ct0:
            self._ct0 = self._cookie_map.get("ct0", "")
        self._timeout = timeout
        self._proxies = proxies
        self._user_agent: Optional[str] = None
        self._initialized = False

        if _HAS_CURL_CFFI:
            # Use curl_cffi with browser impersonation when available.
            self._session = curl_requests.Session(
                impersonate="chrome110",
                proxies=proxies,
            )
        else:
            # Fallback to requests to keep module import/runtime available without curl_cffi.
            self._session = curl_requests.Session()
            if proxies:
                normalized = {}
                for key, value in proxies.items():
                    if not value:
                        continue
                    stripped_key = key.replace("://", "")
                    normalized[stripped_key] = value
                    normalized[f"{stripped_key}://"] = value
                self._session.proxies.update(normalized)
            utils.logger.warning("[TwitterClient] curl_cffi not installed, using requests fallback session.")

    @staticmethod
    def _parse_cookie_header(cookie_header: str) -> Dict[str, str]:
        cookie_dict: Dict[str, str] = {}
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

    async def initialize(self) -> None:
        """
        Initialize client - get user agent from browser.

        This should be called before making any API requests.
        """
        if self._initialized:
            return

        try:
            # Get user agent from energy adapter
            self._user_agent = await self._energy_adapter.get_user_agent()
            utils.logger.info(f"[TwitterClient] Initialized with user agent: {self._user_agent[:50]}...")
            self._initialized = True
        except Exception as e:
            utils.logger.warning(f"[TwitterClient] Failed to get user agent from browser: {e}, using default")
            self._user_agent = self.DEFAULT_USER_AGENT
            self._initialized = True

    def set_auth(self, auth_token: str, ct0: str = "") -> None:
        """
        Set authentication tokens.

        Args:
            auth_token: Twitter auth_token cookie value
            ct0: Twitter ct0 (CSRF) cookie value (optional, will be extracted from cookies if not provided)
        """
        self._auth_token = auth_token
        if auth_token:
            self._cookie_map["auth_token"] = auth_token
        if ct0:
            self._ct0 = ct0
            self._cookie_map["ct0"] = ct0

    def update_auth_from_cookies(self, cookies: Dict[str, str]) -> None:
        """
        Update authentication from cookie dictionary.

        Args:
            cookies: Dictionary containing auth_token and optionally ct0
        """
        self._cookie_map.update(cookies)
        if "auth_token" in cookies:
            self._auth_token = cookies["auth_token"]
        if "ct0" in cookies:
            self._ct0 = cookies["ct0"]

    async def _get_transaction_id(self, method: str, path: str) -> str:
        """
        Generate x-client-transaction-id via Energy browser.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path

        Returns:
            Transaction ID string

        Raises:
            TwitterTransactionIdError: If transaction ID generation fails
        """
        try:
            transaction_id = await self._energy_adapter.generate_transaction_id(method, path)
            return transaction_id
        except Exception as e:
            utils.logger.error(f"[TwitterClient] Failed to generate transaction ID: {e}")
            raise TwitterTransactionIdError(f"Failed to generate transaction ID: {e}")

    def _build_headers(self, method: str, path: str, transaction_id: str) -> Dict[str, str]:
        """
        Build request headers for Twitter API.

        Args:
            method: HTTP method
            path: API path
            transaction_id: x-client-transaction-id value

        Returns:
            Dictionary of headers
        """
        headers = {
            "authorization": PUBLIC_BEARER_TOKEN,
            "x-twitter-auth-type": "OAuth2Session",
            "x-csrf-token": self._ct0,
            "x-client-transaction-id": transaction_id,
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
            "content-type": "application/json",
            "user-agent": self._user_agent or self.DEFAULT_USER_AGENT,
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://x.com",
            "referer": "https://x.com/",
            "sec-ch-ua": '"Chromium";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        return headers

    def _build_cookie_string(self) -> str:
        """
        Build cookie header string.

        Returns:
            Cookie string for Cookie header
        """
        cookies = dict(self._cookie_map)
        if self._auth_token:
            cookies["auth_token"] = self._auth_token
        if self._ct0:
            cookies["ct0"] = self._ct0
        return "; ".join([f"{key}={value}" for key, value in cookies.items()])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_not_exception_type((TwitterAuthError, TwitterNotFoundError)),
    )
    async def _request(
        self,
        method: str,
        operation: str,
        variables: Dict[str, Any],
        features: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make API request to Twitter GraphQL endpoint.

        Args:
            method: HTTP method (GET, POST)
            operation: GraphQL operation name (e.g., "SearchTimeline")
            variables: Request variables
            features: Feature flags (optional, uses default if not provided)

        Returns:
            Response JSON data

        Raises:
            TwitterAuthError: Authentication failed (401, 403)
            TwitterRateLimitError: Rate limited (429)
            TwitterNotFoundError: Not found (404)
            TwitterAPIError: Other API errors
        """
        # Ensure client is initialized
        if not self._initialized:
            await self.initialize()

        # Build URL
        if operation not in OPERATIONS:
            raise TwitterAPIError(f"Unknown operation: {operation}")

        url = get_gql_url(operation)

        # Build request parameters
        if features is None:
            features = GQL_FEATURES

        params = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(features, separators=(",", ":")),
        }

        # Build full URL with path for transaction ID
        path = f"/i/api/graphql/{OPERATIONS[operation]}"

        # Get transaction ID
        transaction_id = await self._get_transaction_id(method, path)

        # Build headers
        headers = self._build_headers(method, path, transaction_id)
        cookie_header = self._build_cookie_string()
        if cookie_header:
            headers["cookie"] = cookie_header

        try:
            # Make request with curl_cffi
            if method.upper() == "GET":
                response = self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._timeout,
                )
            elif method.upper() == "POST":
                response = self._session.post(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._timeout,
                )
            else:
                raise TwitterAPIError(f"Unsupported HTTP method: {method}")

            # Handle HTTP errors
            if response.status_code == 401 or response.status_code == 403:
                raise TwitterAuthError(f"Authentication failed: {response.status_code}")
            elif response.status_code == 429:
                raise TwitterRateLimitError("Rate limit exceeded")
            elif response.status_code == 404:
                raise TwitterNotFoundError(f"Resource not found: {operation}")
            elif response.status_code >= 400:
                error_text = response.text[:500] if response.text else "Unknown error"
                raise TwitterAPIError(f"API error {response.status_code}: {error_text}")

            # Parse JSON response
            data = response.json()

            # Check for errors in response body
            if "errors" in data:
                errors = data["errors"]
                error_msg = errors[0].get("message", "Unknown API error") if errors else "Unknown API error"
                raise TwitterAPIError(f"GraphQL error: {error_msg}")

            return data

        except curl_requests.exceptions.Timeout:
            raise TwitterAPIError(f"Request timeout for {operation}")
        except curl_requests.exceptions.ConnectionError as e:
            raise TwitterAPIError(f"Connection error: {e}")
        except json.JSONDecodeError as e:
            raise TwitterAPIError(f"Failed to parse response: {e}")

    # ==================== API Methods ====================

    async def search(
        self,
        query: str,
        search_type: str = "Latest",
        cursor: Optional[str] = None,
    ) -> List[TwitterTweet]:
        """
        Search tweets by query.

        Args:
            query: Search query string
            search_type: Type of search (Latest, Top, People)
            cursor: Pagination cursor for next page

        Returns:
            List of TwitterTweet objects
        """
        variables = {
            "rawQuery": query,
            "count": 20,
            "querySource": "typed_query",
            "product": search_type,
        }

        if cursor:
            variables["cursor"] = cursor

        features = GQL_FEATURES.copy()
        features["responsive_web_search_deduplication_tiles_enabled"] = False

        data = await self._request("GET", "SearchTimeline", variables, features)

        # Parse tweets from timeline
        tweets = parse_tweets_from_timeline(data)
        return tweets

    async def get_user_by_username(self, username: str) -> Optional[TwitterUser]:
        """
        Get user by username/screen_name.

        Args:
            username: Twitter username (without @)

        Returns:
            TwitterUser object or None if not found
        """
        variables = {
            "screen_name": username,
            "withSafetyModeUserFields": True,
        }

        try:
            data = await self._request("GET", "UserByScreenName", variables)

            # Navigate to user result
            user_result = data.get("data", {}).get("user", {}).get("result", {})

            if user_result:
                return parse_user_from_response(user_result)
            return None

        except TwitterNotFoundError:
            return None

    async def get_user_by_id(self, user_id: str) -> Optional[TwitterUser]:
        """
        Get user by ID.

        Args:
            user_id: Twitter user ID

        Returns:
            TwitterUser object or None if not found
        """
        variables = {
            "userId": user_id,
            "withSafetyModeUserFields": True,
        }

        try:
            data = await self._request("GET", "UserByRestId", variables)

            # Navigate to user result
            user_result = data.get("data", {}).get("user", {}).get("result", {})

            if user_result:
                return parse_user_from_response(user_result)
            return None

        except TwitterNotFoundError:
            return None

    async def get_tweet(self, tweet_id: str) -> Optional[TwitterTweet]:
        """
        Get single tweet by ID.

        Args:
            tweet_id: Tweet ID

        Returns:
            TwitterTweet object or None if not found
        """
        variables = {
            "focalTweetId": tweet_id,
            "with_rux_injections": False,
            "includePromotedContent": True,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": True,
            "withVoice": True,
            "withV2Timeline": True,
        }

        try:
            data = await self._request("GET", "TweetDetail", variables)

            # Parse tweet from response
            tweet = parse_tweet_from_response(data)
            return tweet if tweet.id else None

        except TwitterNotFoundError:
            return None

    async def get_user_tweets(
        self,
        user_id: str,
        cursor: Optional[str] = None,
        include_replies: bool = False,
    ) -> List[TwitterTweet]:
        """
        Get user's tweets.

        Args:
            user_id: Twitter user ID
            cursor: Pagination cursor
            include_replies: Whether to include replies

        Returns:
            List of TwitterTweet objects
        """
        variables = {
            "userId": user_id,
            "count": 20,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }

        if cursor:
            variables["cursor"] = cursor

        operation = "UserTweetsAndReplies" if include_replies else "UserTweets"

        data = await self._request("GET", operation, variables)

        # Parse tweets from timeline
        tweets = parse_tweets_from_timeline(data)
        return tweets

    async def get_user_media(
        self,
        user_id: str,
        cursor: Optional[str] = None,
    ) -> List[TwitterTweet]:
        """
        Get user's media tweets.

        Args:
            user_id: Twitter user ID
            cursor: Pagination cursor

        Returns:
            List of TwitterTweet objects with media
        """
        variables = {
            "userId": user_id,
            "count": 20,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }

        if cursor:
            variables["cursor"] = cursor

        data = await self._request("GET", "UserMedia", variables)

        # Parse tweets from timeline
        tweets = parse_tweets_from_timeline(data)
        return tweets

    async def get_followers(
        self,
        user_id: str,
        cursor: Optional[str] = None,
    ) -> List[TwitterUser]:
        """
        Get user's followers.

        Args:
            user_id: Twitter user ID
            cursor: Pagination cursor

        Returns:
            List of TwitterUser objects
        """
        variables = {
            "userId": user_id,
            "count": 20,
            "includePromotedContent": True,
        }

        if cursor:
            variables["cursor"] = cursor

        data = await self._request("GET", "Followers", variables)

        # Parse users from timeline
        users = self._parse_users_from_timeline(data)
        return users

    async def get_following(
        self,
        user_id: str,
        cursor: Optional[str] = None,
    ) -> List[TwitterUser]:
        """
        Get user's following.

        Args:
            user_id: Twitter user ID
            cursor: Pagination cursor

        Returns:
            List of TwitterUser objects
        """
        variables = {
            "userId": user_id,
            "count": 20,
            "includePromotedContent": True,
        }

        if cursor:
            variables["cursor"] = cursor

        data = await self._request("GET", "Following", variables)

        # Parse users from timeline
        users = self._parse_users_from_timeline(data)
        return users

    async def get_retweeters(
        self,
        tweet_id: str,
        cursor: Optional[str] = None,
    ) -> List[TwitterUser]:
        """
        Get users who retweeted a tweet.

        Args:
            tweet_id: Tweet ID
            cursor: Pagination cursor

        Returns:
            List of TwitterUser objects
        """
        variables = {
            "tweetId": tweet_id,
            "count": 20,
            "includePromotedContent": True,
        }

        if cursor:
            variables["cursor"] = cursor

        data = await self._request("GET", "Retweeters", variables)

        # Parse users from timeline
        users = self._parse_users_from_timeline(data)
        return users

    def _parse_users_from_timeline(self, data: dict) -> List[TwitterUser]:
        """
        Parse users from timeline response.

        Args:
            data: Raw timeline data

        Returns:
            List of TwitterUser objects
        """
        users = []

        # Find instructions in response
        instructions = self._find_nested_key(data, "instructions") or []

        if not instructions:
            instructions = data.get("timeline", {}).get("instructions", [])

        for instruction in instructions:
            if not isinstance(instruction, dict):
                continue

            entries = instruction.get("entries", [])

            if instruction.get("type") == "TimelineAddEntries" and not entries:
                entries = instruction.get("entry", [])

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                content = entry.get("content", {})
                entry_type = content.get("entryType")

                # Handle user entries
                if entry_type == "TimelineTimelineItem":
                    item_content = content.get("itemContent", {})
                    user_results = item_content.get("user_results", {})

                    if user_results:
                        user = parse_user_from_response(user_results)
                        if user.id:
                            users.append(user)

                # Handle timeline modules
                elif entry_type == "TimelineTimelineModule":
                    items = content.get("items", [])
                    for item in items:
                        item_content = item.get("item", {}).get("itemContent", {})
                        user_results = item_content.get("user_results", {})

                        if user_results:
                            user = parse_user_from_response(user_results)
                            if user.id:
                                users.append(user)

        return users

    def _find_nested_key(self, data: Any, key: str) -> Any:
        """
        Recursively find a key in nested dictionary/list structure.

        Args:
            data: Data structure to search
            key: Key to find

        Returns:
            Value of found key or None
        """
        if isinstance(data, dict):
            if key in data:
                return data[key]
            for value in data.values():
                result = self._find_nested_key(value, key)
                if result is not None:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_nested_key(item, key)
                if result is not None:
                    return result
        return None

    # ==================== Convenience Methods ====================

    async def search_tweets(
        self,
        query: str,
        search_type: str = "Latest",
        cursor: Optional[str] = None,
        count: int = 20,
    ) -> Dict:
        """
        Search for tweets (compatibility method).

        Args:
            query: Search query
            search_type: Search type (Latest, Top)
            cursor: Pagination cursor
            count: Number of results

        Returns:
            Dictionary with tweets and pagination info
        """
        tweets = await self.search(query, search_type, cursor)

        return {
            "tweets": tweets,
            "cursor": cursor,
            "has_more": len(tweets) >= count,
        }

    async def get_tweet_by_id(self, tweet_id: str) -> Optional[TwitterTweet]:
        """
        Get tweet by ID (alias for get_tweet).

        Args:
            tweet_id: Tweet ID

        Returns:
            TwitterTweet if found, None otherwise
        """
        return await self.get_tweet(tweet_id)

    async def get_user_by_screen_name(self, screen_name: str) -> Optional[TwitterUser]:
        """
        Get user by screen name (alias for get_user_by_username).

        Args:
            screen_name: Twitter username (without @)

        Returns:
            TwitterUser if found, None otherwise
        """
        return await self.get_user_by_username(screen_name)

    async def get_current_user(self) -> Optional[TwitterUser]:
        """
        Get current authenticated user info.

        Returns:
            TwitterUser if authenticated, None otherwise
        """
        try:
            # Use get_user_by_id with "me" to get current user
            # Note: This may not work as expected, need to verify with actual API
            return await self.get_user_by_id("me")
        except Exception as e:
            utils.logger.error(f"[TwitterClient.get_current_user] Error: {e}")
            return None

    async def get_all_user_tweets(
        self,
        user_id: str,
        max_count: int = 100,
        crawl_interval: float = 1.0,
        callback: Optional[Any] = None,
        include_replies: bool = False,
    ) -> List[TwitterTweet]:
        """
        Get all tweets from a user with pagination.

        Args:
            user_id: Twitter user ID
            max_count: Maximum number of tweets to fetch
            crawl_interval: Delay between requests in seconds
            callback: Optional callback function for each batch
            include_replies: Whether to include replies

        Returns:
            List of TwitterTweet objects
        """
        result = []
        cursor = None

        while len(result) < max_count:
            tweets = await self.get_user_tweets(
                user_id,
                cursor=cursor,
                include_replies=include_replies,
            )

            if not tweets:
                break

            # Limit to max_count
            remaining = max_count - len(result)
            tweets_to_add = tweets[:remaining]

            if callback:
                await callback(tweets_to_add)

            result.extend(tweets_to_add)

            # Get cursor for next page
            # For now, we break after first page as cursor extraction is complex
            # TODO: Extract cursor from response for proper pagination
            break

            await asyncio.sleep(crawl_interval)

        return result

    async def get_all_search_results(
        self,
        query: str,
        max_count: int = 100,
        crawl_interval: float = 1.0,
        callback: Optional[Any] = None,
        search_type: str = "Latest",
    ) -> List[TwitterTweet]:
        """
        Get all search results with pagination.

        Args:
            query: Search query string
            max_count: Maximum number of tweets to fetch
            crawl_interval: Delay between requests in seconds
            callback: Optional callback function for each batch
            search_type: Type of search (Latest, Top, People)

        Returns:
            List of TwitterTweet objects
        """
        result = []
        cursor = None

        while len(result) < max_count:
            tweets = await self.search(
                query,
                search_type=search_type,
                cursor=cursor,
            )

            if not tweets:
                break

            # Limit to max_count
            remaining = max_count - len(result)
            tweets_to_add = tweets[:remaining]

            if callback:
                await callback(tweets_to_add)

            result.extend(tweets_to_add)

            # Get cursor for next page
            # For now, we break after first page as cursor extraction is complex
            # TODO: Extract cursor from response for proper pagination
            break

            await asyncio.sleep(crawl_interval)

        return result

    async def get_media(self, url: str) -> Optional[bytes]:
        """
        Download media from URL.

        Args:
            url: Media URL

        Returns:
            Media content bytes or None
        """
        try:
            response = self._session.get(url, timeout=self._timeout)
            if response.status_code == 200:
                return response.content
            return None
        except Exception as e:
            utils.logger.error(f"[TwitterClient.get_media] Error downloading media: {e}")
            return None

    async def pong(self) -> bool:
        """
        Check if login state is still valid.

        Returns:
            True if logged in, False otherwise
        """
        try:
            # Try to get self user info
            if self._auth_token:
                # We have auth token, assume logged in
                return True
            return False
        except Exception as e:
            utils.logger.error(f"[TwitterClient.pong] Check login state failed: {e}")
            return False

    def close(self) -> None:
        """Close the client and cleanup resources."""
        try:
            if self._session:
                self._session.close()
        except Exception as e:
            utils.logger.warning(f"[TwitterClient.close] Failed to close session: {e}")

    async def aclose(self) -> None:
        """Async close for compatibility."""
        self.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


async def create_twitter_client(
    energy_adapter: TwitterEnergyAdapter,
    auth_token: str = "",
    ct0: str = "",
    cookie_header: str = "",
    timeout: int = 30,
    proxies: Optional[Dict] = None,
) -> TwitterClient:
    """
    Factory function to create and initialize a Twitter client.

    Args:
        energy_adapter: Energy browser adapter for transaction ID generation
        auth_token: Twitter auth_token cookie value
        ct0: Twitter ct0 (CSRF) cookie value
        cookie_header: Full Twitter cookie header string
        timeout: Request timeout in seconds
        proxies: Proxy configuration

    Returns:
        Initialized TwitterClient instance
    """
    client = TwitterClient(
        energy_adapter=energy_adapter,
        auth_token=auth_token,
        ct0=ct0,
        cookie_header=cookie_header,
        timeout=timeout,
        proxies=proxies,
    )
    await client.initialize()
    return client
