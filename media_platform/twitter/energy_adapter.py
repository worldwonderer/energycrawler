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
Twitter/X.com Energy Browser Adapter

This module provides an adapter for using the Energy browser service
with the Twitter/X.com platform for x-client-transaction-id generation
and cookie management.

Features:
- x-client-transaction-id generation via XClIdGen algorithm
- Energy browser integration for key extraction
- Cookie management (auth_token, ct0)
- Login state verification
- Transaction ID caching with TTL

The XClIdGen algorithm is based on:
https://github.com/vladkens/twscrape (MIT licensed)
https://github.com/iSarabjitDhiman/XClientTransaction (MIT licensed)
"""

import asyncio
import base64
import hashlib
import json
import math
import random
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import sys
import os
# Add parent directory to path for energy_client import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging

# Setup logger
logger = logging.getLogger(__name__)

import httpx
from bs4 import BeautifulSoup
from energy_client.browser_interface import BrowserInterface, Cookie, EnergyBrowserBackend


# MARK: Transaction ID Cache

@dataclass
class TransactionIdCacheEntry:
    """Transaction ID cache entry with TTL"""
    value: str
    created_at: float
    ttl: int


class TransactionIdCache:
    """
    Thread-safe LRU cache for transaction IDs with TTL.

    Transaction IDs are relatively short-lived but expensive to generate
    via browser JavaScript execution.
    """

    def __init__(self, max_size: int = 500, ttl: int = 60):
        """
        Initialize the transaction ID cache.

        Args:
            max_size: Maximum number of entries to cache (default 500)
            ttl: Time-to-live in seconds (default 60 seconds)
        """
        self._cache: OrderedDict[str, TransactionIdCacheEntry] = OrderedDict()
        self._lock = Lock()
        self._max_size = max_size
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def _make_key(self, method: str, path: str) -> str:
        """Generate cache key from method and path"""
        return f"{method}:{path}"

    def get(self, method: str, path: str) -> Optional[str]:
        """
        Get cached transaction ID if still valid.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path

        Returns:
            Cached transaction ID or None if expired/not found
        """
        key = self._make_key(method, path)
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry.created_at < entry.ttl:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return entry.value
                else:
                    del self._cache[key]
            self._misses += 1
            return None

    def set(self, method: str, path: str, value: str, ttl: Optional[int] = None) -> None:
        """
        Cache a transaction ID result.

        Args:
            method: HTTP method
            path: API path
            value: Transaction ID to cache
            ttl: Optional custom TTL (uses default if not provided)
        """
        key = self._make_key(method, path)
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = TransactionIdCacheEntry(
                value=value,
                created_at=time.time(),
                ttl=ttl if ttl is not None else self._ttl
            )

    def clear(self) -> None:
        """Clear all cached entries"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.2%}",
                "size": len(self._cache),
                "max_size": self._max_size,
            }


# MARK: Cubic Bezier Curve

class Cubic:
    """
    Cubic Bezier curve calculator for animation key generation.

    Code mostly taken from https://github.com/iSarabjitDhiman/XClientTransaction (MIT licensed)
    """

    def __init__(self, curves: List[float]):
        self.curves = curves

    def get_value(self, time: float) -> float:
        start_gradient = end_gradient = start = mid = 0.0
        end = 1.0

        if time <= 0.0:
            if self.curves[0] > 0.0:
                start_gradient = self.curves[1] / self.curves[0]
            elif self.curves[1] == 0.0 and self.curves[2] > 0.0:
                start_gradient = self.curves[3] / self.curves[2]
            return start_gradient * time

        if time >= 1.0:
            if self.curves[2] < 1.0:
                end_gradient = (self.curves[3] - 1.0) / (self.curves[2] - 1.0)
            elif self.curves[2] == 1.0 and self.curves[0] < 1.0:
                end_gradient = (self.curves[1] - 1.0) / (self.curves[0] - 1.0)
            return 1.0 + end_gradient * (time - 1.0)

        while start < end:
            mid = (start + end) / 2
            x_est = self.calculate(self.curves[0], self.curves[2], mid)
            if abs(time - x_est) < 0.00001:
                return self.calculate(self.curves[1], self.curves[3], mid)
            if x_est < time:
                start = mid
            else:
                end = mid
        return self.calculate(self.curves[1], self.curves[3], mid)

    @staticmethod
    def calculate(a: float, b: float, m: float) -> float:
        return 3.0 * a * (1 - m) * (1 - m) * m + 3.0 * b * (1 - m) * m * m + m * m * m


# MARK: Animation Key Helper Functions

def interpolate(from_list: List[float], to_list: List[float], f: float) -> List[float]:
    """Interpolate between two lists of values."""
    assert len(from_list) == len(to_list), f"Mismatched interpolation args {from_list}: {to_list}"
    return [a * (1 - f) + b * f for a, b in zip(from_list, to_list)]


def get_rotation_matrix(rotation: float) -> List[float]:
    """Get 2D rotation matrix values."""
    rad = math.radians(rotation)
    return [math.cos(rad), -math.sin(rad), math.sin(rad), math.cos(rad)]


def solve(value: float, min_val: float, max_val: float, rounding: bool) -> float:
    """Solve for value within range."""
    result = value * (max_val - min_val) / 255 + min_val
    return math.floor(result) if rounding else round(result, 2)


def float_to_hex(x: float) -> str:
    """Convert float to hex string."""
    result = []
    quotient = int(x)
    fraction = x - quotient

    while quotient > 0:
        quotient = int(x / 16)
        remainder = int(x - (float(quotient) * 16))

        if remainder > 9:
            result.insert(0, chr(remainder + 55))
        else:
            result.insert(0, str(remainder))

        x = float(quotient)

    if fraction == 0:
        return "".join(result)

    result.append(".")

    while fraction > 0:
        fraction *= 16
        integer = int(fraction)
        fraction -= float(integer)

        if integer > 9:
            result.append(chr(integer + 55))
        else:
            result.append(str(integer))

    return "".join(result)


def cacl_anim_key(frames: List[float], target_time: float) -> str:
    """
    Calculate animation key from frame data.

    Args:
        frames: Frame data containing color, rotation, and curve values
        target_time: Target time for animation

    Returns:
        Animation key string
    """
    from_color = [*frames[:3], 1]
    to_color = [*frames[3:6], 1]
    from_rotation = [0.0]
    to_rotation = [solve(frames[6], 60.0, 360.0, True)]

    frames = frames[7:]
    curves = [solve(x, -1.0 if i % 2 else 0.0, 1.0, False) for i, x in enumerate(frames)]
    val = Cubic(curves).get_value(target_time)

    color = interpolate(from_color, to_color, val)
    color = [value if value > 0 else 0 for value in color]
    rotation = interpolate(from_rotation, to_rotation, val)

    matrix = get_rotation_matrix(rotation[0])
    str_arr = [format(round(value), "x") for value in color[:-1]]
    for value in matrix:
        rounded = round(value, 2)
        if rounded < 0:
            rounded = -rounded
        hex_value = float_to_hex(rounded)
        str_arr.append(
            f"0{hex_value}".lower()
            if hex_value.startswith(".")
            else hex_value
            if hex_value
            else "0"
        )

    str_arr.extend(["0", "0"])
    return re.sub(r"[.-]", "", "".join(str_arr))


# MARK: Key Parsing Functions

# Regex for extracting animation indices from ondemand.s.js
INDICES_REGEX = re.compile(r"(\(\w{1}\[(\d{1,2})\],\s*16\))+", flags=(re.VERBOSE | re.MULTILINE))


def _get_ondemand_url(html: str) -> Optional[str]:
    """
    Extract ondemand.s.js URL from Twitter HTML.

    Tries regex extraction first (handles version format with or without 'a' suffix),
    falls back to JSON parse.

    Args:
        html: Raw HTML content of Twitter page

    Returns:
        Full URL to ondemand.s.js or None if not found
    """
    # Try regex extraction first (handles both "ondemand.s":"2ef3c62" and with 'a' suffix)
    pattern = r'"ondemand\.s":"([a-f0-9]+)"'
    match = re.search(pattern, html)
    if match:
        ver = match.group(1)
        return f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{ver}a.js"

    # Try JSON parse as fallback
    try:
        start_marker = 'e=>e+"."+'
        end_marker = '[e]+"a.js"'
        if start_marker in html and end_marker in html:
            json_part = html.split(start_marker)[1].split(end_marker)[0]
            scripts = json.loads(json_part)
            for k, v in scripts.items():
                if k == "ondemand.s":
                    return f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{v}a.js"
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        pass

    return None


def parse_vk_bytes_from_html(html: str) -> List[int]:
    """
    Parse verification key bytes from raw HTML.

    Args:
        html: Raw HTML content

    Returns:
        List of verification key bytes

    Raises:
        Exception: If verification key cannot be found
    """
    pattern = r'<meta[^>]*name=["\']twitter-site-verification["\'][^>]*content=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)

    if not match:
        raise Exception("Couldn't get XClientTxId key bytes from HTML")

    content = match.group(1)
    return list(base64.b64decode(content))


def parse_vk_bytes(soup: BeautifulSoup) -> List[int]:
    """
    Parse verification key bytes from Twitter page.

    Args:
        soup: BeautifulSoup object of Twitter page

    Returns:
        List of verification key bytes

    Raises:
        Exception: If verification key cannot be found
    """
    el = soup.find("meta", {"name": "twitter-site-verification", "content": True})
    el = str(el.get("content")) if el else None
    if not el:
        raise Exception("Couldn't get XClientTxId key bytes")

    return list(base64.b64decode(bytes(el, "utf-8")))


def parse_anim_arr_from_html(html: str, vk_bytes: List[int]) -> List[List[float]]:
    """
    Parse animation array from SVG elements in raw HTML.

    SVG animations are in the original HTML but may not appear in the
    browser-rendered DOM. This function uses regex to extract from raw HTML.

    Args:
        html: Raw HTML content of Twitter page
        vk_bytes: Verification key bytes

    Returns:
        List of animation frame arrays

    Raises:
        Exception: If animation array cannot be found
    """
    # Find all SVG with loading-x-anim id using regex
    pattern = r'<svg[^>]*id=["\']loading-x-anim-\d+["\'][^>]*>.*?</svg>'
    svgs = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

    if not svgs:
        raise Exception("Couldn't find SVG animations in HTML")

    # Extract path d attributes (second path in each SVG)
    els = []
    for svg in svgs:
        paths = re.findall(r'<path[^>]*d=["\']([^"\']+)["\']', svg)
        if len(paths) >= 2:
            els.append(paths[1])  # Second path (g:first-child path:nth-child(2))

    if not els:
        raise Exception("Couldn't find animation paths in SVGs")

    idx = vk_bytes[5] % len(els)
    dat = els[idx][9:].split("C")  # Remove "M " prefix and split by "C"
    arr = [list(map(float, re.sub(r"[^\d]+", " ", x).split())) for x in dat]
    return arr


def parse_anim_arr(soup: BeautifulSoup, vk_bytes: List[int]) -> List[List[float]]:
    """
    Parse animation array from SVG elements (BeautifulSoup version - fallback).

    Args:
        soup: BeautifulSoup object of Twitter page
        vk_bytes: Verification key bytes

    Returns:
        List of animation frame arrays

    Raises:
        Exception: If animation array cannot be found
    """
    els = list(soup.select("svg[id^='loading-x-anim'] g:first-child path:nth-child(2)"))
    els = [str(x.get("d") or "").strip() for x in els]
    if not els:
        raise Exception("Couldn't get XClientTxId animation array")

    idx = vk_bytes[5] % len(els)
    dat = els[idx][9:].split("C")
    arr = [list(map(float, re.sub(r"[^\d]+", " ", x).split())) for x in dat]
    return arr


def parse_anim_idx(js_content: str) -> List[int]:
    """
    Parse animation indices from ondemand.s.js content.

    Args:
        js_content: JavaScript content from ondemand.s.js

    Returns:
        List of animation indices

    Raises:
        Exception: If indices cannot be found
    """
    items = [int(x.group(2)) for x in INDICES_REGEX.finditer(js_content)]
    if not items:
        raise Exception("Couldn't get XClientTxId indices")
    return items


# MARK: XClIdGen Class

class XClIdGen:
    """
    X-Client-Transaction-ID generator for Twitter/X.com.

    This class implements the algorithm for generating x-client-transaction-id
    headers required by Twitter's API.

    Based on:
    - https://github.com/vladkens/twscrape (MIT licensed)
    - https://github.com/iSarabjitDhiman/XClientTransaction (MIT licensed)
    """

    def __init__(self, vk_bytes: List[int], anim_key: str):
        """
        Initialize the transaction ID generator.

        Args:
            vk_bytes: Verification key bytes from Twitter page
            anim_key: Animation key calculated from SVG frames
        """
        self.vk_bytes = vk_bytes
        self.anim_key = anim_key

    def calc(self, method: str, path: str) -> str:
        """
        Calculate x-client-transaction-id for a request.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path

        Returns:
            x-client-transaction-id string
        """
        ts = math.floor((time.time() * 1000 - 1682924400 * 1000) / 1000)
        ts_bytes = [(ts >> (i * 8)) & 0xFF for i in range(4)]

        dkw, drn = "obfiowerehiring", 3  # default keyword and random number
        pld = f"{method.upper()}!{path}!{ts}{dkw}{self.anim_key}"
        pld = list(hashlib.sha256(pld.encode()).digest())
        pld = [*self.vk_bytes, *ts_bytes, *pld[:16], drn]

        num = random.randint(0, 255)
        pld = bytearray([num, *[x ^ num for x in pld]])
        out = base64.b64encode(pld).decode("utf-8").strip("=")
        return out


# MARK: TwitterEnergyAdapter Class

class TwitterEnergyAdapter:
    """
    Energy browser adapter for Twitter/X.com platform.

    This adapter provides methods to interact with the Energy browser
    service for Twitter x-client-transaction-id generation and cookie management.

    Features:
    - x-client-transaction-id generation via XClIdGen algorithm
    - Energy browser integration for key extraction
    - Cookie management (auth_token, ct0)
    - Thread-safe operations with caching
    - Login state verification
    """

    # Twitter URLs
    TWITTER_BASE_URL = "https://x.com"
    TWITTER_HOME_URL = "https://x.com/home"
    TWITTER_LOGIN_URL = "https://x.com/login"

    # Authentication cookie names
    AUTH_COOKIE_NAME = "auth_token"
    CSRF_COOKIE_NAME = "ct0"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY_MS = 200
    DEFAULT_RETRY_BACKOFF_FACTOR = 2.0

    def __init__(
        self,
        browser_backend: BrowserInterface,
        browser_id: str = "twitter_browser",
        enable_cache: bool = True,
        cache_ttl: int = 60,
        cache_max_size: int = 500,
    ):
        """
        Initialize the Twitter Energy adapter.

        Args:
            browser_backend: BrowserInterface implementation (e.g., EnergyBrowserBackend)
            browser_id: Unique identifier for the browser instance
            enable_cache: Whether to enable transaction ID caching
            cache_ttl: Cache TTL in seconds (default 60 seconds)
            cache_max_size: Maximum number of cached transaction IDs
        """
        self.browser = browser_backend
        self.browser_id = browser_id

        # Transaction ID cache
        self._enable_cache = enable_cache
        self._transaction_id_cache = TransactionIdCache(
            max_size=cache_max_size,
            ttl=cache_ttl
        ) if enable_cache else None

        # User agent cache
        self._user_agent: Optional[str] = None

        # Connection state
        self._initialized = False

        # Retry configuration
        self._max_retries = self.DEFAULT_MAX_RETRIES
        self._retry_delay_ms = self.DEFAULT_RETRY_DELAY_MS
        self._retry_backoff_factor = self.DEFAULT_RETRY_BACKOFF_FACTOR

        # XClIdGen instance for transaction ID generation
        self._xclid_gen: Optional[XClIdGen] = None

    def connect(self) -> None:
        """Connect to the browser backend."""
        if hasattr(self.browser, 'connect'):
            self.browser.connect()

    def disconnect(self) -> None:
        """Disconnect from the browser backend."""
        if hasattr(self.browser, 'disconnect'):
            self.browser.disconnect()

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    # ==================== Configuration Methods ====================

    def set_retry_config(
        self,
        max_retries: int = 3,
        retry_delay_ms: int = 200,
        backoff_factor: float = 2.0
    ) -> None:
        """
        Configure retry behavior for transaction ID generation.

        Args:
            max_retries: Maximum number of retry attempts
            retry_delay_ms: Initial delay between retries in milliseconds
            backoff_factor: Multiplier for delay after each retry
        """
        self._max_retries = max_retries
        self._retry_delay_ms = retry_delay_ms
        self._retry_backoff_factor = backoff_factor

    def clear_cache(self) -> None:
        """Clear all cached data"""
        if self._transaction_id_cache:
            self._transaction_id_cache.clear()
        self._user_agent = None
        self._xclid_gen = None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self._transaction_id_cache:
            return {"enabled": False}
        return {
            "enabled": True,
            **self._transaction_id_cache.stats()
        }

    # ==================== Browser Initialization ====================

    async def initialize(self, headless: bool = True) -> bool:
        """
        Initialize the browser and navigate to Twitter.

        Args:
            headless: Whether to run in headless mode

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create browser instance
            self.browser.create_browser(self.browser_id, headless=headless)

            # Navigate to Twitter
            self.browser.navigate(self.browser_id, self.TWITTER_BASE_URL, timeout_ms=30000)

            # Wait for page to load
            await asyncio.sleep(2)

            self._initialized = True
            logger.info(f"[TwitterEnergyAdapter] Browser initialized with browser_id={self.browser_id}")
            return True

        except Exception as e:
            logger.error(f"[TwitterEnergyAdapter] Failed to initialize browser: {e}")
            return False

    async def ensure_initialized(self) -> bool:
        """
        Ensure browser is initialized.

        Returns:
            True if initialized, False otherwise
        """
        if not self._initialized:
            return await self.initialize()
        return True

    # ==================== JavaScript Execution ====================

    def _execute_js_raw(self, script: str) -> str:
        """
        Execute JavaScript and return raw string result.

        This method directly calls the browser backend's execute_js
        without JSON parsing.

        Args:
            script: JavaScript code to execute

        Returns:
            Raw string result from JavaScript execution
        """
        # Directly access the underlying client to get raw result
        if hasattr(self.browser, '_client'):
            client = self.browser._client
            return client.execute_js(self.browser_id, script)
        else:
            result = self.browser.execute_js(self.browser_id, script)
            return result if isinstance(result, str) else str(result) if result else ""

    # ==================== Key Extraction Methods ====================

    async def _get_page_html(self, url: str = "https://x.com/tesla") -> str:
        """
        Get page HTML content via httpx (raw HTML, not rendered DOM).

        SVG animations are in original HTML but removed after React hydration.
        We need raw HTML to extract these elements.

        Args:
            url: URL to fetch

        Returns:
            HTML content string
        """
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    async def _get_ondemand_js_content(self, html: str) -> str:
        """
        Get ondemand.s.js content from Twitter page.

        Uses regex to extract ondemand.s URL from HTML JSON mapping,
        then fetches the JS content via browser.

        Args:
            html: HTML content of Twitter page

        Returns:
            JavaScript content of ondemand.s.js
        """
        # Extract ondemand.s.js URL
        ondemand_url = _get_ondemand_url(html)

        if not ondemand_url:
            # Try to find in script tags as fallback
            soup = BeautifulSoup(html, "html.parser")
            scripts = soup.find_all("script", src=True)
            for script in scripts:
                src = script.get("src", "")
                if "ondemand.s." in src and src.endswith(".js"):
                    ondemand_url = src
                    break

        if not ondemand_url:
            raise Exception("Couldn't find ondemand.s.js URL")

        logger.debug(f"[TwitterEnergyAdapter] Found ondemand.s.js URL: {ondemand_url}")

        # Fetch the JavaScript content via browser
        js_content = await self._fetch_js_via_browser(ondemand_url)

        if not js_content:
            raise Exception("Couldn't fetch ondemand.s.js content")

        logger.debug(f"[TwitterEnergyAdapter] Fetched ondemand.s.js content: {len(js_content)} bytes")
        return js_content

    async def _fetch_js_via_browser(self, url: str) -> str:
        """
        Fetch JS content via browser fetch API.

        Args:
            url: URL to fetch

        Returns:
            JavaScript content string
        """
        # Use browser to fetch the content
        self._execute_js_raw(f"""
        window.__jsContent = '';
        fetch('{url}')
            .then(r => r.text())
            .then(text => {{ window.__jsContent = text; }})
            .catch(e => {{ window.__jsContent = ''; }});
        """)

        # Wait for fetch to complete
        await asyncio.sleep(3)

        # Get the content
        js_content = self._execute_js_raw("window.__jsContent || ''")
        js_content = js_content.strip('"').strip("'")

        return js_content

    async def _init_xclid_gen(self) -> XClIdGen:
        """
        Initialize XClIdGen by extracting keys from Twitter page.

        Returns:
            Initialized XClIdGen instance
        """
        # Get Twitter page HTML via httpx (raw HTML with SVG animations)
        html = await self._get_page_html("https://x.com/tesla")

        # Parse verification key bytes from raw HTML
        vk_bytes = parse_vk_bytes_from_html(html)
        logger.debug(f"[TwitterEnergyAdapter] Parsed vk_bytes: {vk_bytes[:5]}...")

        # Parse animation array from raw HTML
        anim_arr = parse_anim_arr_from_html(html, vk_bytes)
        logger.debug(f"[TwitterEnergyAdapter] Parsed anim_arr with {len(anim_arr)} frames")

        # Get ondemand.s.js URL and fetch content
        ondemand_url = _get_ondemand_url(html)
        if not ondemand_url:
            raise Exception("Couldn't find ondemand.s.js URL")

        # Use browser to fetch JS (to avoid CORS and fingerprinting issues)
        # First ensure browser is initialized
        await self.ensure_initialized()
        js_content = await self._fetch_js_via_browser(ondemand_url)

        # Parse animation indices
        anim_idx = parse_anim_idx(js_content)
        logger.debug(f"[TwitterEnergyAdapter] Parsed anim_idx: {anim_idx}")

        # Calculate animation key
        frame_time = 1
        for x in anim_idx[1:]:
            frame_time *= vk_bytes[x] % 16

        frame_idx = vk_bytes[anim_idx[0]] % 16
        frame_row = anim_arr[frame_idx]
        frame_dur = float(frame_time) / 4096

        anim_key = cacl_anim_key(frame_row, frame_dur)
        logger.debug(f"[TwitterEnergyAdapter] Calculated anim_key: {anim_key}")

        # Create XClIdGen instance
        self._xclid_gen = XClIdGen(vk_bytes, anim_key)
        return self._xclid_gen

    # ==================== Transaction ID Generation ====================

    async def generate_transaction_id(
        self,
        method: str,
        path: str,
        use_cache: bool = True
    ) -> str:
        """
        Generate x-client-transaction-id using XClIdGen algorithm.

        The x-client-transaction-id is generated using Twitter's algorithm
        based on method + path + timestamp + verification keys.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path
            use_cache: Whether to use cached result if available

        Returns:
            x-client-transaction-id string
        """
        # Check cache first
        if use_cache and self._transaction_id_cache:
            cached = self._transaction_id_cache.get(method, path)
            if cached is not None:
                logger.debug(f"[TwitterEnergyAdapter] Cache hit for transaction ID: {method} {path}")
                return cached

        # Ensure browser is initialized
        await self.ensure_initialized()

        # Initialize XClIdGen if not already done
        if self._xclid_gen is None:
            try:
                await self._init_xclid_gen()
            except Exception as e:
                logger.error(f"[TwitterEnergyAdapter] Failed to initialize XClIdGen: {e}")
                raise

        # Generate transaction ID
        transaction_id = self._xclid_gen.calc(method, path)

        # Cache successful result
        if use_cache and self._transaction_id_cache:
            self._transaction_id_cache.set(method, path, transaction_id)

        logger.debug(f"[TwitterEnergyAdapter] Generated transaction ID: {transaction_id[:20]}...")
        return transaction_id

    async def refresh_transaction_id(self, method: str, path: str) -> str:
        """
        Force refresh transaction ID by making a new request.

        Args:
            method: HTTP method
            path: API path

        Returns:
            Fresh transaction ID string
        """
        # Invalidate cache
        if self._transaction_id_cache:
            key = f"{method}:{path}"
            with self._transaction_id_cache._lock:
                self._transaction_id_cache._cache.pop(key, None)

        return await self.generate_transaction_id(method, path, use_cache=False)

    # ==================== Cookie Management ====================

    def get_cookies(self, domain: str = ".x.com") -> Dict[str, str]:
        """
        Get cookies for Twitter domain.

        Args:
            domain: Cookie domain to filter by

        Returns:
            Dictionary of cookie name -> value pairs
        """
        cookies = self.browser.get_cookies(self.browser_id, self.TWITTER_BASE_URL)
        return {c.name: c.value for c in cookies if domain in c.domain or not c.domain}

    def get_all_cookies(self) -> List[Dict[str, Any]]:
        """
        Get all cookies as a list of dictionaries.

        Returns:
            List of cookie dictionaries
        """
        cookies = self.browser.get_cookies(self.browser_id, self.TWITTER_BASE_URL)
        return [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "secure": c.secure,
                "httpOnly": c.http_only
            }
            for c in cookies
        ]

    def set_cookies(self, cookies: List[Dict[str, str]], domain: str = ".x.com") -> bool:
        """
        Set cookies in the browser.

        Args:
            cookies: List of cookie dictionaries with name, value, etc.
            domain: Default domain for cookies

        Returns:
            True if successful
        """
        cookie_objects = []
        for c in cookies:
            cookie_objects.append(Cookie(
                name=c.get("name", ""),
                value=c.get("value", ""),
                domain=c.get("domain", domain),
                path=c.get("path", "/"),
                secure=c.get("secure", True),
                http_only=c.get("httpOnly", False)
            ))

        return self.browser.set_cookies(self.browser_id, cookie_objects)

    def set_cookies_from_dict(self, cookies_dict: Dict[str, str], domain: str = ".x.com") -> bool:
        """
        Set cookies from a simple name-value dictionary.

        Args:
            cookies_dict: Dictionary of cookie name -> value
            domain: Domain for cookies

        Returns:
            True if successful
        """
        cookies = [
            {"name": name, "value": value, "domain": domain}
            for name, value in cookies_dict.items()
        ]
        return self.set_cookies(cookies, domain)

    # ==================== Authentication ====================

    def get_auth_cookies(self) -> Dict[str, str]:
        """
        Get authentication cookies (auth_token, ct0).

        Returns:
            Dictionary with auth_token and ct0 if present
        """
        all_cookies = self.get_cookies()
        auth_cookies = {}

        if self.AUTH_COOKIE_NAME in all_cookies:
            auth_cookies[self.AUTH_COOKIE_NAME] = all_cookies[self.AUTH_COOKIE_NAME]

        if self.CSRF_COOKIE_NAME in all_cookies:
            auth_cookies[self.CSRF_COOKIE_NAME] = all_cookies[self.CSRF_COOKIE_NAME]

        return auth_cookies

    def check_login_state(self) -> bool:
        """
        Check if user is logged in by checking for auth_token cookie.

        Returns:
            True if logged in, False otherwise
        """
        cookies = self.get_cookies()
        return self.AUTH_COOKIE_NAME in cookies and bool(cookies[self.AUTH_COOKIE_NAME])

    async def verify_login_via_page(self) -> bool:
        """
        Verify login state by checking page content.

        Returns:
            True if logged in, False otherwise
        """
        try:
            # Navigate to home page
            self.browser.navigate(self.browser_id, self.TWITTER_HOME_URL, timeout_ms=15000)
            await asyncio.sleep(2)

            # Check if we're redirected to login page
            script = """
            (function() {
                // Check if we're on login page
                if (window.location.pathname === '/login') {
                    return false;
                }

                // Check for logged-in user indicators
                const profileLink = document.querySelector('a[href*="/home"]');
                if (profileLink) {
                    return true;
                }

                // Check for react root with logged-in state
                const reactRoot = document.querySelector('#react-root');
                if (reactRoot && reactRoot.getAttribute('data-logged-in') === 'true') {
                    return true;
                }

                return false;
            })();
            """

            result = self._execute_js_raw(script)
            return result and result.lower() == 'true'

        except Exception as e:
            logger.warning(f"[TwitterEnergyAdapter] Failed to verify login via page: {e}")
            return False

    # ==================== User Agent ====================

    async def get_user_agent(self) -> str:
        """
        Get browser user agent.

        Returns:
            User agent string
        """
        if self._user_agent:
            return self._user_agent

        script = "navigator.userAgent"
        result = self._execute_js_raw(script)

        if result:
            self._user_agent = result.strip('"').strip("'")
            return self._user_agent

        # Fallback to a common user agent
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    # ==================== Utility Methods ====================

    async def navigate(self, url: str, wait_until: str = "networkidle") -> bool:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition (not used in Energy backend)

        Returns:
            True if successful
        """
        try:
            status = self.browser.navigate(self.browser_id, url, timeout_ms=30000)
            await asyncio.sleep(2)  # Wait for page to stabilize
            return status == 200
        except Exception as e:
            logger.error(f"[TwitterEnergyAdapter] Navigation failed: {e}")
            return False

    async def execute_js(self, script: str) -> Any:
        """
        Execute JavaScript in browser context.

        Args:
            script: JavaScript code to execute

        Returns:
            Result of script execution
        """
        return self._execute_js_raw(script)

    async def refresh_page(self) -> bool:
        """
        Refresh the current page.

        Returns:
            True if successful
        """
        script = "location.reload()"
        try:
            self._execute_js_raw(script)
            await asyncio.sleep(2)
            return True
        except Exception as e:
            logger.error(f"[TwitterEnergyAdapter] Page refresh failed: {e}")
            return False


def create_twitter_energy_adapter(
    host: str = 'localhost',
    port: int = 50051,
    browser_id: str = "twitter_browser",
    headless: bool = True,
    enable_cache: bool = True,
    cache_ttl: int = 60,
    cache_max_size: int = 500,
) -> TwitterEnergyAdapter:
    """
    Factory function to create a Twitter Energy adapter.

    This creates a fully configured adapter with browser instance
    already initialized and navigated to Twitter.

    Args:
        host: Energy service host
        port: Energy service port
        browser_id: Browser instance ID
        headless: Whether to run browser in headless mode
        enable_cache: Whether to enable transaction ID caching
        cache_ttl: Cache TTL in seconds
        cache_max_size: Maximum cache entries

    Returns:
        Configured TwitterEnergyAdapter instance
    """
    backend = EnergyBrowserBackend(host=host, port=port)
    adapter = TwitterEnergyAdapter(
        backend,
        browser_id,
        enable_cache=enable_cache,
        cache_ttl=cache_ttl,
        cache_max_size=cache_max_size
    )

    # Connect and create browser
    adapter.connect()
    backend.create_browser(browser_id, headless=headless)

    # Navigate to Twitter to initialize the page context
    backend.navigate(browser_id, TwitterEnergyAdapter.TWITTER_BASE_URL, timeout_ms=30000)

    logger.info(f"[TwitterEnergyAdapter] Created adapter with browser_id={browser_id}")

    return adapter
