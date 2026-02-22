# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/tools/crawler_util.py
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

from typing import Dict
from urllib.parse import parse_qsl, urlparse


def convert_str_cookie_to_dict(cookie_str: str) -> Dict[str, str]:
    cookie_dict: Dict[str, str] = {}
    if not cookie_str:
        return cookie_dict
    for cookie in cookie_str.split(";"):
        cookie = cookie.strip()
        if not cookie:
            continue
        if "=" not in cookie:
            continue
        cookie_name, cookie_value = cookie.split("=", 1)
        cookie_name = cookie_name.strip()
        cookie_value = cookie_value.strip()
        if not cookie_name:
            continue
        if isinstance(cookie_value, list):
            cookie_value = "".join(cookie_value)
        cookie_dict[cookie_name] = cookie_value
    return cookie_dict


def extract_url_params_to_dict(url: str) -> Dict[str, str]:
    """Extract URL parameters to dict"""
    if not url:
        return {}
    parsed_url = urlparse(url)
    return dict(parse_qsl(parsed_url.query))
