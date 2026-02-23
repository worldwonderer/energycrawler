"""
Unit tests for BrowserClient
"""

import pytest
from unittest.mock import MagicMock, patch, call, ANY
import grpc

# Import from energy_client
from energy_client import client, browser_pb2, browser_pb2_grpc


class TestBrowserClient:
    """Test cases for BrowserClient class"""

    def test_init_with_default_address(self):
        """Test client initialization with default address"""
        c = client.BrowserClient()
        assert c.host == 'localhost'
        assert c.port == 50051
        assert c.channel is None
        assert c.stub is None

    def test_init_with_custom_address(self):
        """Test client initialization with custom address"""
        c = client.BrowserClient('192.168.1.100', 8080)
        assert c.host == '192.168.1.100'
        assert c.port == 8080
        assert c.channel is None
        assert c.stub is None

    def test_connect(self, browser_client):
        """Test connecting to server"""
        browser_client.connect()
        assert browser_client.channel is not None

    def test_disconnect(self, browser_client):
        """Test disconnecting from server"""
        browser_client.connect()
        browser_client.disconnect()
        assert browser_client.channel is None
        assert browser_client.stub is None

    def test_context_manager(self):
        """Test context manager protocol"""
        with patch('energy_client.client.grpc.insecure_channel') as mock_channel:
            mock_channel.return_value = MagicMock()
            c = client.BrowserClient('localhost', 50051)
            with c as client_ctx:
                assert client_ctx is c
                assert c.channel is not None
            # Channel should be closed after exit

    def test_context_manager_exception_handling(self):
        """Test context manager handles exceptions properly"""
        with patch('energy_client.client.grpc.insecure_channel') as mock_channel:
            mock_channel.return_value = MagicMock()
            c = client.BrowserClient('localhost', 50051)
            try:
                with c:
                    raise ValueError("Test exception")
            except ValueError:
                pass
            # Channel should still be closed
            assert c.channel is None

    def test_create_browser_success(self, browser_client, mock_browser_stub):
        """Test successful browser creation"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_browser_stub.CreateBrowser.return_value = mock_response

        browser_client.connect()
        result = browser_client.create_browser('test-browser', headless=True)

        assert result is True
        mock_browser_stub.CreateBrowser.assert_called_once()
        call_args = mock_browser_stub.CreateBrowser.call_args[0][0]
        assert call_args.browser_id == 'test-browser'
        assert call_args.headless is True

    def test_create_browser_error(self, browser_client, mock_browser_stub):
        """Test failed browser creation"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "Browser already exists"
        mock_browser_stub.CreateBrowser.return_value = mock_response

        browser_client.connect()
        result = browser_client.create_browser('test-browser', headless=True)

        assert result is False

    def test_create_browser_with_headless_false(self, browser_client, mock_browser_stub):
        """Test browser creation with headless=False"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_browser_stub.CreateBrowser.return_value = mock_response

        browser_client.connect()
        result = browser_client.create_browser('test-browser', headless=False)

        assert result is True
        call_args = mock_browser_stub.CreateBrowser.call_args[0][0]
        assert call_args.headless is False

    def test_close_browser(self, browser_client, mock_browser_stub):
        """Test closing browser"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_browser_stub.CloseBrowser.return_value = mock_response

        browser_client.connect()
        result = browser_client.close_browser('test-browser')

        assert result is True
        mock_browser_stub.CloseBrowser.assert_called_once()
        call_args = mock_browser_stub.CloseBrowser.call_args[0][0]
        assert call_args.browser_id == 'test-browser'

    def test_navigate_success(self, browser_client, mock_browser_stub):
        """Test successful navigation"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.status_code = 200
        mock_browser_stub.Navigate.return_value = mock_response

        browser_client.connect()
        status = browser_client.navigate('test-browser', 'https://example.com')

        assert status == 200
        mock_browser_stub.Navigate.assert_called_once()
        call_args = mock_browser_stub.Navigate.call_args[0][0]
        assert call_args.browser_id == 'test-browser'
        assert call_args.url == 'https://example.com'

    def test_navigate_with_custom_timeout(self, browser_client, mock_browser_stub):
        """Test navigation with custom timeout"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.status_code = 200
        mock_browser_stub.Navigate.return_value = mock_response

        browser_client.connect()
        status = browser_client.navigate('test-browser', 'https://example.com', timeout_ms=60000)

        assert status == 200
        call_args = mock_browser_stub.Navigate.call_args[0][0]
        assert call_args.timeout_ms == 60000

    def test_navigate_timeout(self, browser_client, mock_browser_stub):
        """Test navigation timeout"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "Navigation timeout"
        mock_browser_stub.Navigate.return_value = mock_response

        browser_client.connect()

        with pytest.raises(Exception) as exc_info:
            browser_client.navigate('test-browser', 'https://example.com')

        assert "Navigation timeout" in str(exc_info.value)

    def test_navigate_error(self, browser_client, mock_browser_stub):
        """Test navigation failure"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "Connection refused"
        mock_browser_stub.Navigate.return_value = mock_response

        browser_client.connect()

        with pytest.raises(Exception) as exc_info:
            browser_client.navigate('test-browser', 'https://example.com')

        assert "Connection refused" in str(exc_info.value)

    def test_navigate_invalid_url_raises_before_rpc(self, browser_client, mock_browser_stub):
        """Test invalid URL validation on client side"""
        browser_client.connect()

        with pytest.raises(ValueError):
            browser_client.navigate('test-browser', 'not-a-valid-url')

        mock_browser_stub.Navigate.assert_not_called()

    def test_navigate_file_url_is_allowed(self, browser_client, mock_browser_stub):
        """Test local file:// URL remains supported (QR flow compatibility)"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.status_code = 200
        mock_browser_stub.Navigate.return_value = mock_response

        browser_client.connect()
        status = browser_client.navigate('test-browser', 'file:///tmp/test_qr.html')

        assert status == 200
        mock_browser_stub.Navigate.assert_called_once()

    def test_get_cookies_success(self, browser_client, mock_browser_stub, sample_cookies):
        """Test getting cookies successfully"""
        # Create protobuf cookies
        pb_cookies = [
            browser_pb2.Cookie(
                name=c.name,
                value=c.value,
                domain=c.domain,
                path=c.path,
                secure=c.secure,
                http_only=c.http_only
            )
            for c in sample_cookies
        ]

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.cookies = pb_cookies
        mock_browser_stub.GetCookies.return_value = mock_response

        browser_client.connect()
        cookies = browser_client.get_cookies('test-browser', 'https://example.com')

        assert len(cookies) == 2
        assert cookies[0].name == 'test_cookie'
        assert cookies[1].name == 'session_id'
        assert all(isinstance(c, client.Cookie) for c in cookies)

    def test_get_cookies_error(self, browser_client, mock_browser_stub):
        """Test get cookies failure"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "Browser not found"
        mock_browser_stub.GetCookies.return_value = mock_response

        browser_client.connect()

        with pytest.raises(Exception) as exc_info:
            browser_client.get_cookies('test-browser', 'https://example.com')

        assert "Browser not found" in str(exc_info.value)

    def test_set_cookies_success(self, browser_client, mock_browser_stub, sample_cookies):
        """Test setting cookies successfully"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_browser_stub.SetCookies.return_value = mock_response

        browser_client.connect()
        result = browser_client.set_cookies('test-browser', sample_cookies)

        assert result is True
        mock_browser_stub.SetCookies.assert_called_once()

    def test_set_cookies_error(self, browser_client, mock_browser_stub, sample_cookies):
        """Test set cookies failure"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_browser_stub.SetCookies.return_value = mock_response

        browser_client.connect()
        result = browser_client.set_cookies('test-browser', sample_cookies)

        assert result is False

    def test_execute_js_success(self, browser_client, mock_browser_stub):
        """Test executing JavaScript successfully"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = '{"value": 42}'
        mock_browser_stub.ExecuteJS.return_value = mock_response

        browser_client.connect()
        result = browser_client.execute_js('test-browser', 'return 42;')

        assert result == '{"value": 42}'
        mock_browser_stub.ExecuteJS.assert_called_once()
        call_args = mock_browser_stub.ExecuteJS.call_args[0][0]
        assert call_args.script == 'return 42;'

    def test_execute_js_with_result(self, browser_client, mock_browser_stub):
        """Test executing JavaScript with complex result"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = '{"name": "test", "data": [1, 2, 3], "nested": {"key": "value"}}'
        mock_browser_stub.ExecuteJS.return_value = mock_response

        browser_client.connect()
        result = browser_client.execute_js('test-browser', 'return getData();')

        assert result == '{"name": "test", "data": [1, 2, 3], "nested": {"key": "value"}}'

    def test_execute_js_error(self, browser_client, mock_browser_stub):
        """Test execute JS failure"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "JavaScript error: undefined variable"
        mock_browser_stub.ExecuteJS.return_value = mock_response

        browser_client.connect()

        with pytest.raises(Exception) as exc_info:
            browser_client.execute_js('test-browser', 'return undefinedVar;')

        assert "JavaScript error" in str(exc_info.value)

    def test_set_proxy_success(self, browser_client, mock_browser_stub):
        """Test setting proxy successfully"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_browser_stub.SetProxy.return_value = mock_response

        browser_client.connect()
        result = browser_client.set_proxy(
            'test-browser',
            'http://proxy.example.com:8080',
            'user',
            'pass'
        )

        assert result is True
        mock_browser_stub.SetProxy.assert_called_once()
        call_args = mock_browser_stub.SetProxy.call_args[0][0]
        assert call_args.proxy_url == 'http://proxy.example.com:8080'
        assert call_args.username == 'user'
        assert call_args.password == 'pass'

    def test_set_proxy_without_auth(self, browser_client, mock_browser_stub):
        """Test setting proxy without authentication"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_browser_stub.SetProxy.return_value = mock_response

        browser_client.connect()
        result = browser_client.set_proxy('test-browser', 'http://proxy.example.com:8080')

        assert result is True
        call_args = mock_browser_stub.SetProxy.call_args[0][0]
        assert call_args.username == ''
        assert call_args.password == ''

    def test_set_proxy_error(self, browser_client, mock_browser_stub):
        """Test set proxy failure"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_browser_stub.SetProxy.return_value = mock_response

        browser_client.connect()
        result = browser_client.set_proxy('test-browser', 'http://invalid-proxy:8080')

        assert result is False

    def test_execute_signature_xhs(self, browser_client, mock_browser_stub):
        """Test executing signature for XHS platform"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.signatures = {'x-s': 'sig123', 'x-t': 'timestamp', 'x-s-common': 'common'}
        mock_browser_stub.ExecuteSignature.return_value = mock_response

        browser_client.connect()
        signatures = browser_client.execute_signature(
            'test-browser',
            'xhs',
            'https://xiaohongshu.com'
        )

        assert 'x-s' in signatures
        assert 'x-t' in signatures
        assert 'x-s-common' in signatures
        assert signatures['x-s'] == 'sig123'
        mock_browser_stub.ExecuteSignature.assert_called_once()
        call_args = mock_browser_stub.ExecuteSignature.call_args[0][0]
        assert call_args.platform == 'xhs'

    def test_execute_signature_unsupported(self, browser_client, mock_browser_stub):
        """Test executing signature for unsupported platform"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "Unsupported platform: unknown"
        mock_browser_stub.ExecuteSignature.return_value = mock_response

        browser_client.connect()

        with pytest.raises(Exception) as exc_info:
            browser_client.execute_signature('test-browser', 'unknown', 'https://example.com')

        assert "Unsupported platform" in str(exc_info.value)

    def test_execute_signature_error(self, browser_client, mock_browser_stub):
        """Test execute signature failure"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "Signature generation failed"
        mock_browser_stub.ExecuteSignature.return_value = mock_response

        browser_client.connect()

        with pytest.raises(Exception) as exc_info:
            browser_client.execute_signature('test-browser', 'xhs', 'https://example.com')

        assert "Signature generation failed" in str(exc_info.value)


class TestCookieDataclass:
    """Test cases for Cookie dataclass"""

    def test_cookie_creation(self):
        """Test creating a cookie"""
        cookie = client.Cookie(
            name='test',
            value='value',
            domain='example.com',
            path='/',
            secure=True,
            http_only=False
        )

        assert cookie.name == 'test'
        assert cookie.value == 'value'
        assert cookie.domain == 'example.com'
        assert cookie.path == '/'
        assert cookie.secure is True
        assert cookie.http_only is False

    def test_cookie_defaults(self):
        """Test cookie default values"""
        cookie = client.Cookie(
            name='test',
            value='value',
            domain='',
            path='',
            secure=False,
            http_only=False
        )

        assert cookie.domain == ''
        assert cookie.path == ''
        assert cookie.secure is False

    def test_cookie_equality(self):
        """Test cookie equality"""
        cookie1 = client.Cookie(
            name='test',
            value='value',
            domain='example.com',
            path='/',
            secure=False,
            http_only=False
        )
        cookie2 = client.Cookie(
            name='test',
            value='value',
            domain='example.com',
            path='/',
            secure=False,
            http_only=False
        )

        assert cookie1 == cookie2

    def test_cookie_inequality(self):
        """Test cookie inequality"""
        cookie1 = client.Cookie(
            name='test1',
            value='value',
            domain='example.com',
            path='/',
            secure=False,
            http_only=False
        )
        cookie2 = client.Cookie(
            name='test2',
            value='value',
            domain='example.com',
            path='/',
            secure=False,
            http_only=False
        )

        assert cookie1 != cookie2

    def test_cookie_repr(self):
        """Test cookie string representation"""
        cookie = client.Cookie(
            name='test',
            value='value',
            domain='example.com',
            path='/',
            secure=True,
            http_only=True
        )

        repr_str = repr(cookie)
        assert 'test' in repr_str
        assert 'value' in repr_str
        assert 'example.com' in repr_str


class TestBrowserClientEdgeCases:
    """Edge case tests for BrowserClient"""

    def test_double_connect(self, browser_client):
        """Test connecting twice doesn't cause issues"""
        browser_client.connect()
        first_channel = browser_client.channel
        browser_client.connect()  # Second connect
        # Should create a new channel
        assert browser_client.channel is not None

    def test_double_disconnect(self, browser_client):
        """Test disconnecting twice doesn't cause issues"""
        browser_client.connect()
        browser_client.disconnect()
        browser_client.disconnect()  # Second disconnect
        assert browser_client.channel is None

    def test_operations_without_connect(self, mock_browser_stub):
        """Test that operations fail gracefully without connect"""
        c = client.BrowserClient('localhost', 50051)
        c.stub = mock_browser_stub  # Manually set stub without proper connect

        mock_response = MagicMock()
        mock_response.success = True
        mock_browser_stub.CreateBrowser.return_value = mock_response

        # Should work if stub is set
        result = c.create_browser('test-browser')
        assert result is True

    def test_empty_browser_id(self, browser_client, mock_browser_stub):
        """Test with empty browser ID"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error = "Browser ID cannot be empty"
        mock_browser_stub.CreateBrowser.return_value = mock_response

        browser_client.connect()
        result = browser_client.create_browser('')

        assert result is False

    def test_special_characters_in_url(self, browser_client, mock_browser_stub):
        """Test navigation with special characters in URL"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.status_code = 200
        mock_browser_stub.Navigate.return_value = mock_response

        browser_client.connect()
        status = browser_client.navigate('test-browser', 'https://example.com/path?query=value&foo=bar#anchor')

        assert status == 200

    def test_unicode_in_javascript(self, browser_client, mock_browser_stub):
        """Test JavaScript with unicode characters"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = '{"text": "中文测试 🎉"}'
        mock_browser_stub.ExecuteJS.return_value = mock_response

        browser_client.connect()
        result = browser_client.execute_js('test-browser', 'return "中文测试 🎉";')

        assert '中文测试' in result
