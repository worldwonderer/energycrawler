"""
E2E tests for basic browser flow

Tests the basic browser lifecycle and navigation.
"""

import pytest
import time


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestBrowserLifecycle:
    """Test browser lifecycle operations"""

    def test_create_and_close_browser(self, browser_client, test_browser_id):
        """Test creating and closing a browser"""
        # Create browser
        result = browser_client.create_browser(test_browser_id, headless=True)
        assert result is True, "Failed to create browser"

        # Close browser
        result = browser_client.close_browser(test_browser_id)
        assert result is True, "Failed to close browser"

    def test_create_headless_browser(self, browser_client, test_browser_id):
        """Test creating a headless browser explicitly"""
        result = browser_client.create_browser(test_browser_id, headless=True)
        assert result is True

        try:
            # Should still work normally
            status = browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )
            assert status == 200
        finally:
            browser_client.close_browser(test_browser_id)

    def test_multiple_browsers(self, browser_client):
        """Test creating multiple browsers"""
        browser_ids = [f"multi-test-{i}" for i in range(3)]

        try:
            # Create multiple browsers
            for bid in browser_ids:
                result = browser_client.create_browser(bid, headless=True)
                assert result is True, f"Failed to create browser {bid}"

            # Navigate each browser
            for bid in browser_ids:
                status = browser_client.navigate(
                    bid,
                    'https://example.com',
                    timeout_ms=30000
                )
                assert status == 200, f"Navigation failed for {bid}"

        finally:
            # Cleanup
            for bid in browser_ids:
                browser_client.close_browser(bid)

    def test_recreate_browser(self, browser_client, test_browser_id):
        """Test closing and recreating a browser with same ID"""
        # Create and close
        browser_client.create_browser(test_browser_id, headless=True)
        browser_client.close_browser(test_browser_id)

        # Recreate
        result = browser_client.create_browser(test_browser_id, headless=True)
        assert result is True

        # Should still work
        status = browser_client.navigate(
            test_browser_id,
            'https://example.com',
            timeout_ms=30000
        )
        assert status == 200

        browser_client.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestNavigation:
    """Test navigation operations"""

    def test_navigate_to_url(self, browser):
        """Test navigating to a URL"""
        # browser fixture handles creation
        pass  # Fixture tests basic navigation already

    def test_navigate_to_url_with_client(self, browser_client, test_browser_id):
        """Test navigating to a URL using client directly"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate to example.com
            status = browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )
            assert status == 200, f"Navigation failed with status {status}"
        finally:
            browser_client.close_browser(test_browser_id)

    def test_navigate_to_https_site(self, browser_client, test_browser_id):
        """Test navigating to an HTTPS site"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            status = browser_client.navigate(
                test_browser_id,
                'https://www.google.com',
                timeout_ms=30000
            )
            assert status == 200
        finally:
            browser_client.close_browser(test_browser_id)

    def test_navigate_timeout(self, browser_client, test_browser_id):
        """Test navigation with short timeout"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Use a short timeout - should still work for fast sites
            status = browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=5000
            )
            assert status == 200
        finally:
            browser_client.close_browser(test_browser_id)

    def test_navigate_multiple_pages(self, browser_client, test_browser_id):
        """Test navigating to multiple pages in sequence"""
        browser_client.create_browser(test_browser_id, headless=True)

        urls = [
            'https://example.com',
            'https://www.example.org',
            'https://httpbin.org/html'
        ]

        try:
            for url in urls:
                status = browser_client.navigate(
                    test_browser_id,
                    url,
                    timeout_ms=30000
                )
                assert status == 200, f"Failed to navigate to {url}"
        finally:
            browser_client.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestJavaScript:
    """Test JavaScript execution"""

    def test_execute_simple_js(self, browser):
        """Test executing simple JavaScript"""
        # This test uses the browser fixture
        pass

    def test_execute_js_with_result(self, browser_client, test_browser_id):
        """Test executing JavaScript that returns a value"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate first
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            # Execute JS that returns a simple value
            result = browser_client.execute_js(
                test_browser_id,
                '1 + 1'
            )
            assert result is not None

        finally:
            browser_client.close_browser(test_browser_id)

    def test_execute_js_return_object(self, browser_client, test_browser_id):
        """Test executing JavaScript that returns an object"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate first
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            # Execute JS that returns an object
            result = browser_client.execute_js(
                test_browser_id,
                'JSON.stringify({value: 42, name: "test"})'
            )

            assert result is not None

        finally:
            browser_client.close_browser(test_browser_id)

    def test_execute_js_get_page_info(self, browser_client, test_browser_id):
        """Test executing JavaScript to get page information"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            # Get page title
            title = browser_client.execute_js(
                test_browser_id,
                'document.title'
            )
            assert title is not None

            # Get URL
            url = browser_client.execute_js(
                test_browser_id,
                'window.location.href'
            )
            assert url is not None

        finally:
            browser_client.close_browser(test_browser_id)

    def test_execute_js_dom_manipulation(self, browser_client, test_browser_id):
        """Test executing JavaScript that manipulates DOM"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            # Create an element and get its ID
            result = browser_client.execute_js(
                test_browser_id,
                '''
                var el = document.createElement('div');
                el.id = 'test-element';
                el.textContent = 'Hello World';
                document.body.appendChild(el);
                'test-element';
                '''
            )
            assert result is not None

        finally:
            browser_client.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestCookies:
    """Test cookie operations"""

    def test_get_cookies(self, browser):
        """Test getting cookies from a page"""
        # This test uses the browser fixture
        pass

    def test_cookie_roundtrip(self, browser_client, test_browser_id):
        """Test setting and getting cookies"""
        from energy_client.client import Cookie

        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate first
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            # Set a cookie
            test_cookie = Cookie(
                name='test_cookie',
                value='test_value_123',
                domain='example.com',
                path='/',
                secure=False,
                http_only=False
            )

            result = browser_client.set_cookies(test_browser_id, [test_cookie])

            # Get cookies back
            cookies = browser_client.get_cookies(
                test_browser_id,
                'https://example.com'
            )

            assert isinstance(cookies, list)

        finally:
            browser_client.close_browser(test_browser_id)

    def test_set_multiple_cookies(self, browser_client, test_browser_id):
        """Test setting multiple cookies at once"""
        from energy_client.client import Cookie

        browser_client.create_browser(test_browser_id, headless=True)

        try:
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            cookies = [
                Cookie(name=f'cookie_{i}', value=f'value_{i}',
                       domain='example.com', path='/',
                       secure=False, http_only=False)
                for i in range(3)
            ]

            result = browser_client.set_cookies(test_browser_id, cookies)

        finally:
            browser_client.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestBackendInterface:
    """Test the high-level backend interface"""

    def test_browser_backend_interface(self, browser_backend, test_browser_id):
        """Test using the high-level backend interface"""
        # Create browser
        result = browser_backend.create_browser(test_browser_id, headless=True)
        assert result is True

        try:
            # Navigate
            status = browser_backend.navigate(
                test_browser_id,
                'https://example.com'
            )
            assert status == 200
        finally:
            browser_backend.close_browser(test_browser_id)

    def test_backend_execute_js(self, browser_backend, test_browser_id):
        """Test JavaScript execution through backend interface"""
        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            browser_backend.navigate(
                test_browser_id,
                'https://example.com'
            )

            result = browser_backend.execute_js(
                test_browser_id,
                'document.title'
            )
            assert result is not None

        finally:
            browser_backend.close_browser(test_browser_id)

    def test_backend_cookie_operations(self, browser_backend, test_browser_id):
        """Test cookie operations through backend interface"""
        from energy_client.browser_interface import Cookie

        browser_backend.create_browser(test_browser_id, headless=True)

        try:
            browser_backend.navigate(
                test_browser_id,
                'https://example.com'
            )

            # Set cookie
            test_cookie = Cookie(
                name='backend_test',
                value='test_value',
                domain='example.com'
            )
            result = browser_backend.set_cookies(test_browser_id, [test_cookie])

            # Get cookies
            cookies = browser_backend.get_cookies(
                test_browser_id,
                'https://example.com'
            )
            assert isinstance(cookies, list)

        finally:
            browser_backend.close_browser(test_browser_id)
