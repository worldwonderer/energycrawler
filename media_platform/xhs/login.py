# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/media_platform/xhs/login.py
# GitHub: https://github.com/EnergyCrawler
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


"""
XiaoHongShu Login - Energy Browser Only

This module provides login functionality for Xiaohongshu (XHS) platform
using the Energy browser service. No legacy browser-driver dependency required.
"""

import asyncio
import base64
import functools
import sys
from typing import Optional

from tenacity import (RetryError, retry, retry_if_result, stop_after_attempt,
                      wait_fixed)

import config
from base.base_crawler import AbstractLogin
from cache.cache_factory import CacheFactory
from tools import utils


class XiaoHongShuLogin(AbstractLogin):
    """
    XiaoHongShu Login - Energy Browser Only

    This class provides login functionality using the Energy browser service.
    No legacy browser-driver dependency is required.
    """

    def __init__(self,
                 login_type: str,
                 login_phone: Optional[str] = "",
                 cookie_str: str = "",
                 energy_adapter=None
                 ):
        config.LOGIN_TYPE = login_type
        self.login_phone = login_phone
        self.cookie_str = cookie_str
        self.energy_adapter = energy_adapter  # Energy browser adapter (required)

        if self.energy_adapter is None:
            raise ValueError("Energy adapter is required for XiaoHongShuLogin")

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self, no_logged_in_session: str) -> bool:
        """
        Verify login status by checking cookie changes.
        """
        # Check for cookie changes
        current_cookies = self.energy_adapter.get_cookies()
        current_web_session = current_cookies.get("web_session")

        # If web_session has changed, consider the login successful
        if current_web_session and current_web_session != no_logged_in_session:
            utils.logger.info("[XiaoHongShuLogin.check_login_state] Login status confirmed by Cookie (web_session changed).")
            return True

        return False

    async def begin(self):
        """Start login xiaohongshu"""
        utils.logger.info("[XiaoHongShuLogin.begin] Begin login xiaohongshu ...")

        if config.LOGIN_TYPE == "qrcode":
            await self.login_by_qrcode()
        elif config.LOGIN_TYPE == "phone":
            await self.login_by_mobile()
        elif config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[XiaoHongShuLogin.begin] Invalid Login Type. Currently only supported qrcode or phone or cookies ...")

    async def login_by_mobile(self):
        """Login xiaohongshu by mobile via Energy browser"""
        utils.logger.info("[XiaoHongShuLogin.login_by_mobile] Begin login xiaohongshu by mobile ...")

        await asyncio.sleep(1)
        try:
            # Click login button
            await self.energy_adapter.click_login_button()
            await asyncio.sleep(1)
            # Switch to phone login
            await self.energy_adapter.switch_to_phone_login()
        except Exception as e:
            utils.logger.info(f"[XiaoHongShuLogin.login_by_mobile] have not found mobile button icon and keep going ...: {e}")

        await asyncio.sleep(1)

        # Get not logged session
        current_cookies = self.energy_adapter.get_cookies()
        no_logged_in_session = current_cookies.get("web_session", "")

        # Fill phone number if provided
        if self.login_phone:
            await self.energy_adapter.fill_phone_number(self.login_phone)
            await asyncio.sleep(0.5)

            # Send verification code
            await self.energy_adapter.send_verification_code()

            cache_client = CacheFactory.create_cache(config.CACHE_TYPE_MEMORY)
            max_get_sms_code_time = 60 * 2  # Maximum time to get verification code is 2 minutes

            while max_get_sms_code_time > 0:
                utils.logger.info(f"[XiaoHongShuLogin.login_by_mobile] get sms code from cache remaining time {max_get_sms_code_time}s ...")
                await asyncio.sleep(1)
                sms_code_key = f"xhs_{self.login_phone}"
                sms_code_value = cache_client.get(sms_code_key)
                if not sms_code_value:
                    max_get_sms_code_time -= 1
                    continue

                # Fill verification code
                await self.energy_adapter.fill_verification_code(sms_code_value.decode() if isinstance(sms_code_value, bytes) else sms_code_value)
                await asyncio.sleep(0.5)

                # Agree to privacy policy
                await self.energy_adapter.agree_privacy_policy()
                await asyncio.sleep(0.5)

                # Submit login
                await self.energy_adapter.submit_login()
                break

        # Poll for login status
        try:
            await self.check_login_state(no_logged_in_session)
        except RetryError:
            utils.logger.info("[XiaoHongShuLogin.login_by_mobile] Login xiaohongshu failed by mobile login method ...")
            sys.exit()

        wait_redirect_seconds = 5
        utils.logger.info(f"[XiaoHongShuLogin.login_by_mobile] Login successful then wait for {wait_redirect_seconds} seconds redirect ...")
        await asyncio.sleep(wait_redirect_seconds)

    async def login_by_qrcode(self):
        """Login xiaohongshu by QR code via Energy browser"""
        utils.logger.info("[XiaoHongShuLogin.login_by_qrcode] Begin login xiaohongshu by qrcode ...")

        # Get QR code image
        qrcode_img = await self._get_qrcode_image()

        if not qrcode_img:
            utils.logger.info("[XiaoHongShuLogin.login_by_qrcode] login failed, have not found qrcode please check ....")
            sys.exit()

        # Get not logged session
        current_cookies = self.energy_adapter.get_cookies()
        no_logged_in_session = current_cookies.get("web_session", "")

        # Show login qrcode
        base64_qrcode_img = base64.b64encode(qrcode_img).decode('utf-8')
        partial_show_qrcode = functools.partial(utils.show_qrcode, base64_qrcode_img)
        asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)

        utils.logger.info(f"[XiaoHongShuLogin.login_by_qrcode] waiting for scan code login, remaining time is 600s")

        try:
            await self.check_login_state(no_logged_in_session)
        except RetryError:
            utils.logger.info("[XiaoHongShuLogin.login_by_qrcode] Login xiaohongshu failed by qrcode login method ...")
            sys.exit()

        wait_redirect_seconds = 5
        utils.logger.info(f"[XiaoHongShuLogin.login_by_qrcode] Login successful then wait for {wait_redirect_seconds} seconds redirect ...")
        await asyncio.sleep(wait_redirect_seconds)

    async def _get_qrcode_image(self) -> Optional[bytes]:
        """Get QR code image from Energy browser"""
        try:
            qrcode_img = await self.energy_adapter.get_qrcode_image()
            if qrcode_img:
                return qrcode_img

            # Try clicking login button to show QR code
            await self.energy_adapter.click_login_button()
            await asyncio.sleep(1)
            return await self.energy_adapter.get_qrcode_image()
        except Exception as e:
            utils.logger.error(f"[XiaoHongShuLogin._get_qrcode_image] Error getting QR code: {e}")
            return None

    async def login_by_cookies(self):
        """Login xiaohongshu website by cookies"""
        utils.logger.info("[XiaoHongShuLogin.login_by_cookies] Begin login xiaohongshu by cookie ...")

        if not self.cookie_str:
            utils.logger.warning("[XiaoHongShuLogin.login_by_cookies] No cookie string provided")
            return

        # Parse cookie string to dict
        cookie_dict = utils.convert_str_cookie_to_dict(self.cookie_str)

        # Set cookies via Energy adapter
        if self.energy_adapter:
            await self.energy_adapter.login_with_cookies(cookie_dict)
            utils.logger.info("[XiaoHongShuLogin.login_by_cookies] Cookies set successfully")
        else:
            utils.logger.error("[XiaoHongShuLogin.login_by_cookies] Energy adapter not available")
