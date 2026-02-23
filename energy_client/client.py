"""
Energy Browser gRPC Client

A Python client for communicating with the Energy Browser Service.
This module provides a high-level interface for browser automation.
"""

import grpc
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import urlparse

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
        # Disable HTTP proxy for gRPC channel to avoid localhost requests
        # being hijacked by system proxy (e.g. 127.0.0.1:8001).
        self.channel = grpc.insecure_channel(
            f'{self.host}:{self.port}',
            options=[('grpc.enable_http_proxy', 0)],
        )
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
        self._validate_navigate_url(url)
        request = browser_pb2.NavigateRequest(
            browser_id=browser_id,
            url=url,
            timeout_ms=timeout_ms
        )
        response = self.stub.Navigate(request)
        if not response.success:
            raise Exception(f"Navigation failed: {response.error}")
        return response.status_code

    @staticmethod
    def _validate_navigate_url(url: str) -> None:
        parsed = urlparse((url or "").strip())
        is_http = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        is_file = parsed.scheme == "file" and bool(parsed.path)
        if not (is_http or is_file):
            raise ValueError(f"Invalid URL for navigation: {url}")

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
        response = None
        last_error = ""
        for attempt in range(2):
            response = self.stub.GetCookies(request)
            if response.success:
                break
            last_error = response.error or ""
            if self._is_timeout_error(last_error) and attempt == 0:
                time.sleep(0.5)
                continue
            if self._is_timeout_error(last_error):
                # Some service/runtime combinations intermittently time out on
                # cookie retrieval for third-party domains. Return empty list
                # instead of failing hard so callers can proceed safely.
                return []
            raise Exception(f"Get cookies failed: {last_error}")

        if response is None or not response.success:
            return []

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
            error = response.error or ""
            if self._is_timeout_error(error):
                fallback_script = self._build_js_fallback_script(script)
                if fallback_script:
                    fallback_resp = self.stub.ExecuteJS(
                        browser_pb2.ExecuteJSRequest(
                            browser_id=browser_id,
                            script=fallback_script,
                        )
                    )
                    if fallback_resp.success:
                        return fallback_resp.result
            raise Exception(f"Execute JS failed: {error}")
        return response.result

    @staticmethod
    def _is_timeout_error(error: str) -> bool:
        return "timeout" in (error or "").lower()

    @staticmethod
    def _build_js_fallback_script(script: str) -> str:
        normalized_lines = [line.strip() for line in (script or "").splitlines() if line.strip()]
        if len(normalized_lines) <= 1:
            return ""

        last_line = normalized_lines[-1]
        if last_line.startswith("return "):
            return f"(function(){{\n{script}\n}})()"

        if last_line.endswith(";"):
            last_line = last_line[:-1].strip()

        body = "\n".join(normalized_lines[:-1])
        if body:
            body += "\n"
        return f"(function(){{\n{body}return ({last_line});\n}})()"

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
            platform: Platform name (supported: "xhs")
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
