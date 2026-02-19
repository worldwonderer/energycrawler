# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/media_platform/xhs/__init__.py
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
XiaoHongShu (XHS) Platform Package

This package provides crawlers for the Xiaohongshu (Little Red Book) platform.
It uses the Energy browser service for browser automation and signature generation.

No Playwright dependency is required.
"""

# Import the Energy-based crawler
try:
    from .core import XiaoHongShuCrawler
except ImportError:
    from media_platform.xhs.core import XiaoHongShuCrawler

# Re-export field enums for convenience
try:
    from .field import *
except ImportError:
    from media_platform.xhs.field import *

__all__ = ['XiaoHongShuCrawler']
