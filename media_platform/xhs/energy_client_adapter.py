# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
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

"""
XHS Energy Client Adapter

This module provides an adapter for using the Energy browser service
with the Xiaohongshu (XHS) platform for signature generation.

Features:
- Signature generation via Energy browser IPC
- Signature caching with TTL (LRU eviction)
- Retry logic with exponential backoff
- b1 cache management with automatic refresh
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import sys
import os
# Add parent directory to path for energy_client import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from energy_client.browser_interface import BrowserInterface, Cookie, EnergyBrowserBackend
try:
    from .xhs_sign import b64_encode, encode_utf8, get_trace_id, mrc, build_sign_string
except ImportError:
    from media_platform.xhs.xhs_sign import b64_encode, encode_utf8, get_trace_id, mrc, build_sign_string
from tools import utils


def _md5_hex(s: str) -> str:
    """Calculate MD5 hash value"""
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _build_xs_payload(x3_value: str, data_type: str = "object") -> str:
    """Build x-s signature"""
    s = {
        "x0": "4.2.1",
        "x1": "xhs-pc-web",
        "x2": "Mac OS",
        "x3": x3_value,
        "x4": data_type,
    }
    return "XYS_" + b64_encode(encode_utf8(json.dumps(s, separators=(",", ":"))))


def _build_xs_common(a1: str, b1: str, x_s: str, x_t: str) -> str:
    """Build x-s-common request header"""
    payload = {
        "s0": 3,
        "s1": "",
        "x0": "1",
        "x1": "4.2.2",
        "x2": "Mac OS",
        "x3": "xhs-pc-web",
        "x4": "4.74.0",
        "x5": a1,
        "x6": x_t,
        "x7": x_s,
        "x8": b1,
        "x9": mrc(x_t + x_s + b1),
        "x10": 154,
        "x11": "normal",
    }
    return b64_encode(encode_utf8(json.dumps(payload, separators=(",", ":"))))


@dataclass
class CacheEntry:
    """Signature cache entry with TTL"""
    value: str
    created_at: float
    ttl: int


class SignatureCache:
    """
    Thread-safe LRU cache for signature results with TTL.

    Signatures are expensive to compute but short-lived.
    This cache helps reduce redundant signature calls.
    """

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """
        Initialize the signature cache.

        Args:
            max_size: Maximum number of entries to cache (default 1000)
            ttl: Time-to-live in seconds (default 5 minutes)
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = Lock()
        self._max_size = max_size
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def _make_key(self, sign_str: str, md5_str: str) -> str:
        """Generate cache key from sign parameters"""
        return f"{md5_str}:{hash(sign_str) % 1000000}"

    def get(self, sign_str: str, md5_str: str) -> Optional[str]:
        """
        Get cached signature if still valid.

        Args:
            sign_str: Original sign string
            md5_str: MD5 hash of sign string

        Returns:
            Cached signature or None if expired/not found
        """
        key = self._make_key(sign_str, md5_str)
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

    def set(self, sign_str: str, md5_str: str, value: str, ttl: Optional[int] = None) -> None:
        """
        Cache a signature result.

        Args:
            sign_str: Original sign string
            md5_str: MD5 hash of sign string
            value: Signature result to cache
            ttl: Optional custom TTL (uses default if not provided)
        """
        key = self._make_key(sign_str, md5_str)
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(
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


class XHSEnergyAdapter:
    """
    Energy browser adapter for Xiaohongshu platform.

    This adapter provides methods to interact with the Energy browser
    service for XHS signature generation and cookie management.

    Features:
    - Signature generation with caching and retry logic
    - b1 value caching with automatic refresh
    - Thread-safe operations
    """

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY_MS = 100
    DEFAULT_RETRY_BACKOFF_FACTOR = 2.0

    def __init__(
        self,
        browser_backend: BrowserInterface,
        browser_id: str = "xhs_browser",
        enable_cache: bool = True,
        cache_ttl: int = 300,
        cache_max_size: int = 1000,
    ):
        """
        Initialize the XHS Energy adapter.

        Args:
            browser_backend: BrowserInterface implementation (e.g., EnergyBrowserBackend)
            browser_id: Unique identifier for the browser instance
            enable_cache: Whether to enable signature caching
            cache_ttl: Cache TTL in seconds (default 5 minutes)
            cache_max_size: Maximum number of cached signatures
        """
        self.browser = browser_backend
        self.browser_id = browser_id

        # b1 cache
        self._b1_cache: Optional[str] = None
        self._b1_cache_time: float = 0
        self._b1_cache_ttl: int = 3600  # 1 hour TTL for b1

        # Signature cache
        self._enable_cache = enable_cache
        self._signature_cache = SignatureCache(
            max_size=cache_max_size,
            ttl=cache_ttl
        ) if enable_cache else None

        # Retry configuration
        self._max_retries = self.DEFAULT_MAX_RETRIES
        self._retry_delay_ms = self.DEFAULT_RETRY_DELAY_MS
        self._retry_backoff_factor = self.DEFAULT_RETRY_BACKOFF_FACTOR

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
        retry_delay_ms: int = 100,
        backoff_factor: float = 2.0
    ) -> None:
        """
        Configure retry behavior for signature generation.

        Args:
            max_retries: Maximum number of retry attempts
            retry_delay_ms: Initial delay between retries in milliseconds
            backoff_factor: Multiplier for delay after each retry
        """
        self._max_retries = max_retries
        self._retry_delay_ms = retry_delay_ms
        self._retry_backoff_factor = backoff_factor

    def clear_cache(self) -> None:
        """Clear all cached data (signatures and b1)"""
        self._b1_cache = None
        self._b1_cache_time = 0
        if self._signature_cache:
            self._signature_cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self._signature_cache:
            return {"enabled": False}
        return {
            "enabled": True,
            **self._signature_cache.stats()
        }

    # ==================== b1 Management ====================

    async def get_b1_from_localstorage(self, force_refresh: bool = False) -> str:
        """
        Get b1 value from localStorage via JavaScript execution.

        The b1 value is cached for 1 hour by default to avoid
        repeated localStorage access.

        Args:
            force_refresh: Force refresh from browser even if cached

        Returns:
            b1 value string, empty string if not found or error
        """
        current_time = time.time()

        # Return cached value if still valid
        if not force_refresh and self._b1_cache:
            if current_time - self._b1_cache_time < self._b1_cache_ttl:
                return self._b1_cache

        try:
            script = "JSON.stringify(window.localStorage)"
            result = self._execute_js_raw(script)

            if result:
                # Parse the localStorage JSON string
                # The result might be double-encoded (JSON string of JSON string)
                local_storage = json.loads(result) if isinstance(result, str) else result

                # If still a string, parse again (double-encoded)
                if isinstance(local_storage, str):
                    local_storage = json.loads(local_storage)

                # Handle case where parsed result might not be a dict
                if not isinstance(local_storage, dict):
                    utils.logger.warning(f"[XHSEnergyAdapter] localStorage is not a dict, got: {type(local_storage)}")
                    return self._b1_cache or ""

                # b1 is stored directly in localStorage
                b1_value = local_storage.get("b1", "")

                if b1_value:
                    self._b1_cache = b1_value
                    self._b1_cache_time = current_time
                    return b1_value

                utils.logger.debug(f"[XHSEnergyAdapter] b1 not found in localStorage, keys: {list(local_storage.keys())[:10]}")
        except Exception as e:
            utils.logger.warning(f"[XHSEnergyAdapter] Failed to get b1 from localStorage: {e}")
            import traceback
            utils.logger.debug(f"[XHSEnergyAdapter] Traceback: {traceback.format_exc()}")

        # Return cached value even if expired, better than nothing
        return self._b1_cache or ""

    # ==================== JavaScript Execution ====================

    def _execute_js_raw(self, script: str) -> str:
        """
        Execute JavaScript and return raw string result.

        This method directly calls the browser backend's execute_js
        without JSON parsing, since some results (like mnsv2) return
        plain strings.

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

    # ==================== Signature Execution ====================

    async def execute_signature(
        self,
        sign_str: str,
        md5_str: str,
        use_cache: bool = True
    ) -> str:
        """
        Execute XHS signature generation using Energy browser service.

        Implements caching and retry logic with exponential backoff.

        Args:
            sign_str: String to be signed (uri + JSON.stringify(data))
            md5_str: MD5 hash value of sign_str
            use_cache: Whether to use cached result if available

        Returns:
            Signature string returned by the browser
        """
        # Check cache first
        if use_cache and self._signature_cache:
            cached = self._signature_cache.get(sign_str, md5_str)
            if cached is not None:
                utils.logger.debug(f"[XHSEnergyAdapter] Cache hit for signature")
                return cached

        # Escape the strings for JavaScript
        sign_str_escaped = sign_str.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        md5_str_escaped = md5_str.replace("\\", "\\\\").replace("'", "\\'")

        script = f"window.mnsv2('{sign_str_escaped}', '{md5_str_escaped}')"

        # Retry loop with exponential backoff
        last_error: Optional[Exception] = None
        delay_ms = self._retry_delay_ms

        for attempt in range(self._max_retries):
            try:
                result = self._execute_js_raw(script)

                if result:
                    # Remove surrounding quotes from the result (mnsv2 returns quoted string)
                    result = result.strip('"').strip("'")
                    # Cache successful result
                    if use_cache and self._signature_cache:
                        self._signature_cache.set(sign_str, md5_str, result)
                    return result

                last_error = Exception("mnsv2 returned empty result")

            except Exception as e:
                last_error = e
                utils.logger.warning(
                    f"[XHSEnergyAdapter] Signature attempt {attempt + 1}/{self._max_retries} failed: {e}"
                )

            # Wait before retry (except on last attempt)
            if attempt < self._max_retries - 1:
                await asyncio.sleep(delay_ms / 1000.0)
                delay_ms = int(delay_ms * self._retry_backoff_factor)

        utils.logger.error(
            f"[XHSEnergyAdapter] All {self._max_retries} signature attempts failed"
        )
        # Return empty string on failure (consistent with original behavior)
        return ""

    async def execute_signature_with_fallback(
        self,
        sign_str: str,
        md5_str: str
    ) -> str:
        """
        Execute signature via Energy browser.

        Args:
            sign_str: String to be signed
            md5_str: MD5 hash value

        Returns:
            Signature string
        """
        return await self.execute_signature(sign_str, md5_str)

    # ==================== High-Level Signature Methods ====================

    async def sign_xs_with_energy(
        self,
        uri: str,
        data: Optional[Union[Dict, str]] = None,
        method: str = "POST",
    ) -> str:
        """
        Generate x-s signature via Energy browser.

        Args:
            uri: API path, e.g., "/api/sns/web/v1/search/notes"
            data: Request data (GET params or POST payload)
            method: Request method (GET or POST)

        Returns:
            x-s signature string
        """
        sign_str = build_sign_string(uri, data, method)
        md5_str = _md5_hex(sign_str)
        x3_value = await self.execute_signature(sign_str, md5_str)
        data_type = "object" if isinstance(data, (dict, list)) else "string"
        return _build_xs_payload(x3_value, data_type)

    async def sign_with_energy(
        self,
        uri: str,
        data: Optional[Union[Dict, str]] = None,
        a1: str = "",
        method: str = "POST",
    ) -> Dict[str, Any]:
        """
        Generate complete signature request headers via Energy browser.

        Args:
            uri: API path
            data: Request data
            a1: a1 value from cookie
            method: Request method (GET or POST)

        Returns:
            Dictionary containing x-s, x-t, x-s-common, x-b3-traceid
        """
        b1 = await self.get_b1_from_localstorage()
        x_s = await self.sign_xs_with_energy(uri, data, method)
        x_t = str(int(time.time() * 1000))

        return {
            "x-s": x_s,
            "x-t": x_t,
            "x-s-common": _build_xs_common(a1, b1, x_s, x_t),
            "x-b3-traceid": get_trace_id(),
        }

    async def pre_headers_with_energy(
        self,
        url: str,
        cookie_dict: Dict[str, str],
        params: Optional[Dict] = None,
        payload: Optional[Dict] = None,
    ) -> Dict[str, str]:
        """
        Generate request header signature using Energy browser.

        This method can directly replace the _pre_headers method in client.py
        when using Energy browser backend.

        Args:
            url: Request URL
            cookie_dict: Cookie dictionary
            params: GET request parameters
            payload: POST request parameters

        Returns:
            Signed request header dictionary
        """
        a1_value = cookie_dict.get("a1", "")
        uri = urlparse(url).path

        # Determine request data and method
        if params is not None:
            data = params
            method = "GET"
        elif payload is not None:
            data = payload
            method = "POST"
        else:
            raise ValueError("params or payload is required")

        signs = await self.sign_with_energy(uri, data, a1_value, method)

        return {
            "X-S": signs["x-s"],
            "X-T": signs["x-t"],
            "x-S-Common": signs["x-s-common"],
            "X-B3-Traceid": signs["x-b3-traceid"],
        }

    # ==================== Cookie Management ====================

    def get_cookies(self, domain: str = ".xiaohongshu.com") -> Dict[str, str]:
        """
        Get cookies for XHS domain.

        Args:
            domain: Cookie domain to filter by

        Returns:
            Dictionary of cookie name -> value pairs
        """
        url = "https://www.xiaohongshu.com"
        cookies = self.browser.get_cookies(self.browser_id, url)
        return {c.name: c.value for c in cookies if domain in c.domain or not c.domain}

    def set_cookies(self, cookies: List[Dict[str, str]], domain: str = ".xiaohongshu.com") -> bool:
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
                secure=c.get("secure", False),
                http_only=c.get("httpOnly", False)
            ))

        return self.browser.set_cookies(self.browser_id, cookie_objects)

def create_xhs_energy_adapter(
    host: str = 'localhost',
    port: int = 50051,
    browser_id: str = "xhs_browser",
    headless: bool = True,
    enable_cache: bool = True,
    cache_ttl: int = 300,
    cache_max_size: int = 1000,
) -> XHSEnergyAdapter:
    """
    Factory function to create an XHS Energy adapter.

    This creates a fully configured adapter with browser instance
    already initialized and navigated to XHS.

    Args:
        host: Energy service host
        port: Energy service port
        browser_id: Browser instance ID
        headless: Whether to run browser in headless mode
        enable_cache: Whether to enable signature caching
        cache_ttl: Cache TTL in seconds
        cache_max_size: Maximum cache entries

    Returns:
        Configured XHSEnergyAdapter instance
    """
    backend = EnergyBrowserBackend(host=host, port=port)
    adapter = XHSEnergyAdapter(
        backend,
        browser_id,
        enable_cache=enable_cache,
        cache_ttl=cache_ttl,
        cache_max_size=cache_max_size
    )

    # Connect and create browser
    adapter.connect()
    backend.create_browser(browser_id, headless=headless)

    # Navigate to XHS to initialize the page context
    backend.navigate(browser_id, "https://www.xiaohongshu.com")

    utils.logger.info(f"[XHSEnergyAdapter] Created adapter with browser_id={browser_id}")

    return adapter
