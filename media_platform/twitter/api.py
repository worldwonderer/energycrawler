# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/media_platform/twitter/api.py
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


from __future__ import annotations

import re
from typing import Dict, Any, List

import requests


# GraphQL API base URL
GQL_URL = "https://x.com/i/api/graphql"

# Public bearer token (used for unauthenticated requests)
PUBLIC_BEARER_TOKEN = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# SearchTimeline query IDs can rotate frequently.
# Keep a small fallback list and let runtime refresh from X web bundle.
SEARCH_TIMELINE_QUERY_IDS: List[str] = [
    "cGK-Qeg1XJc2sZ6kgQw_Iw",
    "AIdc203rPpK_k_2KWSdm7g",
]


def build_operation_path(query_id: str, operation_name: str) -> str:
    return f"{query_id}/{operation_name}"


def _dedupe_keep_order(items: List[str]) -> List[str]:
    deduped: List[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def get_search_timeline_operation_paths() -> List[str]:
    return [build_operation_path(query_id, "SearchTimeline") for query_id in SEARCH_TIMELINE_QUERY_IDS]


def set_primary_search_timeline_query_id(query_id: str) -> None:
    if not query_id:
        return
    global SEARCH_TIMELINE_QUERY_IDS
    SEARCH_TIMELINE_QUERY_IDS = _dedupe_keep_order([query_id, *SEARCH_TIMELINE_QUERY_IDS])
    OPERATIONS["SearchTimeline"] = build_operation_path(SEARCH_TIMELINE_QUERY_IDS[0], "SearchTimeline")


def refresh_search_timeline_query_ids(timeout_sec: int = 20, max_assets: int = 8) -> List[str]:
    """
    Pull latest SearchTimeline query id candidates from X web bundle.
    """
    global SEARCH_TIMELINE_QUERY_IDS
    try:
        home_resp = requests.get("https://x.com", timeout=timeout_sec)
        home_resp.raise_for_status()
    except Exception:
        return SEARCH_TIMELINE_QUERY_IDS[:]

    asset_urls = re.findall(
        r'src="(https://abs\.twimg\.com/responsive-web/client-web/[^"]+\.js)"',
        home_resp.text,
    )
    found_ids: List[str] = []
    patterns = [
        re.compile(r'queryId:"([A-Za-z0-9_-]{10,})",operationName:"SearchTimeline"'),
        re.compile(r'"queryId":"([A-Za-z0-9_-]{10,})","operationName":"SearchTimeline"'),
        re.compile(r'operationName:"SearchTimeline",queryId:"([A-Za-z0-9_-]{10,})"'),
    ]

    for asset_url in asset_urls[:max_assets]:
        try:
            content_resp = requests.get(asset_url, timeout=timeout_sec)
            content_resp.raise_for_status()
            content = content_resp.text
        except Exception:
            continue

        for pattern in patterns:
            for match in pattern.findall(content):
                found_ids.append(match)

    if not found_ids:
        return SEARCH_TIMELINE_QUERY_IDS[:]

    deduped_found = _dedupe_keep_order(found_ids)
    SEARCH_TIMELINE_QUERY_IDS = _dedupe_keep_order(deduped_found + SEARCH_TIMELINE_QUERY_IDS)
    OPERATIONS["SearchTimeline"] = build_operation_path(SEARCH_TIMELINE_QUERY_IDS[0], "SearchTimeline")
    return SEARCH_TIMELINE_QUERY_IDS[:]


# GraphQL operation IDs
OPERATIONS: Dict[str, str] = {
    "SearchTimeline": build_operation_path(SEARCH_TIMELINE_QUERY_IDS[0], "SearchTimeline"),
    "UserByScreenName": "1VOOyvKkiI3FMmkeDNxM9A/UserByScreenName",
    "UserByRestId": "WJ7rCtezBVT6nk6VM5R8Bw/UserByRestId",
    "TweetDetail": "_8aYOgEDz35BrBcBal1-_w/TweetDetail",
    "UserTweets": "HeWHY26ItCfUmm1e6ITjeA/UserTweets",
    "UserTweetsAndReplies": "OAx9yEcW3JA9bPo63pcYlA/UserTweetsAndReplies",
    "UserMedia": "vFPc2LVIu7so2uA_gHQAdg/UserMedia",
    "Followers": "Elc_-qTARceHpztqhI9PQA/Followers",
    "Following": "C1qZ6bs-L3oc_TKSZyxkXQ/Following",
    "Retweeters": "i-CI8t2pJD15euZJErEDrg/Retweeters",
    "Bookmarks": "-LGfdImKeQz0xSjjUwzlA/Bookmarks",
}

# GraphQL features (required for API requests)
GQL_FEATURES: Dict[str, Any] = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


def get_gql_url(operation: str) -> str:
    """
    Build GraphQL API URL for a given operation.

    Args:
        operation: Operation name (e.g., "SearchTimeline")

    Returns:
        Full GraphQL URL for the operation
    """
    if operation not in OPERATIONS:
        raise ValueError(f"Unknown operation: {operation}")

    return f"{GQL_URL}/{OPERATIONS[operation]}"


def get_gql_url_by_path(operation_path: str) -> str:
    if not operation_path or "/" not in operation_path:
        raise ValueError(f"Invalid operation path: {operation_path}")
    return f"{GQL_URL}/{operation_path}"


def get_search_url(query: str, search_type: str = "Latest") -> str:
    """
    Build search timeline URL with query parameters.

    Args:
        query: Search query string
        search_type: Type of search (Latest, Top, People)

    Returns:
        Full search URL
    """
    base_url = get_gql_url("SearchTimeline")
    return f"{base_url}?variables=%7B%22query%22%3A%22{query}%22%2C%22search_type%22%3A%22{search_type}%22%7D"
