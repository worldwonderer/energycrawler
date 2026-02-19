"""
Energy Browser gRPC Client

A Python client for communicating with the Energy Browser Service.
This module provides a high-level interface for browser automation.
"""

import grpc
from typing import List, Dict, Optional
from dataclasses import dataclass

# Import generated protobuf modules
from . import browser_pb2
from . import browser_pb2_grpc


@dataclass
class Cookie:
    """Represents an HTTP cookie"""
    name: str
    value: str
    domain: str
    path: str
    secure: bool
    http_only: bool


class BrowserClient:
    """
    gRPC client for the Energy Browser Service.

    This client provides methods to interact with browser instances
    running in the Energy service.
    """

    def __init__(self, host: str = 'localhost', port: int = 50051):
        """
        Initialize the browser client.

        Args:
            host: The hostname of the Energy service
            port: The port number of the Energy service
        """
        self.host = host
        self.port = port
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[browser_pb2_grpc.BrowserServiceStub] = None

    def connect(self) -> None:
        """Establish connection to the Energy service."""
        self.channel = grpc.insecure_channel(f'{self.host}:{self.port}')
        self.stub = browser_pb2_grpc.BrowserServiceStub(self.channel)

    def disconnect(self) -> None:
        """Close the connection to the Energy service."""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def create_browser(self, browser_id: str, headless: bool = True) -> bool:
        """
        Create a new browser instance.

        Args:
            browser_id: Unique identifier for the browser
            headless: Whether to run in headless mode

        Returns:
            True if successful, False otherwise
        """
        request = browser_pb2.CreateBrowserRequest(
            browser_id=browser_id,
            headless=headless
        )
        response = self.stub.CreateBrowser(request)
        return response.success

    def close_browser(self, browser_id: str) -> bool:
        """
        Close a browser instance.

        Args:
            browser_id: The ID of the browser to close

        Returns:
            True if successful, False otherwise
        """
        request = browser_pb2.CloseBrowserRequest(browser_id=browser_id)
        response = self.stub.CloseBrowser(request)
        return response.success

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
        request = browser_pb2.NavigateRequest(
            browser_id=browser_id,
            url=url,
            timeout_ms=timeout_ms
        )
        response = self.stub.Navigate(request)
        if not response.success:
            raise Exception(f"Navigation failed: {response.error}")
        return response.status_code

    def get_cookies(self, browser_id: str, url: str) -> List[Cookie]:
        """
        Get cookies for a URL.

        Args:
            browser_id: The ID of the browser
            url: The URL to get cookies for

        Returns:
            List of Cookie objects
        """
        request = browser_pb2.GetCookiesRequest(
            browser_id=browser_id,
            url=url
        )
        response = self.stub.GetCookies(request)
        if not response.success:
            raise Exception(f"Get cookies failed: {response.error}")

        return [
            Cookie(
                name=c.name,
                value=c.value,
                domain=c.domain,
                path=c.path,
                secure=c.secure,
                http_only=c.http_only
            )
            for c in response.cookies
        ]

    def set_cookies(self, browser_id: str, cookies: List[Cookie]) -> bool:
        """
        Set cookies in the browser.

        Args:
            browser_id: The ID of the browser
            cookies: List of Cookie objects to set

        Returns:
            True if successful, False otherwise
        """
        pb_cookies = [
            browser_pb2.Cookie(
                name=c.name,
                value=c.value,
                domain=c.domain,
                path=c.path,
                secure=c.secure,
                http_only=c.http_only
            )
            for c in cookies
        ]

        request = browser_pb2.SetCookiesRequest(
            browser_id=browser_id,
            cookies=pb_cookies
        )
        response = self.stub.SetCookies(request)
        return response.success

    def execute_js(self, browser_id: str, script: str) -> str:
        """
        Execute JavaScript in the browser.

        Args:
            browser_id: The ID of the browser
            script: JavaScript code to execute

        Returns:
            Result of the script execution (JSON string)
        """
        request = browser_pb2.ExecuteJSRequest(
            browser_id=browser_id,
            script=script
        )
        response = self.stub.ExecuteJS(request)
        if not response.success:
            raise Exception(f"Execute JS failed: {response.error}")
        return response.result

    def set_proxy(self, browser_id: str, proxy_url: str,
                  username: str = '', password: str = '') -> bool:
        """
        Set proxy for a browser instance.

        Args:
            browser_id: The ID of the browser
            proxy_url: Proxy URL (e.g., "http://host:port")
            username: Proxy username (optional)
            password: Proxy password (optional)

        Returns:
            True if successful, False otherwise
        """
        request = browser_pb2.SetProxyRequest(
            browser_id=browser_id,
            proxy_url=proxy_url,
            username=username,
            password=password
        )
        response = self.stub.SetProxy(request)
        return response.success

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
        request = browser_pb2.ExecuteSignatureRequest(
            browser_id=browser_id,
            platform=platform,
            url=url
        )
        response = self.stub.ExecuteSignature(request)
        if not response.success:
            raise Exception(f"Execute signature failed: {response.error}")
        return dict(response.signatures)

    def click(self, browser_id: str, selector: str = '',
              x: int = 0, y: int = 0, timeout_ms: int = 5000) -> Dict:
        """
        Click on an element specified by CSS selector or coordinates.

        Args:
            browser_id: The ID of the browser
            selector: CSS selector (e.g., "#login-btn", ".submit-button")
                      If provided, takes precedence over coordinates.
            x: X coordinate (used if selector is empty)
            y: Y coordinate (used if selector is empty)
            timeout_ms: Timeout in milliseconds for waiting for element

        Returns:
            Dictionary with click result:
            - element_found: Whether element was found (for selector-based clicks)
            - clicked_x: Actual X coordinate clicked
            - clicked_y: Actual Y coordinate clicked
        """
        request = browser_pb2.ClickRequest(
            browser_id=browser_id,
            selector=selector,
            x=x,
            y=y,
            timeout_ms=timeout_ms
        )
        response = self.stub.Click(request)
        if not response.success:
            raise Exception(f"Click failed: {response.error}")
        return {
            'element_found': response.element_found,
            'clicked_x': response.clicked_x,
            'clicked_y': response.clicked_y
        }
