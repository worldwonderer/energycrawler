"""
Tests for BrowserInterface and EnergyBrowserBackend
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import List
import json

# Import from energy_client
from energy_client import browser_interface
from energy_client.browser_interface import (
    BrowserInterface,
    Cookie,
    EnergyBrowserBackend,
    create_browser_backend
)
from energy_client import client as client_module


class TestCookieDataclass:
    """Test cases for Cookie dataclass"""

    def test_cookie_creation(self):
        """Test creating a cookie"""
        cookie = Cookie(
            name='test',
            value='value',
            domain='example.com',
            path='/test',
            secure=True,
            http_only=True
        )

        assert cookie.name == 'test'
        assert cookie.value == 'value'
        assert cookie.domain == 'example.com'
        assert cookie.path == '/test'
        assert cookie.secure is True
        assert cookie.http_only is True

    def test_cookie_defaults(self):
        """Test cookie default values"""
        cookie = Cookie(
            name='test',
            value='value'
        )

        assert cookie.domain == ''
        assert cookie.path == '/'
        assert cookie.secure is False
        assert cookie.http_only is False

    def test_cookie_partial_values(self):
        """Test cookie with partial values"""
        cookie = Cookie(
            name='session',
            value='abc123',
            domain='api.example.com'
        )

        assert cookie.name == 'session'
        assert cookie.domain == 'api.example.com'
        assert cookie.path == '/'  # Default
        assert cookie.secure is False  # Default

    def test_cookie_equality(self):
        """Test cookie equality"""
        cookie1 = Cookie(name='test', value='val', domain='ex.com', path='/', secure=False, http_only=False)
        cookie2 = Cookie(name='test', value='val', domain='ex.com', path='/', secure=False, http_only=False)

        assert cookie1 == cookie2

    def test_cookie_inequality(self):
        """Test cookie inequality"""
        cookie1 = Cookie(name='test1', value='val', domain='', path='/', secure=False, http_only=False)
        cookie2 = Cookie(name='test2', value='val', domain='', path='/', secure=False, http_only=False)

        assert cookie1 != cookie2


class TestBrowserInterfaceAbstract:
    """Test that BrowserInterface is properly abstract"""

    def test_abstract_methods(self):
        """Test that BrowserInterface has all required abstract methods"""
        abstract_methods = [
            'create_browser', 'close_browser', 'navigate',
            'get_cookies', 'set_cookies', 'execute_js',
            'set_proxy', 'execute_signature'
        ]

        for method_name in abstract_methods:
            assert hasattr(BrowserInterface, method_name)
            method = getattr(BrowserInterface, method_name)
            assert callable(method)

    def test_cannot_instantiate_abstract(self):
        """Test that BrowserInterface cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BrowserInterface()

    def test_subclass_must_implement_all_methods(self):
        """Test that subclasses must implement all abstract methods"""
        class IncompleteBackend(BrowserInterface):
            pass

        with pytest.raises(TypeError):
            IncompleteBackend()

    def test_partial_implementation_fails(self):
        """Test that partial implementation fails"""
        class PartialBackend(BrowserInterface):
            def create_browser(self, browser_id: str, headless: bool = True) -> bool:
                return True

        with pytest.raises(TypeError):
            PartialBackend()


class TestEnergyBrowserBackend:
    """Test cases for EnergyBrowserBackend"""

    def test_init(self):
        """Test backend initialization"""
        backend = EnergyBrowserBackend('localhost', 50051)
        assert backend._connected is False
        assert backend._client is not None

    def test_init_with_defaults(self):
        """Test backend initialization with default values"""
        backend = EnergyBrowserBackend()
        assert backend._connected is False

    def test_connect(self):
        """Test connecting backend"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            mock_client.connect.assert_called_once()
            assert backend._connected is True

    def test_disconnect(self):
        """Test disconnecting backend"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()
            backend.disconnect()

            mock_client.disconnect.assert_called_once()
            assert backend._connected is False

    def test_context_manager(self):
        """Test context manager protocol"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with EnergyBrowserBackend('localhost', 50051) as backend:
                assert backend is not None
                assert backend._connected is True

            mock_client.disconnect.assert_called_once()

    def test_context_manager_with_exception(self):
        """Test context manager handles exceptions"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            try:
                with EnergyBrowserBackend('localhost', 50051) as backend:
                    raise ValueError("Test error")
            except ValueError:
                pass

            # Should still disconnect
            mock_client.disconnect.assert_called_once()

    def test_all_methods_delegated(self):
        """Test all methods are properly delegated to client"""
        methods_to_test = [
            ('create_browser', ('test-id',), {'headless': True}, True),
            ('close_browser', ('test-id',), {}, True),
            ('navigate', ('test-id', 'https://example.com'), {}, 200),
            ('set_proxy', ('test-id', 'http://proxy:8080'), {'username': 'user', 'password': 'pass'}, True),
            ('execute_signature', ('test-id', 'xhs', 'https://xhs.com'), {}, {'x-s': 'sig'}),
        ]

        for method_name, args, kwargs, return_value in methods_to_test:
            with patch.object(client_module, 'BrowserClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                getattr(mock_client, method_name).return_value = return_value

                backend = EnergyBrowserBackend('localhost', 50051)
                backend.connect()

                method = getattr(backend, method_name)
                result = method(*args, **kwargs)

                assert result == return_value
                getattr(mock_client, method_name).assert_called_once()

    def test_create_browser(self):
        """Test create_browser delegation"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.create_browser.return_value = True
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            result = backend.create_browser('test-id', headless=True)
            assert result is True
            mock_client.create_browser.assert_called_once_with('test-id', True)

    def test_close_browser(self):
        """Test close_browser delegation"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.close_browser.return_value = True
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            result = backend.close_browser('test-id')
            assert result is True
            mock_client.close_browser.assert_called_once_with('test-id')

    def test_navigate(self):
        """Test navigate delegation"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.navigate.return_value = 200
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            status = backend.navigate('test-id', 'https://example.com')
            assert status == 200
            mock_client.navigate.assert_called_once()

    def test_navigate_with_timeout(self):
        """Test navigate with custom timeout"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.navigate.return_value = 200
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            status = backend.navigate('test-id', 'https://example.com', timeout_ms=60000)
            assert status == 200
            mock_client.navigate.assert_called_once_with('test-id', 'https://example.com', 60000)

    def test_get_cookies(self):
        """Test get_cookies delegation"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_cookies.return_value = [
                client_module.Cookie(
                    name='test',
                    value='value',
                    domain='example.com',
                    path='/',
                    secure=False,
                    http_only=False
                )
            ]
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            cookies = backend.get_cookies('test-id', 'https://example.com')
            assert len(cookies) == 1
            assert isinstance(cookies[0], Cookie)
            assert cookies[0].name == 'test'

    def test_get_cookies_empty(self):
        """Test get_cookies with empty result"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_cookies.return_value = []
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            cookies = backend.get_cookies('test-id', 'https://example.com')
            assert len(cookies) == 0

    def test_set_cookies(self):
        """Test set_cookies delegation"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.set_cookies.return_value = True
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            cookies = [Cookie(name='test', value='value', domain='', path='/', secure=False, http_only=False)]
            result = backend.set_cookies('test-id', cookies)
            assert result is True
            mock_client.set_cookies.assert_called_once()

    def test_set_cookies_multiple(self):
        """Test set_cookies with multiple cookies"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.set_cookies.return_value = True
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            cookies = [
                Cookie(name='c1', value='v1', domain='', path='/', secure=False, http_only=False),
                Cookie(name='c2', value='v2', domain='', path='/', secure=True, http_only=True),
            ]
            result = backend.set_cookies('test-id', cookies)
            assert result is True

    def test_execute_js(self):
        """Test execute_js delegation"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.execute_js.return_value = '{"result": 42}'
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            result = backend.execute_js('test-id', 'return 42;')
            assert result == {'result': 42}
            mock_client.execute_js.assert_called_once_with('test-id', 'return 42;')

    def test_execute_js_empty_result(self):
        """Test execute_js with empty result"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.execute_js.return_value = ''
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            result = backend.execute_js('test-id', 'return null;')
            assert result is None

    def test_execute_js_none_result(self):
        """Test execute_js with None result"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.execute_js.return_value = None
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            result = backend.execute_js('test-id', 'return undefined;')
            assert result is None

    def test_execute_js_complex_result(self):
        """Test execute_js with complex JSON result"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.execute_js.return_value = '{"data": {"items": [1, 2, 3]}, "meta": {"count": 3}}'
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            result = backend.execute_js('test-id', 'return getData();')
            assert result['data']['items'] == [1, 2, 3]
            assert result['meta']['count'] == 3

    def test_set_proxy(self):
        """Test set_proxy delegation"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.set_proxy.return_value = True
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            result = backend.set_proxy('test-id', 'http://proxy:8080', 'user', 'pass')
            assert result is True
            mock_client.set_proxy.assert_called_once_with('test-id', 'http://proxy:8080', 'user', 'pass')

    def test_set_proxy_without_auth(self):
        """Test set_proxy without authentication"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.set_proxy.return_value = True
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            result = backend.set_proxy('test-id', 'http://proxy:8080')
            assert result is True
            mock_client.set_proxy.assert_called_once_with('test-id', 'http://proxy:8080', '', '')

    def test_execute_signature(self):
        """Test execute_signature delegation"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.execute_signature.return_value = {'x-s': 'sig', 'x-t': 'time'}
            mock_client_class.return_value = mock_client

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            sigs = backend.execute_signature('test-id', 'xhs', 'https://example.com')
            assert 'x-s' in sigs
            assert 'x-t' in sigs
            mock_client.execute_signature.assert_called_once()

    def test_execute_signature_multiple_platforms(self):
        """Test execute_signature for different platforms"""
        platforms = [
            ('xhs', {'x-s': 'xhs_sig', 'x-t': 'time'}),
            ('douyin', {'_signature': 'dy_sig', 'X-Bogus': 'bogus'}),
            ('bilibili', {'buvid3': 'bili_sig'}),
        ]

        for platform, expected_sigs in platforms:
            with patch.object(client_module, 'BrowserClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client.execute_signature.return_value = expected_sigs
                mock_client_class.return_value = mock_client

                backend = EnergyBrowserBackend('localhost', 50051)
                backend.connect()

                sigs = backend.execute_signature('test-id', platform, 'https://example.com')
                assert sigs == expected_sigs


class TestCreateBrowserBackend:
    """Test cases for create_browser_backend factory function"""

    def test_create_energy_backend(self):
        """Test creating energy backend"""
        backend = create_browser_backend('energy', host='localhost', port=50051)
        assert isinstance(backend, EnergyBrowserBackend)

    def test_create_energy_backend_with_defaults(self):
        """Test creating energy backend with default parameters"""
        backend = create_browser_backend('energy')
        assert isinstance(backend, EnergyBrowserBackend)

    def test_create_drission_backend(self):
        """Test creating drission backend (not implemented)"""
        with pytest.raises(NotImplementedError) as exc_info:
            create_browser_backend('drission')

        assert "not yet implemented" in str(exc_info.value)

    def test_create_unknown_backend(self):
        """Test creating unknown backend"""
        with pytest.raises(ValueError) as exc_info:
            create_browser_backend('unknown')

        assert "Unknown backend type" in str(exc_info.value)

    def test_create_backend_case_sensitive(self):
        """Test that backend type is case-sensitive"""
        with pytest.raises(ValueError):
            create_browser_backend('ENERGY')

    def test_create_backend_empty_type(self):
        """Test with empty backend type"""
        with pytest.raises(ValueError):
            create_browser_backend('')


class TestEnergyBrowserBackendIntegration:
    """Integration-style tests for EnergyBrowserBackend"""

    def test_full_workflow(self):
        """Test a typical workflow using the backend"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Setup mock responses
            mock_client.create_browser.return_value = True
            mock_client.navigate.return_value = 200
            mock_client.get_cookies.return_value = []
            mock_client.execute_js.return_value = '{"title": "Test Page"}'
            mock_client.close_browser.return_value = True

            # Execute workflow
            with EnergyBrowserBackend('localhost', 50051) as backend:
                # Create browser
                assert backend.create_browser('test-browser', headless=True)

                # Navigate
                status = backend.navigate('test-browser', 'https://example.com')
                assert status == 200

                # Execute JS
                result = backend.execute_js('test-browser', 'document.title')
                assert result == {'title': 'Test Page'}

                # Close browser
                assert backend.close_browser('test-browser')

            # Verify all calls were made
            mock_client.create_browser.assert_called_once()
            mock_client.navigate.assert_called_once()
            mock_client.execute_js.assert_called_once()
            mock_client.close_browser.assert_called_once()

    def test_error_propagation(self):
        """Test that errors are properly propagated"""
        with patch.object(client_module, 'BrowserClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_client.create_browser.side_effect = Exception("Connection failed")

            backend = EnergyBrowserBackend('localhost', 50051)
            backend.connect()

            with pytest.raises(Exception) as exc_info:
                backend.create_browser('test-browser')

            assert "Connection failed" in str(exc_info.value)
