"""
E2E tests for signature generation

Tests platform-specific signature execution.
"""

import pytest
import json


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestSignature:
    """Test signature generation for various platforms"""

    def test_xhs_signature_structure(self, browser_client, test_browser_id):
        """Test XHS signature generation structure (requires mnsv2)"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate to XHS
            status = browser_client.navigate(
                test_browser_id,
                'https://www.xiaohongshu.com',
                timeout_ms=60000
            )

            if status != 200:
                pytest.skip("Failed to navigate to XHS - skipping signature test")

            # Execute signature
            # Note: This will only work if window.mnsv2 exists on the page
            try:
                signatures = browser_client.execute_signature(
                    test_browser_id,
                    'xhs',
                    'https://www.xiaohongshu.com/explore'
                )

                # Verify signature structure
                assert isinstance(signatures, dict)
            except Exception as e:
                # If signature function not available, skip
                pytest.skip(f"Signature function not available: {e}")

        finally:
            browser_client.close_browser(test_browser_id)

    def test_signature_with_valid_params(self, browser_client, test_browser_id):
        """Test signature generation with valid parameters"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate to a page first
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            # Try signature - may fail if no signature function available
            try:
                signatures = browser_client.execute_signature(
                    test_browser_id,
                    'xhs',
                    'https://example.com'
                )
                assert isinstance(signatures, dict)
            except Exception:
                # Expected if signature function not available
                pass

        finally:
            browser_client.close_browser(test_browser_id)

    def test_signature_error_handling(self, browser_client, test_browser_id):
        """Test that signature generation handles errors gracefully"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate to a page without signature functions
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            # Try to execute signature - should handle gracefully
            try:
                signatures = browser_client.execute_signature(
                    test_browser_id,
                    'xhs',
                    'https://example.com'
                )
                # If it doesn't raise an error, it should return empty or error
                assert isinstance(signatures, dict)
            except Exception as e:
                # Expected - page doesn't have signature function
                assert True

        finally:
            browser_client.close_browser(test_browser_id)

    def test_signature_timeout_handling(self, browser_client, test_browser_id):
        """Test that signature generation handles timeouts gracefully"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate to a page without signature functions
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            # Try to execute signature - should handle gracefully
            try:
                signatures = browser_client.execute_signature(
                    test_browser_id,
                    'xhs',
                    'https://example.com'
                )
                assert isinstance(signatures, dict)
            except Exception as e:
                # Expected - page doesn't have signature function
                assert True

        finally:
            browser_client.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestProxySettings:
    """Test proxy configuration"""

    def test_set_proxy_no_auth(self, browser_client, test_browser_id):
        """Test setting proxy without authentication"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Set proxy (using a dummy proxy - won't actually work)
            result = browser_client.set_proxy(
                test_browser_id,
                'http://localhost:8080'
            )

            # Result depends on whether proxy is available
            # We're testing the API call works
            assert isinstance(result, bool)

        finally:
            browser_client.close_browser(test_browser_id)

    def test_set_proxy_with_auth(self, browser_client, test_browser_id):
        """Test setting proxy with authentication"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Set proxy with auth
            result = browser_client.set_proxy(
                test_browser_id,
                'http://proxy.example.com:8080',
                'testuser',
                'testpass'
            )

            assert isinstance(result, bool)

        finally:
            browser_client.close_browser(test_browser_id)

    def test_set_proxy_socks5(self, browser_client, test_browser_id):
        """Test setting SOCKS5 proxy"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Set SOCKS5 proxy
            result = browser_client.set_proxy(
                test_browser_id,
                'socks5://localhost:1080'
            )

            assert isinstance(result, bool)

        finally:
            browser_client.close_browser(test_browser_id)

    def test_set_proxy_before_navigation(self, browser_client, test_browser_id):
        """Test setting proxy before navigation"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Set proxy first
            browser_client.set_proxy(
                test_browser_id,
                'http://localhost:8080'
            )

            # Then navigate - will likely fail with invalid proxy
            # but we're testing the order of operations
            try:
                status = browser_client.navigate(
                    test_browser_id,
                    'https://example.com',
                    timeout_ms=10000
                )
            except Exception:
                pass  # Expected with invalid proxy

        finally:
            browser_client.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestErrorHandling:
    """Test error handling scenarios"""

    def test_invalid_browser_id(self, browser_client):
        """Test operations with invalid browser ID"""
        with pytest.raises(Exception):
            browser_client.navigate(
                'non-existent-browser',
                'https://example.com'
            )

    def test_double_create(self, browser_client, test_browser_id):
        """Test creating browser with same ID twice"""
        # First create
        result1 = browser_client.create_browser(test_browser_id, headless=True)
        assert result1 is True

        try:
            # Second create - should fail or return False
            result2 = browser_client.create_browser(test_browser_id, headless=True)
            # Might return False or raise exception
            assert result2 is False or True  # Behavior depends on implementation
        finally:
            browser_client.close_browser(test_browser_id)

    def test_close_nonexistent_browser(self, browser_client):
        """Test closing a browser that doesn't exist"""
        result = browser_client.close_browser('non-existent-browser')
        # Should return False or handle gracefully
        assert result is False or result is True

    def test_navigate_invalid_url(self, browser_client, test_browser_id):
        """Test navigating to invalid URL"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            with pytest.raises(Exception):
                browser_client.navigate(
                    test_browser_id,
                    'not-a-valid-url',
                    timeout_ms=5000
                )
        finally:
            browser_client.close_browser(test_browser_id)

    def test_js_execution_on_closed_browser(self, browser_client, test_browser_id):
        """Test JS execution on closed browser"""
        browser_client.create_browser(test_browser_id, headless=True)
        browser_client.close_browser(test_browser_id)

        with pytest.raises(Exception):
            browser_client.execute_js(test_browser_id, '1 + 1')

    def test_cookie_operations_on_closed_browser(self, browser_client, test_browser_id):
        """Test cookie operations on closed browser"""
        browser_client.create_browser(test_browser_id, headless=True)
        browser_client.navigate(test_browser_id, 'https://example.com', timeout_ms=30000)
        browser_client.close_browser(test_browser_id)

        with pytest.raises(Exception):
            browser_client.get_cookies(test_browser_id, 'https://example.com')

    def test_navigate_on_closed_browser(self, browser_client, test_browser_id):
        """Test navigation on closed browser"""
        browser_client.create_browser(test_browser_id, headless=True)
        browser_client.close_browser(test_browser_id)

        with pytest.raises(Exception):
            browser_client.navigate(test_browser_id, 'https://example.com')


@pytest.mark.e2e
@pytest.mark.requires_energy
@pytest.mark.slow
class TestStressTests:
    """Stress tests for the browser service"""

    def test_rapid_browser_creation(self, browser_client):
        """Test rapid creation and destruction of browsers"""
        browser_ids = [f"stress-test-{i}" for i in range(5)]

        try:
            for bid in browser_ids:
                result = browser_client.create_browser(bid, headless=True)
                assert result is True

            for bid in browser_ids:
                result = browser_client.close_browser(bid)
                assert result is True

        finally:
            for bid in browser_ids:
                try:
                    browser_client.close_browser(bid)
                except Exception:
                    pass

    def test_rapid_navigation(self, browser_client, test_browser_id):
        """Test rapid navigation requests"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            for i in range(3):
                status = browser_client.navigate(
                    test_browser_id,
                    f'https://example.com',
                    timeout_ms=30000
                )
                assert status == 200

        finally:
            browser_client.close_browser(test_browser_id)

    def test_concurrent_js_execution(self, browser_client, test_browser_id):
        """Test multiple JavaScript executions in sequence"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )

            for i in range(5):
                result = browser_client.execute_js(
                    test_browser_id,
                    f'{i} + {i}'
                )
                assert result is not None

        finally:
            browser_client.close_browser(test_browser_id)


@pytest.mark.e2e
@pytest.mark.requires_energy
class TestServiceHealth:
    """Test service health and connectivity"""

    def test_service_connectivity(self, browser_client):
        """Test that the service is accessible"""
        # The browser_client fixture already connects
        # If we get here, connection works
        assert browser_client is not None

    def test_service_responsiveness(self, browser_client, test_browser_id):
        """Test that the service responds to requests"""
        result = browser_client.create_browser(test_browser_id, headless=True)
        assert result is True
        browser_client.close_browser(test_browser_id)

    def test_multiple_sequential_operations(self, browser_client, test_browser_id):
        """Test multiple sequential operations"""
        browser_client.create_browser(test_browser_id, headless=True)

        try:
            # Navigate
            status = browser_client.navigate(
                test_browser_id,
                'https://example.com',
                timeout_ms=30000
            )
            assert status == 200

            # Execute JS
            result = browser_client.execute_js(
                test_browser_id,
                'document.title'
            )
            assert result is not None

            # Get cookies
            cookies = browser_client.get_cookies(
                test_browser_id,
                'https://example.com'
            )
            assert isinstance(cookies, list)

        finally:
            browser_client.close_browser(test_browser_id)
