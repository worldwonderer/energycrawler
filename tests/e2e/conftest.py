"""
E2E test configuration and fixtures

This module provides fixtures for starting the Go Energy service
and managing test lifecycle.
"""

import pytest
import subprocess
import time
import os
import signal
import sys
from typing import Generator

# Disable proxy for localhost connections (gRPC to Energy service)
# This must be done before any gRPC imports
os.environ['NO_PROXY'] = os.environ.get('NO_PROXY', '') + ',localhost,127.0.0.1'
# Also unset proxy vars for this process if they're pointing to localhost
for var in ['http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY']:
    if var in os.environ:
        proxy_val = os.environ[var]
        if '127.0.0.1' in proxy_val or 'localhost' in proxy_val:
            del os.environ[var]

# Add energy_client to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'energy_client'))

try:
    from energy_client import client, browser_interface
except ImportError:
    import client
    import browser_interface


# Configuration
ENERGY_SERVICE_HOST = os.environ.get('ENERGY_SERVICE_HOST', 'localhost')
ENERGY_SERVICE_PORT = int(os.environ.get('ENERGY_SERVICE_PORT', '50051'))
ENERGY_SERVICE_PATH = os.environ.get(
    'ENERGY_SERVICE_PATH',
    os.path.join(os.path.dirname(__file__), '..', '..', 'energy-service')
)
ENERGY_SERVICE_BINARY = os.environ.get(
    'ENERGY_SERVICE_BINARY',
    os.path.join(ENERGY_SERVICE_PATH, 'energy-service')
)
SERVICE_STARTUP_TIMEOUT = int(os.environ.get('SERVICE_STARTUP_TIMEOUT', 30))


class EnergyServiceManager:
    """Manages the Energy service lifecycle for E2E tests"""

    def __init__(self):
        self.process = None
        self.host = ENERGY_SERVICE_HOST
        self.port = ENERGY_SERVICE_PORT

    def start(self) -> bool:
        """Start the Energy service"""
        print(f"Starting Energy service at {self.host}:{self.port}")

        # Check if binary exists
        if not os.path.exists(ENERGY_SERVICE_BINARY):
            # Try to build it
            print(f"Energy service binary not found at {ENERGY_SERVICE_BINARY}")
            print("Attempting to build...")
            self._build_service()
            if not os.path.exists(ENERGY_SERVICE_BINARY):
                raise FileNotFoundError(
                    f"Energy service binary not found at {ENERGY_SERVICE_BINARY}. "
                    "Please build it first: cd energy-service && go build -o energy-service ."
                )

        # Start the service
        env = os.environ.copy()
        env['GRPC_PORT'] = f":{self.port}"
        # Set display for macOS if not set
        if 'DISPLAY' not in env and os.name != 'nt':
            env['DISPLAY'] = ':0'

        self.process = subprocess.Popen(
            [ENERGY_SERVICE_BINARY],
            cwd=ENERGY_SERVICE_PATH,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )

        # Wait for service to be ready
        if not self._wait_for_service():
            # Check if process crashed
            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode('utf-8', errors='replace')
                raise RuntimeError(
                    f"Energy service crashed during startup. "
                    f"This usually means CEF/Chromium could not initialize.\n"
                    f"Ensure you have a display environment (GUI session or Xvfb).\n"
                    f"Error output: {stderr[:500]}"
                )
            return False

        return True

    def _build_service(self):
        """Build the Energy service"""
        try:
            subprocess.run(
                ['go', 'build', '-o', 'energy-service', '.'],
                cwd=ENERGY_SERVICE_PATH,
                check=True,
                capture_output=True
            )
            print("Energy service built successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to build Energy service: {e}")
            raise

    def _wait_for_service(self) -> bool:
        """Wait for service to be ready"""
        start_time = time.time()

        while time.time() - start_time < SERVICE_STARTUP_TIMEOUT:
            try:
                # Try to create a gRPC connection and actually test it
                test_client = client.BrowserClient(self.host, self.port)
                test_client.connect()
                # Actually verify the service responds by creating a test browser
                test_client.create_browser("__startup_test__", headless=True)
                test_client.close_browser("__startup_test__")
                test_client.disconnect()
                print(f"Energy service ready (startup time: {time.time() - start_time:.2f}s)")
                return True
            except Exception as e:
                time.sleep(0.5)

        return False

    def stop(self):
        """Stop the Energy service"""
        if self.process:
            print("Stopping Energy service...")
            if os.name == 'nt':
                self.process.terminate()
            else:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    self.process.kill()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)

            self.process = None
            print("Energy service stopped")

    def is_running(self) -> bool:
        """Check if service is running"""
        if self.process is None:
            return False
        return self.process.poll() is None


# Global availability check
_energy_service_available = None


def _check_energy_service_available() -> bool:
    """Check if the Energy gRPC service is running and accessible."""
    global _energy_service_available
    if _energy_service_available is not None:
        return _energy_service_available

    try:
        test_client = client.BrowserClient(ENERGY_SERVICE_HOST, ENERGY_SERVICE_PORT)
        test_client.connect()
        # Actually test that the service responds
        test_client.create_browser("__test__", headless=True)
        test_client.close_browser("__test__")
        test_client.disconnect()
        _energy_service_available = True
        return True
    except Exception:
        _energy_service_available = False
        return False


@pytest.fixture(scope="session")
def energy_service() -> Generator[EnergyServiceManager, None, None]:
    """
    Session-scoped fixture that checks if Energy service is running.

    Note: The Energy service requires a CEF (Chromium Embedded Framework)
    runtime environment with a display. This fixture will skip tests if
    the service is not running. Start the service manually using:

        cd /Users/pite/EnergyCrawler/energy-service && ./energy-service

    Or use: bash /Users/pite/EnergyCrawler/tests/e2e/start_service.sh
    """
    # Check if service is already running
    if _check_energy_service_available():
        # Service is already running, create a manager (but don't start it)
        service = EnergyServiceManager()
        yield service
        # No cleanup needed since we didn't start it
        return

    # Service not running - skip with clear instructions
    pytest.skip(
        "Energy service not running. "
        "Please start it manually:\n"
        "  cd /Users/pite/EnergyCrawler/energy-service && ./energy-service\n"
        "Or use: bash /Users/pite/EnergyCrawler/tests/e2e/start_service.sh"
    )


@pytest.fixture
def browser_client(energy_service: EnergyServiceManager) -> Generator[client.BrowserClient, None, None]:
    """
    Function-scoped fixture that provides a connected browser client.
    """
    test_client = client.BrowserClient(energy_service.host, energy_service.port)
    test_client.connect()

    yield test_client

    test_client.disconnect()


@pytest.fixture
def browser_backend(energy_service: EnergyServiceManager) -> Generator[browser_interface.EnergyBrowserBackend, None, None]:
    """
    Function-scoped fixture that provides a browser backend.
    """
    backend = browser_interface.EnergyBrowserBackend(
        energy_service.host,
        energy_service.port
    )
    backend.connect()

    # Verify the connection actually works
    try:
        # Try a simple operation to verify the service is responsive
        # Create a test browser to verify connection works
        backend.create_browser("__connection_test__", headless=True)
        backend.close_browser("__connection_test__")
    except Exception as e:
        pytest.skip(
            f"Energy service not responding at {energy_service.host}:{energy_service.port}: {e}"
        )

    yield backend

    backend.disconnect()


@pytest.fixture
def test_browser_id() -> str:
    """Generate a unique browser ID for each test"""
    import uuid
    return f"test-browser-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def browser(browser_client, test_browser_id):
    """
    Function-scoped fixture that creates a browser instance.
    Handles creation and cleanup automatically.
    """
    browser_client.create_browser(test_browser_id, headless=True)
    yield test_browser_id
    try:
        browser_client.close_browser(test_browser_id)
    except Exception:
        pass  # Browser may already be closed


# Pytest configuration
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "requires_energy: mark test as requiring Energy runtime"
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to tests based on location"""
    for item in items:
        # Mark all tests in e2e directory
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
