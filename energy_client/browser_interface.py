"""
Browser Interface - Abstract base class for browser automation

This module provides an abstract interface that can be implemented
by different browser backends (DrissionPage, Energy, etc.)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class Cookie:
    """Represents an HTTP cookie"""
    name: str
    value: str
    domain: str = ''
    path: str = '/'
    secure: bool = False
    http_only: bool = False


class BrowserInterface(ABC):
    """
    Abstract base class for browser automation.

    This interface provides a common API that can be implemented
    by different browser backends, allowing for easy switching
    between implementations.
    """

    @abstractmethod
    def create_browser(self, browser_id: str, headless: bool = True) -> bool:
        """
        Create a new browser instance.

        Args:
            browser_id: Unique identifier for the browser
            headless: Whether to run in headless mode

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def close_browser(self, browser_id: str) -> bool:
        """
        Close a browser instance.

        Args:
            browser_id: The ID of the browser to close

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def navigate(self, browser_id: str, url: str, timeout_ms: int = 30000) -> int:
        """
        Navigate to a URL.

        Args:
            browser_id: The ID of the browser
            url: The URL to navigate to
            timeout_ms: Timeout in milliseconds

        Returns:
            HTTP status code
        """
        pass

    @abstractmethod
    def get_cookies(self, browser_id: str, url: str) -> List[Cookie]:
        """
        Get cookies for a URL.

        Args:
            browser_id: The ID of the browser
            url: The URL to get cookies for

        Returns:
            List of Cookie objects
        """
        pass

    @abstractmethod
    def set_cookies(self, browser_id: str, cookies: List[Cookie]) -> bool:
        """
        Set cookies in the browser.

        Args:
            browser_id: The ID of the browser
            cookies: List of Cookie objects to set

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def execute_js(self, browser_id: str, script: str) -> Any:
        """
        Execute JavaScript in the browser.

        Args:
            browser_id: The ID of the browser
            script: JavaScript code to execute

        Returns:
            Result of the script execution
        """
        pass

    @abstractmethod
    def set_proxy(self, browser_id: str, proxy_url: str,
                  username: str = '', password: str = '') -> bool:
        """
        Set proxy for a browser instance.

        Args:
            browser_id: The ID of the browser
            proxy_url: Proxy URL
            username: Proxy username (optional)
            password: Proxy password (optional)

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def execute_signature(self, browser_id: str, platform: str,
                          url: str) -> Dict[str, str]:
        """
        Execute platform-specific signature generation.

        Args:
            browser_id: The ID of the browser
            platform: Platform name (e.g., "xhs", "douyin")
            url: The URL to generate signatures for

        Returns:
            Dictionary of signature values
        """
        pass


class EnergyBrowserBackend(BrowserInterface):
    """
    Energy browser backend implementation.

    This class implements the BrowserInterface using the Energy
    gRPC service for browser automation.
    """

    def __init__(self, host: str = 'localhost', port: int = 50051):
        """
        Initialize the Energy backend.

        Args:
            host: The hostname of the Energy service
            port: The port number of the Energy service
        """
        from .client import BrowserClient
        self._client = BrowserClient(host, port)
        self._connected = False

    def connect(self) -> None:
        """Connect to the Energy service."""
        self._client.connect()
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect from the Energy service."""
        self._client.disconnect()
        self._connected = False

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def create_browser(self, browser_id: str, headless: bool = True) -> bool:
        return self._client.create_browser(browser_id, headless)

    def close_browser(self, browser_id: str) -> bool:
        return self._client.close_browser(browser_id)

    def navigate(self, browser_id: str, url: str, timeout_ms: int = 30000) -> int:
        return self._client.navigate(browser_id, url, timeout_ms)

    def get_cookies(self, browser_id: str, url: str) -> List[Cookie]:
        # Convert from client Cookie to interface Cookie
        client_cookies = self._client.get_cookies(browser_id, url)
        return [
            Cookie(
                name=c.name,
                value=c.value,
                domain=c.domain,
                path=c.path,
                secure=c.secure,
                http_only=c.http_only
            )
            for c in client_cookies
        ]

    def set_cookies(self, browser_id: str, cookies: List[Cookie]) -> bool:
        # Convert from interface Cookie to client Cookie
        from .client import Cookie as ClientCookie
        client_cookies = [
            ClientCookie(
                name=c.name,
                value=c.value,
                domain=c.domain,
                path=c.path,
                secure=c.secure,
                http_only=c.http_only
            )
            for c in cookies
        ]
        return self._client.set_cookies(browser_id, client_cookies)

    def execute_js(self, browser_id: str, script: str) -> Any:
        import json
        result = self._client.execute_js(browser_id, script)
        if result:
            return json.loads(result)
        return None

    def set_proxy(self, browser_id: str, proxy_url: str,
                  username: str = '', password: str = '') -> bool:
        return self._client.set_proxy(browser_id, proxy_url, username, password)

    def execute_signature(self, browser_id: str, platform: str,
                          url: str) -> Dict[str, str]:
        return self._client.execute_signature(browser_id, platform, url)


# Factory function for creating browser backends
def create_browser_backend(backend_type: str = 'energy',
                           **kwargs) -> BrowserInterface:
    """
    Create a browser backend instance.

    Args:
        backend_type: Type of backend ('energy' or 'drission')
        **kwargs: Additional arguments passed to the backend constructor

    Returns:
        BrowserInterface instance
    """
    if backend_type == 'energy':
        return EnergyBrowserBackend(**kwargs)
    elif backend_type == 'drission':
        # Placeholder for DrissionPage backend
        raise NotImplementedError("DrissionPage backend not yet implemented")
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")
