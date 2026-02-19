# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# Declaration: This code is for learning and research purposes only. Users should follow these principles:
# 1. Not for any commercial use.
# 2. Comply with the terms of service and robots.txt rules of the target platform.
# 3. No large-scale crawling or operational disruption to the platform.
# 4. Reasonably control request frequency to avoid unnecessary burden on the target platform.
# 5. Not for any illegal or improper purposes.
#
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# Using this code means you agree to abide by the above principles and all terms in the LICENSE.

"""
Twitter/X.com Login Module

Supports:
- Cookie-based login (auth_token + ct0)
- QR code login (via Energy browser)
"""

import asyncio
import base64
import functools
import sys
from typing import Optional, Dict

from tenacity import (RetryError, retry, retry_if_result, stop_after_attempt,
                      wait_fixed)

from tools import utils
from base.base_crawler import AbstractLogin

from .energy_adapter import TwitterEnergyAdapter
from .exception import TwitterAuthError


class TwitterLogin(AbstractLogin):
    """
    Twitter/X.com Login Handler

    This class provides login functionality for Twitter/X.com platform
    using the Energy browser service for cookie-based and QR code authentication.
    """

    TWITTER_LOGIN_URL = "https://x.com/login"
    TWITTER_HOME_URL = "https://x.com/home"

    def __init__(
        self,
        login_type: str,
        cookie_str: str = "",
        energy_adapter: Optional[TwitterEnergyAdapter] = None,
    ):
        """
        Initialize Twitter login handler.

        Args:
            login_type: Login type - "qrcode" or "cookie"
            cookie_str: Cookie string for cookie-based login
            energy_adapter: Twitter Energy adapter instance (required)
        """
        self.login_type = login_type
        self.cookie_str = cookie_str
        self._adapter = energy_adapter

        if self._adapter is None:
            raise ValueError("[TwitterLogin] Energy adapter is required for Twitter login")

    @retry(
        stop=stop_after_attempt(600),
        wait=wait_fixed(1),
        retry=retry_if_result(lambda value: value is False)
    )
    async def check_login_state(self, no_auth_token: str = "") -> bool:
        """
        Verify login status by checking cookie changes.

        Args:
            no_auth_token: The auth_token value when not logged in (for comparison)

        Returns:
            True if login successful, False otherwise
        """
        # Get current cookies
        current_cookies = self._adapter.get_auth_cookies()
        current_auth_token = current_cookies.get(self._adapter.AUTH_COOKIE_NAME, "")

        # If auth_token has changed and is not empty, consider login successful
        if current_auth_token and current_auth_token != no_auth_token:
            utils.logger.info(
                "[TwitterLogin.check_login_state] Login status confirmed by Cookie (auth_token changed)."
            )
            return True

        return False

    async def begin(self):
        """
        Start login process for Twitter/X.com.
        """
        utils.logger.info("[TwitterLogin.begin] Begin login Twitter/X.com ...")

        if self.login_type == "qrcode":
            await self.login_by_qrcode()
        elif self.login_type == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError(
                "[TwitterLogin.begin] Invalid Login Type. "
                "Currently only supported: qrcode, cookie"
            )

    async def login_by_qrcode(self):
        """
        Login Twitter/X.com by QR code via Energy browser.

        This method:
        1. Navigates to Twitter login page
        2. Captures QR code image
        3. Displays QR code to user
        4. Waits for user to scan with mobile app
        5. Polls for login completion
        """
        utils.logger.info("[TwitterLogin.login_by_qrcode] Begin login Twitter by qrcode ...")

        # Navigate to login page
        await self._adapter.navigate(self.TWITTER_LOGIN_URL)
        await asyncio.sleep(2)

        # Get QR code image
        qrcode_img = await self._get_qrcode_image()

        if not qrcode_img:
            utils.logger.error(
                "[TwitterLogin.login_by_qrcode] Login failed, could not get QR code"
            )
            sys.exit(1)

        # Get current auth_token before login (for comparison)
        current_cookies = self._adapter.get_auth_cookies()
        no_auth_token = current_cookies.get(self._adapter.AUTH_COOKIE_NAME, "")

        # Display QR code to user
        base64_qrcode_img = base64.b64encode(qrcode_img).decode('utf-8')
        partial_show_qrcode = functools.partial(utils.show_qrcode, base64_qrcode_img)
        asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)

        utils.logger.info(
            "[TwitterLogin.login_by_qrcode] Waiting for scan code login, timeout is 600s"
        )

        # Poll for login completion
        try:
            await self.check_login_state(no_auth_token)
        except RetryError:
            utils.logger.error(
                "[TwitterLogin.login_by_qrcode] Login Twitter failed by qrcode method"
            )
            sys.exit(1)

        # Wait for redirect after successful login
        wait_redirect_seconds = 5
        utils.logger.info(
            f"[TwitterLogin.login_by_qrcode] Login successful, "
            f"waiting {wait_redirect_seconds}s for redirect ..."
        )
        await asyncio.sleep(wait_redirect_seconds)

    async def _get_qrcode_image(self) -> Optional[bytes]:
        """
        Get QR code image from Energy browser.

        The QR code is typically displayed on the login page. This method
        tries to capture it using JavaScript canvas conversion.

        Returns:
            QR code image as bytes, or None if failed
        """
        try:
            # First, try to find and capture the QR code canvas/image
            script = """
            (function() {
                // Try to find QR code image
                const qrImage = document.querySelector('img[src*="qr"]');
                if (qrImage) {
                    return qrImage.src;
                }

                // Try to find QR code in canvas
                const canvas = document.querySelector('canvas');
                if (canvas) {
                    return canvas.toDataURL('image/png');
                }

                return null;
            })();
            """

            result = await self._adapter.execute_js(script)

            if result and result.lower() not in ['null', 'undefined', '']:
                # Clean up result
                result = result.strip('"').strip("'")

                # If it's a data URL, extract the base64 part
                if result.startswith('data:image'):
                    # Format: data:image/png;base64,<base64_data>
                    base64_data = result.split(',', 1)[-1]
                    return base64.b64decode(base64_data)

                # If it's a URL, we would need to fetch it (simplified for now)
                utils.logger.warning(
                    "[TwitterLogin._get_qrcode_image] QR code is a URL, "
                    "canvas capture recommended"
                )

            # Fallback: wait for page to fully load and try again
            await asyncio.sleep(2)

            # Try taking a screenshot of the QR code area
            screenshot_script = """
            (function() {
                // Try to find the QR code container
                const qrContainer = document.querySelector('[data-testid="qrCode"]') ||
                                   document.querySelector('canvas') ||
                                   document.querySelector('img[src*="qr"]');

                if (!qrContainer) {
                    return null;
                }

                // If it's a canvas, convert to data URL
                if (qrContainer.tagName === 'CANVAS') {
                    return qrContainer.toDataURL('image/png');
                }

                // If it's an image, return its src
                if (qrContainer.tagName === 'IMG') {
                    return qrContainer.src;
                }

                return null;
            })();
            """

            result = await self._adapter.execute_js(screenshot_script)

            if result and result.lower() not in ['null', 'undefined', '']:
                result = result.strip('"').strip("'")
                if result.startswith('data:image'):
                    base64_data = result.split(',', 1)[-1]
                    return base64.b64decode(base64_data)

            utils.logger.error("[TwitterLogin._get_qrcode_image] Could not find QR code on page")
            return None

        except Exception as e:
            utils.logger.error(f"[TwitterLogin._get_qrcode_image] Error getting QR code: {e}")
            return None

    async def login_by_cookies(self):
        """
        Login Twitter/X.com website by cookies.

        This method sets the auth_token and ct0 cookies directly in the browser.
        """
        utils.logger.info("[TwitterLogin.login_by_cookies] Begin login Twitter by cookie ...")

        if not self.cookie_str:
            utils.logger.warning("[TwitterLogin.login_by_cookies] No cookie string provided")
            return

        # Parse cookie string to dict
        # Support formats:
        # 1. "auth_token=xxx; ct0=yyy"
        # 2. "auth_token=xxx;ct0=yyy"
        cookie_dict = utils.convert_str_cookie_to_dict(self.cookie_str)

        if not cookie_dict:
            utils.logger.error("[TwitterLogin.login_by_cookies] Failed to parse cookie string")
            raise TwitterAuthError("Invalid cookie string format")

        # Validate required cookies
        if self._adapter.AUTH_COOKIE_NAME not in cookie_dict:
            utils.logger.warning(
                f"[TwitterLogin.login_by_cookies] Cookie string missing {self._adapter.AUTH_COOKIE_NAME}"
            )

        # Set cookies via Energy adapter
        try:
            success = self._adapter.set_cookies_from_dict(cookie_dict, domain=".x.com")

            if success:
                utils.logger.info("[TwitterLogin.login_by_cookies] Cookies set successfully")

                # Navigate to home page to verify cookies work
                await self._adapter.navigate(self.TWITTER_HOME_URL)
                await asyncio.sleep(2)

                # Verify login state
                if await self._adapter.verify_login_via_page():
                    utils.logger.info("[TwitterLogin.login_by_cookies] Login verified successfully")
                else:
                    utils.logger.warning(
                        "[TwitterLogin.login_by_cookies] Cookies set but login verification failed"
                    )
            else:
                utils.logger.error("[TwitterLogin.login_by_cookies] Failed to set cookies")
                raise TwitterAuthError("Failed to set cookies in browser")

        except Exception as e:
            utils.logger.error(f"[TwitterLogin.login_by_cookies] Error setting cookies: {e}")
            raise TwitterAuthError(f"Cookie login failed: {e}")

    async def check_login_state_simple(self) -> bool:
        """
        Simple login state check (without retry).

        Returns:
            True if logged in, False otherwise
        """
        return self._adapter.check_login_state()

    async def get_auth_cookies(self) -> Dict[str, str]:
        """
        Get authentication cookies.

        Returns:
            Dict with auth_token and ct0
        """
        return self._adapter.get_auth_cookies()
