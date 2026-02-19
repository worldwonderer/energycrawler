"""
E2E tests for XHS Energy adapter

Tests the XHS-specific Energy integration including:
- Signature generation with caching
- Cookie management
- Login flow (mocked)
- High-level adapter interface

Note: Tests import directly from module files to avoid package-level side effects
when running standalone E2E tests.
"""

import pytest
import asyncio
import time
import sys
import os
import importlib.util

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'energy_client'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from energy_client.browser_interface import Cookie, EnergyBrowserBackend


def _import_adapter_module():
    """
    Import the energy_client_adapter module directly without going through
    the media_platform.xhs package.

    Returns None if required dependencies are not available.
    """
    adapter_path = os.path.join(
        os.path.dirname(__file__),
        '..', '..',
        'media_platform', 'xhs', 'energy_client_adapter.py'
    )
    adapter_path = os.path.abspath(adapter_path)

    spec = importlib.util.spec_from_file_location('energy_client_adapter', adapter_path)
    module = importlib.util.module_from_spec(spec)

    # Set up necessary modules for the adapter's imports
    # Mock tools.utils if not available
    if 'tools' not in sys.modules:
        class MockLogger:
            def debug(self, *args): pass
            def warning(self, *args): pass
            def error(self, *args): pass
            def info(self, *args): pass

        mock_tools = type(sys)('tools')
        mock_utils = type('utils', (), {'logger': MockLogger()})()
        mock_tools.utils = mock_utils
        sys.modules['tools'] = mock_tools

    # Import xhs_sign module directly
    xhs_sign_path = os.path.join(
        os.path.dirname(__file__),
        '..', '..',
        'media_platform', 'xhs', 'xhs_sign.py'
    )
    xhs_sign_path = os.path.abspath(xhs_sign_path)

    if 'media_platform.xhs.xhs_sign' not in sys.modules:
        xhs_spec = importlib.util.spec_from_file_location('xhs_sign', xhs_sign_path)
        xhs_module = importlib.util.module_from_spec(xhs_spec)
        sys.modules['media_platform.xhs.xhs_sign'] = xhs_module
        xhs_spec.loader.exec_module(xhs_module)

    spec.loader.exec_module(module)
    return module


def _import_xhs_sign_module():
    """
    Import the xhs_sign module directly for standalone helper function tests.
    """
    xhs_sign_path = os.path.join(
        os.path.dirname(__file__),
        '..', '..',
        'media_platform', 'xhs', 'xhs_sign.py'
    )
    xhs_sign_path = os.path.abspath(xhs_sign_path)

    spec = importlib.util.spec_from_file_location('xhs_sign', xhs_sign_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestXHSAdapterBasic:
    """Test basic XHS adapter functionality"""

    def test_create_adapter(self, browser_backend, test_browser_id):
        """Test creating XHS adapter instance"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")
        adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

        assert adapter.browser == browser_backend
        assert adapter.browser_id == test_browser_id
        assert adapter._enable_cache is True  # Default

    def test_create_adapter_without_cache(self, browser_backend, test_browser_id):
        """Test creating XHS adapter with cache disabled"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")
        adapter = adapter_module.XHSEnergyAdapter(
            browser_backend,
            test_browser_id,
            enable_cache=False
        )

        assert adapter._enable_cache is False
        assert adapter._signature_cache is None

    def test_adapter_context_manager(self, browser_backend, test_browser_id):
        """Test using adapter as context manager"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")
        adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

        # Should work as context manager
        with adapter as a:
            assert a is adapter

    def test_adapter_cache_operations(self, browser_backend, test_browser_id):
        """Test adapter cache operations"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")
        adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

        # Clear cache should work
        adapter.clear_cache()

        # Get cache stats
        stats = adapter.get_cache_stats()
        assert stats['enabled'] is True


@pytest.mark.e2e
class TestXHSSignatureCacheStandalone:
    """Test signature caching functionality with standalone cache logic."""

    def test_cache_basic_operations(self):
        """Test basic cache set/get operations"""
        import hashlib
        from collections import OrderedDict
        from threading import Lock
        from dataclasses import dataclass
        from typing import Optional, Dict, Any
        import time

        # Inline cache implementation for standalone testing
        @dataclass
        class CacheEntry:
            value: str
            created_at: float
            ttl: int

        class SignatureCache:
            def __init__(self, max_size: int = 1000, ttl: int = 300):
                self._cache: OrderedDict = OrderedDict()
                self._lock = Lock()
                self._max_size = max_size
                self._ttl = ttl
                self._hits = 0
                self._misses = 0

            def _make_key(self, sign_str: str, md5_str: str) -> str:
                return f"{md5_str}:{hash(sign_str) % 1000000}"

            def get(self, sign_str: str, md5_str: str) -> Optional[str]:
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
                with self._lock:
                    self._cache.clear()
                    self._hits = 0
                    self._misses = 0

            def stats(self) -> Dict[str, Any]:
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

        cache = SignatureCache(max_size=10, ttl=60)

        # Cache miss
        result = cache.get('test_str', 'test_md5')
        assert result is None

        # Cache set
        cache.set('test_str', 'test_md5', 'signature_value')

        # Cache hit
        result = cache.get('test_str', 'test_md5')
        assert result == 'signature_value'

    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration"""
        import time
        from collections import OrderedDict
        from threading import Lock
        from dataclasses import dataclass
        from typing import Optional, Dict, Any

        @dataclass
        class CacheEntry:
            value: str
            created_at: float
            ttl: int

        class SignatureCache:
            def __init__(self, max_size: int = 1000, ttl: int = 300):
                self._cache: OrderedDict = OrderedDict()
                self._lock = Lock()
                self._max_size = max_size
                self._ttl = ttl
                self._hits = 0
                self._misses = 0

            def _make_key(self, sign_str: str, md5_str: str) -> str:
                return f"{md5_str}:{hash(sign_str) % 1000000}"

            def get(self, sign_str: str, md5_str: str) -> Optional[str]:
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
                key = self._make_key(sign_str, md5_str)
                with self._lock:
                    if len(self._cache) >= self._max_size:
                        self._cache.popitem(last=False)
                    self._cache[key] = CacheEntry(
                        value=value,
                        created_at=time.time(),
                        ttl=ttl if ttl is not None else self._ttl
                    )

        cache = SignatureCache(max_size=10, ttl=1)  # 1 second TTL

        # Set value
        cache.set('test_str', 'test_md5', 'value')

        # Should be available immediately
        result = cache.get('test_str', 'test_md5')
        assert result == 'value'

        # Wait for TTL to expire
        time.sleep(1.5)

        # Should be expired now
        result = cache.get('test_str', 'test_md5')
        assert result is None

    def test_md5_hash(self):
        """Test MD5 hash calculation"""
        import hashlib

        def _md5_hex(s: str) -> str:
            return hashlib.md5(s.encode("utf-8")).hexdigest()

        # Known MD5 hash
        result = _md5_hex("test")
        assert result == "098f6bcd4621d373cade4e832627b4f6"

    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full"""
        import time
        from collections import OrderedDict
        from threading import Lock
        from dataclasses import dataclass
        from typing import Optional

        @dataclass
        class CacheEntry:
            value: str
            created_at: float
            ttl: int

        class SignatureCache:
            def __init__(self, max_size: int = 1000, ttl: int = 300):
                self._cache: OrderedDict = OrderedDict()
                self._lock = Lock()
                self._max_size = max_size
                self._ttl = ttl
                self._hits = 0
                self._misses = 0

            def _make_key(self, sign_str: str, md5_str: str) -> str:
                return f"{md5_str}:{hash(sign_str) % 1000000}"

            def get(self, sign_str: str, md5_str: str) -> Optional[str]:
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
                key = self._make_key(sign_str, md5_str)
                with self._lock:
                    if len(self._cache) >= self._max_size:
                        self._cache.popitem(last=False)
                    self._cache[key] = CacheEntry(
                        value=value,
                        created_at=time.time(),
                        ttl=ttl if ttl is not None else self._ttl
                    )

        cache = SignatureCache(max_size=3, ttl=60)

        # Add 3 items (filling cache)
        cache.set('str1', 'md5_1', 'value1')
        cache.set('str2', 'md5_2', 'value2')
        cache.set('str3', 'md5_3', 'value3')

        # All should be available
        assert cache.get('str1', 'md5_1') == 'value1'
        assert cache.get('str2', 'md5_2') == 'value2'
        assert cache.get('str3', 'md5_3') == 'value3'

        # Add 4th item (should evict oldest)
        cache.set('str4', 'md5_4', 'value4')

        # First item should be evicted
        assert cache.get('str1', 'md5_1') is None
        assert cache.get('str4', 'md5_4') == 'value4'

    def test_cache_statistics(self):
        """Test cache statistics tracking"""
        import time
        from collections import OrderedDict
        from threading import Lock
        from dataclasses import dataclass
        from typing import Optional, Dict, Any

        @dataclass
        class CacheEntry:
            value: str
            created_at: float
            ttl: int

        class SignatureCache:
            def __init__(self, max_size: int = 1000, ttl: int = 300):
                self._cache: OrderedDict = OrderedDict()
                self._lock = Lock()
                self._max_size = max_size
                self._ttl = ttl
                self._hits = 0
                self._misses = 0

            def _make_key(self, sign_str: str, md5_str: str) -> str:
                return f"{md5_str}:{hash(sign_str) % 1000000}"

            def get(self, sign_str: str, md5_str: str) -> Optional[str]:
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
                key = self._make_key(sign_str, md5_str)
                with self._lock:
                    if len(self._cache) >= self._max_size:
                        self._cache.popitem(last=False)
                    self._cache[key] = CacheEntry(
                        value=value,
                        created_at=time.time(),
                        ttl=ttl if ttl is not None else self._ttl
                    )

            def stats(self) -> Dict[str, Any]:
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

        cache = SignatureCache(max_size=10, ttl=60)

        # Initial stats
        stats = cache.stats()
        assert stats['hits'] == 0
        assert stats['misses'] == 0

        # Miss
        cache.get('str1', 'md5_1')
        stats = cache.stats()
        assert stats['misses'] == 1

        # Set and hit
        cache.set('str1', 'md5_1', 'value')
        cache.get('str1', 'md5_1')
        stats = cache.stats()
        assert stats['hits'] == 1
        assert 'hit_rate' in stats


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestXHSSignatureCache:
    """Test signature caching functionality using the actual adapter module"""

    def test_cache_basic_operations(self):
        """Test basic cache set/get operations"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter cache tests")
        cache = adapter_module.SignatureCache(max_size=10, ttl=60)

        # Cache miss
        result = cache.get('test_str', 'test_md5')
        assert result is None

        # Cache set
        cache.set('test_str', 'test_md5', 'signature_value')

        # Cache hit
        result = cache.get('test_str', 'test_md5')
        assert result == 'signature_value'

    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter cache tests")
        cache = adapter_module.SignatureCache(max_size=10, ttl=1)  # 1 second TTL

        # Set value
        cache.set('test_str', 'test_md5', 'value')

        # Should be available immediately
        result = cache.get('test_str', 'test_md5')
        assert result == 'value'

        # Wait for TTL to expire
        time.sleep(1.5)

        # Should be expired now
        result = cache.get('test_str', 'test_md5')
        assert result is None

    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter cache tests")
        cache = adapter_module.SignatureCache(max_size=3, ttl=60)

        # Add 3 items (filling cache)
        cache.set('str1', 'md5_1', 'value1')
        cache.set('str2', 'md5_2', 'value2')
        cache.set('str3', 'md5_3', 'value3')

        # All should be available
        assert cache.get('str1', 'md5_1') == 'value1'
        assert cache.get('str2', 'md5_2') == 'value2'
        assert cache.get('str3', 'md5_3') == 'value3'

        # Add 4th item (should evict oldest)
        cache.set('str4', 'md5_4', 'value4')

        # First item should be evicted
        assert cache.get('str1', 'md5_1') is None
        assert cache.get('str4', 'md5_4') == 'value4'

    def test_cache_statistics(self):
        """Test cache statistics tracking"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter cache tests")
        cache = adapter_module.SignatureCache(max_size=10, ttl=60)

        # Initial stats
        stats = cache.stats()
        assert stats['hits'] == 0
        assert stats['misses'] == 0

        # Miss
        cache.get('str1', 'md5_1')
        stats = cache.stats()
        assert stats['misses'] == 1

        # Set and hit
        cache.set('str1', 'md5_1', 'value')
        cache.get('str1', 'md5_1')
        stats = cache.stats()
        assert stats['hits'] == 1
        assert 'hit_rate' in stats

    def test_cache_clear(self):
        """Test cache clearing"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter cache tests")
        cache = adapter_module.SignatureCache(max_size=10, ttl=60)

        # Add items
        cache.set('str1', 'md5_1', 'value1')
        cache.set('str2', 'md5_2', 'value2')

        # Clear
        cache.clear()

        # All should be gone (these will be misses)
        assert cache.get('str1', 'md5_1') is None
        assert cache.get('str2', 'md5_2') is None

        # Stats should show 0 hits but 2 misses from the above get() calls
        stats = cache.stats()
        assert stats['hits'] == 0
        assert stats['misses'] == 2


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestXHSSignatureGeneration:
    """Test signature generation with real browser"""

    @pytest.mark.asyncio
    async def test_execute_signature_on_xhs_page(self, browser_backend, test_browser_id):
        """Test executing signature on XHS page"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        # Create browser and navigate to XHS
        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            status = browser_backend.navigate(
                test_browser_id,
                'https://www.xiaohongshu.com',
                timeout_ms=60000
            )

            if status != 200:
                pytest.skip("Failed to navigate to XHS")

            # Create adapter
            adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

            # Execute signature
            sign_str = "/api/sns/web/v1/search/notes"
            md5_str = "d41d8cd98f00b204e9800998ecf8427e"

            result = await adapter.execute_signature(sign_str, md5_str, use_cache=False)

            # Result should be a string (may be empty if mnsv2 not loaded)
            assert isinstance(result, str)

        finally:
            browser_backend.close_browser(test_browser_id)

    @pytest.mark.asyncio
    async def test_signature_with_cache(self, browser_backend, test_browser_id):
        """Test signature generation with caching"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            status = browser_backend.navigate(
                test_browser_id,
                'https://www.xiaohongshu.com',
                timeout_ms=60000
            )

            if status != 200:
                pytest.skip("Failed to navigate to XHS")

            adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id, enable_cache=True)

            sign_str = "/api/sns/web/v1/search/notes"
            md5_str = "d41d8cd98f00b204e9800998ecf8427e"

            # First call (cache miss)
            result1 = await adapter.execute_signature(sign_str, md5_str, use_cache=True)

            # Second call (should hit cache)
            result2 = await adapter.execute_signature(sign_str, md5_str, use_cache=True)

            # Results should be the same
            assert result1 == result2

            # Check cache stats
            stats = adapter.get_cache_stats()
            assert stats['enabled'] is True

        finally:
            browser_backend.close_browser(test_browser_id)

    @pytest.mark.asyncio
    async def test_sign_with_energy(self, browser_backend, test_browser_id):
        """Test complete signature generation"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            status = browser_backend.navigate(
                test_browser_id,
                'https://www.xiaohongshu.com',
                timeout_ms=60000
            )

            if status != 200:
                pytest.skip("Failed to navigate to XHS")

            adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

            # Generate complete signature
            signs = await adapter.sign_with_energy(
                uri="/api/sns/web/v1/search/notes",
                data={"keyword": "test"},
                a1="test_a1_value",
                method="POST"
            )

            # Verify signature structure
            assert 'x-s' in signs
            assert 'x-t' in signs
            assert 'x-s-common' in signs
            assert 'x-b3-traceid' in signs

            # Verify types
            assert isinstance(signs['x-s'], str)
            assert isinstance(signs['x-t'], str)
            assert isinstance(signs['x-s-common'], str)
            assert isinstance(signs['x-b3-traceid'], str)

            # Verify x-s starts with XYS_
            assert signs['x-s'].startswith('XYS_')

            # Verify x-t is a timestamp
            assert signs['x-t'].isdigit()

        finally:
            browser_backend.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestXHSCookieManagement:
    """Test cookie management"""

    def test_get_cookies(self, browser_backend, test_browser_id):
        """Test getting cookies from XHS"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            browser_backend.navigate(
                test_browser_id,
                'https://www.xiaohongshu.com',
                timeout_ms=60000
            )

            adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

            # Get cookies
            cookies = adapter.get_cookies()

            # Should return a dict
            assert isinstance(cookies, dict)

        finally:
            browser_backend.close_browser(test_browser_id)

    def test_set_cookies(self, browser_backend, test_browser_id):
        """Test setting cookies"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            browser_backend.navigate(
                test_browser_id,
                'https://www.xiaohongshu.com',
                timeout_ms=60000
            )

            adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

            # Set cookies
            cookies_to_set = [
                {"name": "test_cookie", "value": "test_value", "domain": ".xiaohongshu.com"}
            ]

            result = adapter.set_cookies(cookies_to_set)

            # Should succeed
            assert result is True

        finally:
            browser_backend.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestXHSRetryLogic:
    """Test retry logic for signature generation"""

    @pytest.mark.asyncio
    async def test_retry_configuration(self, browser_backend, test_browser_id):
        """Test retry configuration"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

        # Configure retry
        adapter.set_retry_config(
            max_retries=5,
            retry_delay_ms=50,
            backoff_factor=1.5
        )

        # Verify configuration is stored
        assert adapter._max_retries == 5
        assert adapter._retry_delay_ms == 50
        assert adapter._retry_backoff_factor == 1.5


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestXHSHelperFunctions:
    """Test helper functions"""

    def test_md5_hex(self):
        """Test MD5 hash calculation"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        # Known MD5 hash
        result = adapter_module._md5_hex("test")
        assert result == "098f6bcd4621d373cade4e832627b4f6"

    def test_build_xs_payload(self):
        """Test x-s payload building"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        result = adapter_module._build_xs_payload("test_x3_value", "object")

        # Should start with XYS_
        assert result.startswith("XYS_")

    def test_build_xs_common(self):
        """Test x-s-common building"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        result = adapter_module._build_xs_common(
            a1="test_a1",
            b1="test_b1",
            x_s="test_x_s",
            x_t="1234567890"
        )

        # Should be a non-empty string
        assert isinstance(result, str)
        assert len(result) > 0


@pytest.mark.e2e
@pytest.mark.requires_energy
@pytest.mark.slow
class TestXHSIntegration:
    """Integration tests requiring full setup"""

    @pytest.mark.asyncio
    async def test_pre_headers_generation(self, browser_backend, test_browser_id):
        """Test pre-headers generation"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            status = browser_backend.navigate(
                test_browser_id,
                'https://www.xiaohongshu.com',
                timeout_ms=60000
            )

            if status != 200:
                pytest.skip("Failed to navigate to XHS")

            adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

            # Generate headers
            headers = await adapter.pre_headers_with_energy(
                url="https://edith.xiaohongshu.com/api/sns/web/v1/search/notes",
                cookie_dict={"a1": "test_a1"},
                payload={"keyword": "test"}
            )

            # Verify header structure
            assert 'X-S' in headers
            assert 'X-T' in headers
            assert 'x-S-Common' in headers
            assert 'X-B3-Traceid' in headers

        finally:
            browser_backend.close_browser(test_browser_id)

    @pytest.mark.asyncio
    async def test_b1_cache(self, browser_backend, test_browser_id):
        """Test b1 caching"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            status = browser_backend.navigate(
                test_browser_id,
                'https://www.xiaohongshu.com',
                timeout_ms=60000
            )

            if status != 200:
                pytest.skip("Failed to navigate to XHS")

            adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

            # First call (may be empty if b1 not in localStorage)
            b1_first = await adapter.get_b1_from_localstorage()

            # Second call should return cached value
            b1_second = await adapter.get_b1_from_localstorage()

            assert b1_first == b1_second

            # Force refresh
            b1_refresh = await adapter.get_b1_from_localstorage(force_refresh=True)

            # May be same or different depending on page state
            assert isinstance(b1_refresh, str)

        finally:
            browser_backend.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestXHSErrorHandling:
    """Test error handling"""

    @pytest.mark.asyncio
    async def test_signature_on_wrong_page(self, browser_backend, test_browser_id):
        """Test signature when mnsv2 doesn't exist"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            # Navigate to a page without mnsv2
            browser_backend.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            adapter = adapter_module.XHSEnergyAdapter(browser_backend, test_browser_id)

            # Should return empty string gracefully
            result = await adapter.execute_signature("test", "test_md5")

            assert result == ""

        finally:
            browser_backend.close_browser(test_browser_id)

    def test_adapter_with_invalid_browser(self, browser_backend):
        """Test adapter with non-existent browser"""
        adapter_module = _import_adapter_module()
        if adapter_module is None:
            pytest.skip("adapter module unavailable - skipping adapter tests")

        adapter = adapter_module.XHSEnergyAdapter(browser_backend, "non-existent-browser")

        # Operations should fail gracefully
        # This tests that the adapter handles missing browsers
        with pytest.raises(Exception):
            adapter.get_cookies()
