# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
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
Twitter/X.com DOM Extractor

Extracts tweets from Twitter page DOM without requiring login.
Uses Energy browser to navigate and JavaScript to extract data.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class TweetData:
    """Extracted tweet data from DOM."""
    id: str
    user_name: str
    user_screen_name: str
    text: str
    created_at: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    views: int = 0
    quotes: int = 0
    bookmarks: int = 0
    has_media: bool = False
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    url: str = ""
    is_retweet: bool = False
    is_reply: bool = False
    reply_to_id: Optional[str] = None
    reply_to_user: Optional[str] = None


class TwitterDOMExtractor:
    """
    Extract tweets from Twitter/X.com page DOM.

    No login required for public profiles and tweets.
    """

    TWITTER_BASE_URL = "https://x.com"

    # JavaScript to extract tweets from timeline
    EXTRACT_TIMELINE_JS = """
    (function() {
        const tweets = [];
        const tweetElements = document.querySelectorAll('[data-testid="tweet"]');

        tweetElements.forEach((tweet) => {
            try {
                // Get tweet ID from link
                const linkElement = tweet.querySelector('a[href*="/status/"]');
                if (!linkElement) return;
                const link = linkElement.href;
                const tweetIdMatch = link.match(/status\\/(\\d+)/);
                if (!tweetIdMatch) return;
                const tweetId = tweetIdMatch[1];

                // Get text
                const textElement = tweet.querySelector('[data-testid="tweetText"]');
                const text = textElement ? textElement.innerText : '';

                // Get user info
                const userElement = tweet.querySelector('[data-testid="User-Name"]');
                const userName = userElement ? userElement.innerText.split('\\n')[0] : '';
                const screenNameLink = tweet.querySelector('a[href^="/"][role="link"]');
                const screenName = screenNameLink ? screenNameLink.href.split('/').pop() : '';

                // Get engagement numbers
                const getNumber = (selector) => {
                    const el = tweet.querySelector(`[data-testid="${selector}"]`);
                    if (!el) return 0;
                    const label = el.getAttribute('aria-label') || '';
                    const match = label.match(/[\\d,]+/);
                    return match ? parseInt(match[0].replace(/,/g, '')) : 0;
                };

                // Get images
                const images = [];
                const imgElements = tweet.querySelectorAll('[data-testid="tweetPhoto"] img');
                imgElements.forEach(img => {
                    if (img.src && !img.src.includes('profile_images')) {
                        images.push(img.src);
                    }
                });

                // Get videos
                const videos = [];
                const videoElements = tweet.querySelectorAll('video');
                videoElements.forEach(video => {
                    if (video.src) videos.push(video.src);
                });

                // Check if retweet
                const isRetweet = tweet.querySelector('[data-testid="socialContext"]') !== null;

                // Get timestamp
                const timeElement = tweet.querySelector('time');
                const timestamp = timeElement ? timeElement.getAttribute('datetime') : '';

                tweets.push({
                    id: tweetId,
                    user_name: userName,
                    user_screen_name: screenName,
                    text: text,
                    created_at: timestamp,
                    likes: getNumber('like'),
                    retweets: getNumber('retweet'),
                    replies: getNumber('reply'),
                    views: getNumber('view'),
                    has_media: images.length > 0 || videos.length > 0,
                    images: images,
                    videos: videos,
                    url: link,
                    is_retweet: isRetweet
                });
            } catch (e) {
                // Skip problematic tweets
            }
        });

        return JSON.stringify({ tweets: tweets, count: tweets.length });
    })();
    """

    # JavaScript to extract tweet detail
    EXTRACT_TWEET_DETAIL_JS = """
    (function() {
        const tweet = document.querySelector('[data-testid="tweet"]');
        if (!tweet) return '{"error": "Tweet not found"}';

        // Get tweet ID from URL
        const urlMatch = window.location.href.match(/status\\/(\\d+)/);
        const tweetId = urlMatch ? urlMatch[1] : '';

        // Get text
        const textElement = tweet.querySelector('[data-testid="tweetText"]');
        const text = textElement ? textElement.innerText : '';

        // Get user info
        const userElement = tweet.querySelector('[data-testid="User-Name"]');
        const userName = userElement ? userElement.innerText.split('\\n')[0] : '';
        const screenNameLink = tweet.querySelector('a[href^="/"][role="link"]');
        const screenName = screenNameLink ? screenNameLink.href.split('/').pop() : '';

        // Get timestamp
        const timeElement = tweet.querySelector('time');
        const timestamp = timeElement ? timeElement.getAttribute('datetime') : '';

        // Get engagement
        const getNumber = (selector) => {
            const el = document.querySelector(`[data-testid="${selector}"]`);
            if (!el) return 0;
            const label = el.getAttribute('aria-label') || '';
            const match = label.match(/[\\d,]+/);
            return match ? parseInt(match[0].replace(/,/g, '')) : 0;
        };

        // Get all images
        const images = [];
        const imgElements = tweet.querySelectorAll('[data-testid="tweetPhoto"] img');
        imgElements.forEach(img => {
            if (img.src && !img.src.includes('profile_images')) {
                images.push(img.src);
            }
        });

        // Get videos
        const videos = [];
        const videoElements = document.querySelectorAll('video');
        videoElements.forEach(video => {
            if (video.src) videos.push(video.src);
        });

        // Check if reply
        const replyContext = document.querySelector('[data-testid="tweetContext"]');
        const isReply = replyContext !== null;

        return JSON.stringify({
            id: tweetId,
            user_name: userName,
            user_screen_name: screenName,
            text: text,
            created_at: timestamp,
            likes: getNumber('like'),
            retweets: getNumber('retweet'),
            replies: getNumber('reply'),
            views: getNumber('view'),
            bookmarks: getNumber('bookmark'),
            has_media: images.length > 0 || videos.length > 0,
            images: images,
            videos: videos,
            url: window.location.href,
            is_reply: isReply
        });
    })();
    """

    # JavaScript to extract tweet replies from tweet detail page
    EXTRACT_REPLIES_JS = """
    (function() {
        const replies = [];
        const tweetElements = document.querySelectorAll('[data-testid="tweet"]');

        // Skip the first tweet element (main tweet)
        // Extract all subsequent tweets as replies
        for (let i = 1; i < tweetElements.length; i++) {
            const tweet = tweetElements[i];
            try {
                // Get tweet ID from link
                const linkElement = tweet.querySelector('a[href*="/status/"]');
                if (!linkElement) continue;
                const link = linkElement.href;
                const tweetIdMatch = link.match(/status\\/(\\d+)/);
                if (!tweetIdMatch) continue;
                const tweetId = tweetIdMatch[1];

                // Get text
                const textElement = tweet.querySelector('[data-testid="tweetText"]');
                const text = textElement ? textElement.innerText : '';

                // Get user info - handle multiple structures
                let userName = '';
                let screenName = '';

                // Method 1: Try User-Name testid
                const userElement = tweet.querySelector('[data-testid="User-Name"]');
                if (userElement) {
                    const userLinks = userElement.querySelectorAll('a');
                    for (const userLink of userLinks) {
                        const href = userLink.getAttribute('href') || '';
                        if (href.startsWith('/') && !href.includes('/status/')) {
                            screenName = href.substring(1);
                            const span = userLink.querySelector('span');
                            if (span) {
                                userName = span.innerText || '';
                            }
                            break;
                        }
                    }
                }

                // Method 2: Fallback - get from any link with user path
                if (!screenName) {
                    const userLink = tweet.querySelector('a[href^="/"][role="link"]:not([href*="/status/"])');
                    if (userLink) {
                        screenName = userLink.href.split('/').pop().split('?')[0];
                    }
                }

                // Get user name from first span in User-Name if not found
                if (!userName && userElement) {
                    const spans = userElement.querySelectorAll('span');
                    for (const span of spans) {
                        const t = span.innerText.trim();
                        if (t && t.length > 0 && !t.startsWith('@')) {
                            userName = t;
                            break;
                        }
                    }
                }

                // Get timestamp
                const timeElement = tweet.querySelector('time');
                const timestamp = timeElement ? timeElement.getAttribute('datetime') : '';

                // Get engagement numbers
                const getNumber = (selector) => {
                    const el = tweet.querySelector(`[data-testid="${selector}"]`);
                    if (!el) return 0;
                    const label = el.getAttribute('aria-label') || '';
                    const match = label.match(/[\\d,]+/);
                    return match ? parseInt(match[0].replace(/,/g, '')) : 0;
                };

                // Get images
                const images = [];
                const imgElements = tweet.querySelectorAll('[data-testid="tweetPhoto"] img');
                imgElements.forEach(img => {
                    if (img.src && !img.src.includes('profile_images')) {
                        images.push(img.src);
                    }
                });

                // Get videos
                const videos = [];
                const videoElements = tweet.querySelectorAll('video');
                videoElements.forEach(video => {
                    if (video.src) videos.push(video.src);
                });

                replies.push({
                    id: tweetId,
                    user_name: userName,
                    user_screen_name: screenName,
                    text: text,
                    created_at: timestamp,
                    likes: getNumber('like'),
                    retweets: getNumber('retweet'),
                    replies: getNumber('reply'),
                    views: getNumber('view'),
                    has_media: images.length > 0 || videos.length > 0,
                    images: images,
                    videos: videos,
                    url: link,
                    is_reply: true
                });
            } catch (e) {
                // Skip problematic tweets
                console.error('Error extracting reply:', e);
            }
        }

        return JSON.stringify({ replies: replies, count: replies.length });
    })();
    """

    # JavaScript to extract user profile
    EXTRACT_USER_PROFILE_JS = """
    (function() {
        let userName = '';
        let screenName = '';

        // 从 URL 获取 screen_name
        const urlMatch = window.location.pathname.match(/^\\/(\\w+)/);
        screenName = urlMatch ? urlMatch[1] : '';

        // 获取用户名 - 尝试多种方法
        // 方法1: 查找大字体的用户名 (通常是第一个大的文本块)
        const mainColumn = document.querySelector('[data-testid="primaryColumn"]');
        if (mainColumn) {
            // 获取所有 span 元素
            const spans = mainColumn.querySelectorAll('span');
            for (const span of spans) {
                const text = span.innerText.trim();
                // 排除: 空、太短、包含特殊关键词、@开头、数字
                if (text && text.length > 1 && text.length < 100 &&
                    !text.includes('@') && !text.includes('Joined') &&
                    !text.includes('following') && !text.includes('follower') &&
                    !text.match(/^\\d/)) {
                    userName = text;
                    break;
                }
            }
        }

        // 方法2: 从 h1 元素获取
        if (!userName) {
            const h1s = document.querySelectorAll('h1');
            for (const h1 of h1s) {
                const text = h1.innerText.trim();
                if (text && text.length > 1 && !text.includes('@') && !text.includes('Joined')) {
                    userName = text;
                    break;
                }
            }
        }

        // 方法3: 从 User-Name testid 获取
        if (!userName) {
            const userNameEl = document.querySelector('[data-testid="UserName"]');
            if (userNameEl) {
                userName = userNameEl.innerText.split('\\n')[0];
            }
        }

        // 获取 bio
        const bio = document.querySelector('[data-testid="UserDescription"]')?.innerText ||
                    document.querySelector('[data-testid="userDescription"]')?.innerText || '';

        // 获取位置
        const location = document.querySelector('[data-testid="UserLocation"]')?.innerText ||
                         document.querySelector('[data-testid="userLocation"]')?.innerText || '';

        // 获取网站
        const website = document.querySelector('[data-testid="UserProfileHeader_Items"] a')?.href || '';

        // 获取粉丝数
        const getCount = (text) => {
            if (!text) return 0;
            text = text.toString();
            const match = text.match(/([\\d.]+)\\s*([KM]?)/i);
            if (!match) return 0;
            let num = parseFloat(match[1]);
            const suffix = match[2].toUpperCase();
            if (suffix === 'M') num *= 1000000;
            else if (suffix === 'K') num *= 1000;
            return Math.floor(num);
        };

        let followingCount = 0;
        let followersCount = 0;

        const allLinks = document.querySelectorAll('a[href*="following"], a[href*="followers"]');
        allLinks.forEach(link => {
            const href = link.getAttribute('href') || '';
            const text = link.innerText || link.getAttribute('aria-label') || '';
            if (href.includes('following') && !href.includes('followers')) {
                followingCount = getCount(text);
            } else if (href.includes('followers')) {
                followersCount = getCount(text);
            }
        });

        // 获取头像
        const avatar = document.querySelector('img[src*="profile_images"]');
        const avatarUrl = avatar ? avatar.src : '';

        return JSON.stringify({
            screen_name: screenName,
            name: userName,
            bio: bio,
            location: location,
            website: website,
            avatar_url: avatarUrl,
            following_count: followingCount,
            followers_count: followersCount
        });
    })();
    """

    def __init__(self, browser_client, browser_id: str):
        """
        Initialize DOM extractor.

        Args:
            browser_client: Energy browser client
            browser_id: Browser instance ID
        """
        self.client = browser_client
        self.browser_id = browser_id

    def _execute_js(self, script: str) -> Dict:
        """Execute JavaScript and parse JSON result."""
        result = self.client.execute_js(self.browser_id, script)
        return self._parse_json_result(result)

    def _parse_json_result(self, result: str) -> Dict:
        """Parse JSON from browser JS result."""
        if not result:
            return {}

        cleaned = result.strip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        cleaned = cleaned.replace('\\"', '"')

        try:
            return json.loads(cleaned)
        except Exception as e:
            logger.warning(f"[TwitterDOMExtractor] JSON parse error: {e}")
            return {}

    def navigate(self, url: str, wait_ms: int = 3000) -> bool:
        """Navigate to URL and wait for page load.

        Note: This is a synchronous wrapper. In async contexts, use navigate_async() instead.
        """
        import time
        status = self.client.navigate(self.browser_id, url, timeout_ms=30000)
        time.sleep(wait_ms / 1000)
        return status == 200

    async def navigate_async(self, url: str, wait_seconds: float = 3) -> bool:
        """Async navigate to URL."""
        status = self.client.navigate(self.browser_id, url, timeout_ms=30000)
        await asyncio.sleep(wait_seconds)
        return status == 200

    async def get_user_timeline(
        self,
        screen_name: str,
        count: int = 20,
        scroll_times: int = 3
    ) -> List[TweetData]:
        """
        Get user's tweets from their profile page.

        Args:
            screen_name: Twitter username (without @)
            count: Maximum tweets to return
            scroll_times: Number of times to scroll for more tweets

        Returns:
            List of TweetData objects
        """
        url = f"{self.TWITTER_BASE_URL}/{screen_name}"
        await self.navigate_async(url, wait_seconds=4)

        # Scroll to load more tweets
        for i in range(scroll_times):
            self.client.execute_js(self.browser_id, "window.scrollBy(0, 800)")
            await asyncio.sleep(1.5)

        # Extract tweets
        data = self._execute_js(self.EXTRACT_TIMELINE_JS)
        tweets = data.get('tweets', [])

        result = []
        for t in tweets[:count]:
            result.append(TweetData(
                id=t.get('id', ''),
                user_name=t.get('user_name', ''),
                user_screen_name=t.get('user_screen_name', ''),
                text=t.get('text', ''),
                created_at=t.get('created_at'),
                likes=t.get('likes', 0),
                retweets=t.get('retweets', 0),
                replies=t.get('replies', 0),
                views=t.get('views', 0),
                has_media=t.get('has_media', False),
                images=t.get('images', []),
                videos=t.get('videos', []),
                url=t.get('url', ''),
                is_retweet=t.get('is_retweet', False)
            ))

        logger.info(f"[TwitterDOMExtractor] Extracted {len(result)} tweets from @{screen_name}")
        return result

    async def get_tweet_detail(self, screen_name: str, tweet_id: str) -> Optional[TweetData]:
        """
        Get tweet details.

        Args:
            screen_name: Twitter username
            tweet_id: Tweet ID

        Returns:
            TweetData object or None
        """
        url = f"{self.TWITTER_BASE_URL}/{screen_name}/status/{tweet_id}"
        await self.navigate_async(url, wait_seconds=3)

        data = self._execute_js(self.EXTRACT_TWEET_DETAIL_JS)

        if data.get('error'):
            logger.warning(f"[TwitterDOMExtractor] Tweet not found: {tweet_id}")
            return None

        return TweetData(
            id=data.get('id', ''),
            user_name=data.get('user_name', ''),
            user_screen_name=data.get('user_screen_name', ''),
            text=data.get('text', ''),
            created_at=data.get('created_at'),
            likes=data.get('likes', 0),
            retweets=data.get('retweets', 0),
            replies=data.get('replies', 0),
            views=data.get('views', 0),
            bookmarks=data.get('bookmarks', 0),
            has_media=data.get('has_media', False),
            images=data.get('images', []),
            videos=data.get('videos', []),
            url=data.get('url', ''),
            is_reply=data.get('is_reply', False)
        )

    async def get_user_profile(self, screen_name: str) -> Optional[Dict[str, Any]]:
        """
        Get user profile information.

        Args:
            screen_name: Twitter username (without @)

        Returns:
            User profile dictionary or None
        """
        url = f"{self.TWITTER_BASE_URL}/{screen_name}"
        await self.navigate_async(url, wait_seconds=3)

        data = self._execute_js(self.EXTRACT_USER_PROFILE_JS)

        if not data.get('screen_name'):
            logger.warning(f"[TwitterDOMExtractor] Profile not found: @{screen_name}")
            return None

        logger.info(f"[TwitterDOMExtractor] Got profile for @{screen_name}")
        return data

    async def debug_tweet_page(self, screen_name: str, tweet_id: str) -> Dict:
        """Debug tweet page to see available elements."""
        url = f"{self.TWITTER_BASE_URL}/{screen_name}/status/{tweet_id}"
        await self.navigate_async(url, wait_seconds=5)

        debug_script = """
        (function() {
            const tweets = document.querySelectorAll('[data-testid="tweet"]');
            const tweetTexts = document.querySelectorAll('[data-testid="tweetText"]');
            const articles = document.querySelectorAll('article');
            const sections = document.querySelectorAll('section');

            return JSON.stringify({
                tweet_count: tweets.length,
                tweetText_count: tweetTexts.length,
                article_count: articles.length,
                section_count: sections.length,
                url: window.location.href
            });
        })();
        """

        return self._execute_js(debug_script)

    async def get_tweet_replies(
        self,
        screen_name: str,
        tweet_id: str,
        count: int = 20,
        scroll_times: int = 6,
        prefer_api: bool = True
    ) -> List[TweetData]:
        """
        Get replies to a tweet.

        This method supports two approaches:
        1. API-based (preferred, requires authentication): Uses Twitter's GraphQL API
           to fetch replies directly. Fast and reliable.
        2. DOM-based (fallback, no authentication required): Attempts to click the
           "Read X replies" button and extract replies from the page.

        NOTE: The DOM-based approach has limitations - the "Read X replies" button
        uses React's event system and JS click simulation typically doesn't work.
        For reliable reply extraction without authentication, consider using Twitter API v2.

        Args:
            screen_name: Tweet author's username
            tweet_id: Tweet ID
            count: Maximum replies to return
            scroll_time: Number of times to scroll for more replies (DOM mode)
            prefer_api: If True and authenticated, use API method first

        Returns:
            List of TweetData objects (replies)
        """
        # Check if authenticated and prefer API method
        if prefer_api and self.is_authenticated():
            logger.info(f"[TwitterDOMExtractor] Using API method for replies (authenticated)")
            url = f"{self.TWITTER_BASE_URL}/{screen_name}/status/{tweet_id}"
            await self.navigate_async(url, wait_seconds=3)
            try:
                return await self.get_tweet_replies_via_api(tweet_id, count)
            except Exception as e:
                logger.warning(f"[TwitterDOMExtractor] API method failed, falling back to DOM: {e}")

        url = f"{self.TWITTER_BASE_URL}/{screen_name}/status/{tweet_id}"
        await self.navigate_async(url, wait_seconds=5)

        # Wait for page to fully load
        await asyncio.sleep(2)

        # Find "Read replies" button position
        find_button_script = """
        (function() {
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                const text = btn.innerText || '';
                if (text.toLowerCase().includes('read') && text.toLowerCase().includes('repl')) {
                    const rect = btn.getBoundingClientRect();
                    return JSON.stringify({
                        found: true,
                        text: text,
                        x: Math.round(rect.left + rect.width / 2),
                        y: Math.round(rect.top + rect.height / 2)
                    });
                }
            }
            return JSON.stringify({found: false});
        })();
        """
        btn_info = self._execute_js(find_button_script)

        if btn_info and btn_info.get('found'):
            logger.info(f"[TwitterDOMExtractor] Found '{btn_info.get('text')}' button at ({btn_info.get('x')}, {btn_info.get('y')})")

            # Try real browser click first (if Energy service supports it)
            try:
                click_result = self.client.click(
                    self.browser_id,
                    x=btn_info.get('x', 0),
                    y=btn_info.get('y', 0)
                )
                logger.info(f"[TwitterDOMExtractor] Real click result: {click_result}")
                await asyncio.sleep(4)
            except Exception as e:
                # Fall back to JS click simulation
                logger.warning(f"[TwitterDOMExtractor] Real click not available, trying JS click: {e}")
                click_replies_script = """
                (function() {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.innerText || '';
                        if (text.toLowerCase().includes('read') && text.toLowerCase().includes('repl')) {
                            btn.click();
                            return JSON.stringify({clicked: true, text: text});
                        }
                    }
                    return JSON.stringify({clicked: false});
                })();
                """
                click_result = self._execute_js(click_replies_script)
                if click_result.get('clicked'):
                    logger.info(f"[TwitterDOMExtractor] JS click on '{click_result.get('text')}' button")
                await asyncio.sleep(4)

        # Scroll multiple times to load more replies
        for i in range(scroll_times):
            self.client.execute_js(self.browser_id, "window.scrollBy(0, 1000)")
            await asyncio.sleep(2)

        # Check how many tweet elements exist on page
        check_script = """
        (function() {
            const tweets = document.querySelectorAll('[data-testid="tweet"]');
            return JSON.stringify({count: tweets.length});
        })();
        """
        check = self._execute_js(check_script)
        logger.info(f"[TwitterDOMExtractor] Found {check.get('count', 0)} tweet elements on page")

        # Extract replies using dedicated script (skips first/main tweet)
        data = self._execute_js(self.EXTRACT_REPLIES_JS)
        raw_replies = data.get('replies', [])

        logger.info(f"[TwitterDOMExtractor] Extracted {len(raw_replies)} replies from page")

        # Convert to TweetData objects
        replies = []
        for t in raw_replies[:count]:
            if t.get('id') and t.get('text'):  # Ensure valid data
                replies.append(TweetData(
                    id=t.get('id', ''),
                    user_name=t.get('user_name', ''),
                    user_screen_name=t.get('user_screen_name', ''),
                    text=t.get('text', ''),
                    created_at=t.get('created_at'),
                    likes=t.get('likes', 0),
                    retweets=t.get('retweets', 0),
                    replies=t.get('replies', 0),
                    views=t.get('views', 0),
                    has_media=t.get('has_media', False),
                    images=t.get('images', []),
                    videos=t.get('videos', []),
                    url=t.get('url', ''),
                    is_reply=True
                ))

        logger.info(f"[TwitterDOMExtractor] Returning {len(replies)} valid replies")
        return replies

    def is_authenticated(self) -> bool:
        """
        Check if the browser session is authenticated with Twitter.

        Returns:
            True if auth_token and ct0 cookies are present
        """
        try:
            cookies = self.client.get_cookies(self.browser_id, "https://x.com")
            has_auth_token = False
            has_ct0 = False

            for c in cookies:
                if c.name == 'auth_token':
                    has_auth_token = True
                elif c.name == 'ct0':
                    has_ct0 = True

            return has_auth_token and has_ct0
        except Exception as e:
            logger.warning(f"[TwitterDOMExtractor] Failed to check auth status: {e}")
            return False

    async def get_tweet_replies_via_api(
        self,
        tweet_id: str,
        count: int = 20
    ) -> List[TweetData]:
        """
        Get replies to a tweet via Twitter's GraphQL API.

        This method requires an authenticated session (auth_token and ct0 cookies).

        Args:
            tweet_id: Tweet ID
            count: Maximum replies to return

        Returns:
            List of TweetData objects (replies)

        Raises:
            Exception: If not authenticated
        """
        if not self.is_authenticated():
            raise Exception("Authentication required. Please login to Twitter first.")

        # Get cookies for API call
        cookies = self.client.get_cookies(self.browser_id, "https://x.com")
        ct0 = None
        for c in cookies:
            if c.name == 'ct0':
                ct0 = c.value
                break

        # Call Twitter GraphQL API from browser context
        api_script = f"""
        (async function() {{
            try {{
                const tweetId = '{tweet_id}';
                const variables = {{
                    "focalTweetId": tweetId,
                    "with_rux_injections": false,
                    "includePromotedContent": false,
                    "withCommunity": false,
                    "withQuickPromoteEligibilityTweetFields": false,
                    "withArticleRichContent": false,
                    "withBirdwatchNotes": false,
                    "withVoice": false,
                    "withV2Timeline": true
                }};

                const url = 'https://x.com/i/api/graphql/ic1wEv0iY3loEXQdI0j-PQ/TweetDetail?variables=' + encodeURIComponent(JSON.stringify(variables));

                const response = await fetch(url, {{
                    method: 'GET',
                    credentials: 'include',
                    headers: {{
                        'authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
                        'x-twitter-auth-type': 'OAuth2Session',
                        'x-twitter-active-user': 'yes',
                        'x-csrf-token': '{ct0}'
                    }}
                }});

                if (!response.ok) {{
                    return JSON.stringify({{error: 'API error', status: response.status}});
                }}

                const data = await response.json();

                // Extract replies from the response
                const instructions = data?.data?.threaded_conversation_with_injections_v2?.instructions || [];
                let replies = [];

                for (const instruction of instructions) {{
                    if (instruction.type === 'TimelineAddEntries') {{
                        for (const entry of instruction.entries || []) {{
                            if (entry.entryId?.startsWith('tweet-')) {{
                                const tweet = entry.content?.itemContent?.tweet_results?.result;
                                if (tweet && tweet.rest_id !== tweetId) {{
                                    const legacy = tweet.legacy || {{}};
                                    const user = tweet.core?.user_results?.result?.legacy || {{}};

                                    replies.push({{
                                        id: tweet.rest_id,
                                        user_name: user.name || '',
                                        user_screen_name: user.screen_name || '',
                                        text: legacy.full_text || '',
                                        created_at: legacy.created_at || '',
                                        likes: legacy.favorite_count || 0,
                                        retweets: legacy.retweet_count || 0,
                                        replies: legacy.reply_count || 0,
                                        url: 'https://x.com/' + user.screen_name + '/status/' + tweet.rest_id
                                    }});
                                }}
                            }}
                        }}
                    }}
                }}

                return JSON.stringify({{success: true, replies: replies, count: replies.length}});
            }} catch (e) {{
                return JSON.stringify({{error: e.toString()}});
            }}
        }})();
        """

        result = self.client.execute_js(self.browser_id, api_script)
        data = self._parse_json_result(result)

        if data.get('error'):
            logger.error(f"[TwitterDOMExtractor] API error: {data.get('error')}")
            return []

        raw_replies = data.get('replies', [])
        logger.info(f"[TwitterDOMExtractor] Got {len(raw_replies)} replies via API")

        replies = []
        for t in raw_replies[:count]:
            if t.get('id') and t.get('text'):
                replies.append(TweetData(
                    id=t.get('id', ''),
                    user_name=t.get('user_name', ''),
                    user_screen_name=t.get('user_screen_name', ''),
                    text=t.get('text', ''),
                    created_at=t.get('created_at'),
                    likes=t.get('likes', 0),
                    retweets=t.get('retweets', 0),
                    replies=t.get('replies', 0),
                    url=t.get('url', ''),
                    is_reply=True
                ))

        return replies

    async def scroll_for_more_tweets(self, times: int = 3) -> None:
        """Scroll page to load more tweets."""
        for i in range(times):
            self.client.execute_js(self.browser_id, "window.scrollBy(0, 800)")
            await asyncio.sleep(1.5)
