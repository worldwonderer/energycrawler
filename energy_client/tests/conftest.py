"""
Pytest configuration and fixtures for energy_client tests
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, Mock
from typing import Generator
from concurrent import futures
import grpc

# Add energy_client to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import energy_client modules
try:
    from energy_client import client, browser_interface
except ImportError:
    # For when running from tests directory
    import client
    import browser_interface


@pytest.fixture
def mock_grpc_channel():
    """Create a mock gRPC channel"""
    channel = MagicMock()
    channel.close = MagicMock()
    return channel


@pytest.fixture
def mock_browser_stub():
    """Create a mock browser service stub with common responses"""
    stub = MagicMock()
    return stub


@pytest.fixture
def mock_grpc_server():
    """
    Create a mock gRPC server for integration testing.
    This provides a more complete mock of the gRPC server infrastructure.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    # Server starts on a random available port
    port = server.add_insecure_port('[::]:0')
    server.start()
    yield server, port
    server.stop(grace=0)


@pytest.fixture
def browser_client(mock_grpc_channel, mock_browser_stub):
    """Create a browser client with mocked gRPC components"""
    with patch('energy_client.client.grpc.insecure_channel') as mock_channel, \
         patch('energy_client.client.browser_pb2_grpc.BrowserServiceStub') as mock_stub_class:
        mock_channel.return_value = mock_grpc_channel
        mock_stub_class.return_value = mock_browser_stub
        client_instance = client.BrowserClient('localhost', 50051)
        client_instance.channel = mock_grpc_channel
        client_instance.stub = mock_browser_stub
        yield client_instance


@pytest.fixture
def sample_cookie():
    """Create a sample cookie for testing"""
    return client.Cookie(
        name='test_cookie',
        value='test_value',
        domain='example.com',
        path='/',
        secure=False,
        http_only=False
    )


@pytest.fixture
def sample_cookies(sample_cookie):
    """Create a list of sample cookies"""
    return [
        sample_cookie,
        client.Cookie(
            name='session_id',
            value='abc123',
            domain='example.com',
            path='/',
            secure=True,
            http_only=True
        )
    ]


@pytest.fixture
def mock_browser_backend(browser_client):
    """Create a browser backend with mocked client"""
    backend = browser_interface.EnergyBrowserBackend('localhost', 50051)
    backend._client = browser_client
    yield backend


@pytest.fixture
def sample_pb_cookie():
    """Create a sample protobuf cookie"""
    from . import browser_pb2
    return browser_pb2.Cookie(
        name='test_cookie',
        value='test_value',
        domain='example.com',
        path='/',
        secure=False,
        http_only=False
    )


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mocks after each test"""
    yield
    # Cleanup after test


# Test configuration
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
