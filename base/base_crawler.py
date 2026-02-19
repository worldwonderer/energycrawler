# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/base/base_crawler.py
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
Base Crawler Classes

This module defines abstract base classes for crawlers.
No external browser-driver dependency is required - the platform-specific crawlers
should use Energy browser service for browser automation.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any


class AbstractCrawler(ABC):
    """Abstract base class for all crawlers"""

    @abstractmethod
    async def start(self):
        """
        Start the crawler
        """
        pass

    @abstractmethod
    async def search(self):
        """
        Search for content
        """
        pass

    async def launch_browser(self, chromium: Any = None, browser_proxy: Optional[Dict] = None, user_agent: Optional[str] = None, headless: bool = True) -> Any:
        """
        Launch browser (deprecated - use Energy browser service instead)

        This method is kept for backward compatibility but should not be used.
        Platform-specific crawlers should use the Energy browser service.

        :param chromium: chromium browser (deprecated)
        :param browser_proxy: browser proxy (deprecated)
        :param user_agent: user agent
        :param headless: headless mode
        :return: browser context (deprecated)
        """
        raise NotImplementedError("Legacy browser mode is not supported. Use Energy browser service instead.")

    async def close(self):
        """
        Clean up resources (optional implementation)
        """
        pass


class AbstractStore(ABC):
    """Abstract base class for data storage"""

    @abstractmethod
    async def store_content(self, content_item: Dict):
        """Store content item"""
        pass

    @abstractmethod
    async def store_comment(self, comment_item: Dict):
        """Store comment item"""
        pass

    @abstractmethod
    async def store_creator(self, creator: Dict):
        """Store creator information"""
        pass


class AbstractStoreImage(ABC):
    """Abstract base class for image storage"""

    async def store_image(self, image_content_item: Dict):
        """Store image content (optional implementation)"""
        pass


class AbstractStoreVideo(ABC):
    """Abstract base class for video storage"""

    async def store_video(self, video_content_item: Dict):
        """Store video content (optional implementation)"""
        pass


class AbstractApiClient(ABC):
    """Abstract base class for API clients"""

    @abstractmethod
    async def request(self, method, url, **kwargs):
        """Make an HTTP request"""
        pass

    async def update_cookies(self, cookie_source: Any = None):
        """
        Update cookies from the source

        Args:
            cookie_source: Source of cookies (can be a dict, Energy adapter, or any other source)

        This method is optional - subclasses can override it for their specific needs.
        """
        pass

    async def update_cookies_from_dict(self, cookie_dict: Dict[str, str]):
        """
        Update cookies from a dictionary

        Args:
            cookie_dict: Dictionary of cookies
        """
        pass

    async def update_cookies_from_energy(self):
        """
        Update cookies from Energy browser adapter

        Subclasses should override this if they use Energy browser.
        """
        pass
