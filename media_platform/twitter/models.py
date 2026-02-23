# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/media_platform/twitter/models.py
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


# -*- coding: utf-8 -*-

"""
Twitter/X.com data models for parsing GraphQL API responses.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class TwitterMedia:
    """Twitter media attachment data model."""
    media_key: str = None             # Media key
    media_id: str = None              # Media ID
    media_type: str = None            # photo, video, animated_gif
    media_url: str = None             # Media URL (image thumbnail)
    video_url: str = None             # Video URL (for videos)
    display_url: str = None           # Display URL
    expanded_url: str = None          # Expanded URL
    width: int = 0                    # Original width
    height: int = 0                   # Original height
    duration_ms: int = 0              # Duration for video
    view_count: int = 0               # View count for video


@dataclass
class TwitterUser:
    """Twitter user data model."""
    id: str = None                    # User ID (rest_id)
    screen_name: str = None           # @username
    name: str = None                  # Display name
    description: str = None           # Bio
    profile_image_url: str = None     # Profile image
    profile_banner_url: str = None    # Banner image
    followers_count: int = 0          # Follower count
    friends_count: int = 0            # Following count
    statuses_count: int = 0           # Tweet count
    media_count: int = 0              # Media count
    created_at: str = None            # Account creation date
    location: str = None              # Location
    url: str = None                   # Website URL
    verified: bool = False            # Is verified
    verified_type: str = None         # Blue, Gold, etc.
    is_blue_verified: bool = False    # Twitter Blue subscriber
    protected: bool = False           # Private account


@dataclass
class TwitterTweet:
    """Twitter tweet data model."""
    id: str = None                    # Tweet ID (rest_id)
    id_str: str = None                # Tweet ID as string
    text: str = None                  # Tweet text (full_text)
    created_at: str = None            # Creation timestamp
    user_id: str = None               # Author user ID
    screen_name: str = None           # Author username
    name: str = None                  # Author display name
    reply_count: int = 0              # Reply count
    retweet_count: int = 0            # Retweet count
    favorite_count: int = 0           # Like count
    bookmark_count: int = 0           # Bookmark count
    quote_count: int = 0              # Quote count
    view_count: int = 0               # View count (impressions)
    lang: str = None                  # Language code
    source: str = None                # Client used (e.g., "Twitter for iPhone")
    in_reply_to_status_id: str = None # Reply to tweet ID
    in_reply_to_user_id: str = None   # Reply to user ID
    in_reply_to_screen_name: str = None  # Reply to username
    is_quote_status: bool = False     # Is a quote tweet
    quoted_status_id: str = None      # Quoted tweet ID
    retweeted_status_id: str = None   # Retweeted tweet ID
    possibly_sensitive: bool = False  # Sensitive content flag
    tweet_url: str = None             # Full tweet URL
    hashtags: List[str] = field(default_factory=list)        # Hashtags list
    urls: List[dict] = field(default_factory=list)           # URLs in tweet
    user_mentions: List[dict] = field(default_factory=list)  # Mentioned users
    media: List[TwitterMedia] = field(default_factory=list)  # Media attachments


def _extract_nested_value(data: dict, *keys) -> Any:
    """Extract nested value from dictionary using a sequence of keys."""
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _find_nested_key(dataset: Any, nested_key: str) -> Any:
    """Recursively find a key in nested dictionary/list structure."""
    if isinstance(dataset, dict):
        if nested_key in dataset:
            return dataset[nested_key]
        for value in dataset.values():
            result = _find_nested_key(value, nested_key)
            if result is not None:
                return result
    elif isinstance(dataset, list):
        for item in dataset:
            result = _find_nested_key(item, nested_key)
            if result is not None:
                return result
    return None


def _parse_media_from_response(media_data: dict) -> TwitterMedia:
    """Parse media data from GraphQL response."""
    media = TwitterMedia()

    media.media_key = media_data.get("media_key")
    media.media_id = media_data.get("id_str") or media_data.get("media_id")

    media_type = media_data.get("type") or media_data.get("media_type")
    media.media_type = media_type

    media.media_url = media_data.get("media_url_https") or media_data.get("media_url")
    media.display_url = media_data.get("display_url")
    media.expanded_url = media_data.get("expanded_url")

    # Extract original dimensions
    original_info = media_data.get("original_info") or {}
    media.width = original_info.get("width", 0)
    media.height = original_info.get("height", 0)

    # Video/GIF-specific fields
    if media_type in {"video", "animated_gif"}:
        video_info = media_data.get("video_info", {})
        media.duration_ms = video_info.get("duration_millis", 0)

        # Get highest quality video URL
        variants = video_info.get("variants", [])
        if variants:
            # Sort by bitrate to get highest quality
            video_variants = [v for v in variants if v.get("type") == "video/mp4"]
            if video_variants:
                video_variants.sort(key=lambda x: x.get("bitrate", 0), reverse=True)
                media.video_url = video_variants[0].get("url")

        # View count for videos
        media.view_count = media_data.get("ext_media_availability", {}).get("views", 0) if isinstance(media_data.get("ext_media_availability"), dict) else 0
        # Alternative location for view count
        if media.view_count == 0:
            media.view_count = media_data.get("mediaStats", {}).get("viewCount", 0)

    return media


def parse_user_from_response(data: dict) -> TwitterUser:
    """Parse user from GraphQL response.

    Args:
        data: Raw user data from GraphQL response, typically from user_results.result

    Returns:
        TwitterUser dataclass instance
    """
    user = TwitterUser()

    # Navigate to user result if needed
    user_result = _extract_nested_value(data, "user_results", "result") or data

    # Get legacy data (contains most user info)
    legacy = user_result.get("legacy", {})

    # Basic identification
    user.id = user_result.get("rest_id") or legacy.get("id_str")
    user.screen_name = legacy.get("screen_name")
    user.name = legacy.get("name")
    user.description = legacy.get("description")

    # Profile images
    user.profile_image_url = legacy.get("profile_image_url_https") or legacy.get("profile_image_url")
    user.profile_banner_url = user_result.get("profile_banner_url") or legacy.get("profile_banner_url")

    # Counts
    user.followers_count = legacy.get("followers_count", 0) or 0
    user.friends_count = legacy.get("friends_count", 0) or 0
    user.statuses_count = legacy.get("statuses_count", 0) or 0
    user.media_count = legacy.get("media_count", 0) or 0

    # Other profile info
    user.created_at = legacy.get("created_at")
    user.location = legacy.get("location")
    user.url = legacy.get("url")

    # Verification status
    user.verified = legacy.get("verified", False) or False
    user.verified_type = legacy.get("verified_type")
    user.is_blue_verified = user_result.get("is_blue_verified", False) or False

    # Account status
    user.protected = legacy.get("protected", False) or False

    return user


def parse_tweet_from_response(data: dict) -> TwitterTweet:
    """Parse tweet from GraphQL response.

    Args:
        data: Raw tweet data from GraphQL response, typically from tweet_results.result
              or from timeline entries

    Returns:
        TwitterTweet dataclass instance
    """
    tweet = TwitterTweet()

    # Navigate to tweet result if needed
    is_single_tweet = "tweetResult" in data or "tweet_results" in data
    if is_single_tweet:
        tweet_result = _extract_nested_value(data, "tweetResult", "result") or \
                       _extract_nested_value(data, "tweet_results", "result")
    else:
        tweet_result = data

    if not tweet_result:
        return tweet

    # Get legacy data (contains most tweet info)
    legacy = tweet_result.get("legacy", {})

    # Basic identification
    tweet.id = tweet_result.get("rest_id")
    tweet.id_str = str(tweet.id) if tweet.id else legacy.get("id_str")
    tweet.text = legacy.get("full_text") or legacy.get("text")
    tweet.created_at = legacy.get("created_at")

    # Author info from core
    core = tweet_result.get("core", {})
    user_results = core.get("user_results", {}).get("result", {})
    user_legacy = user_results.get("legacy", {})

    tweet.user_id = user_results.get("rest_id") or legacy.get("user_id_str")
    tweet.screen_name = user_legacy.get("screen_name")
    tweet.name = user_legacy.get("name")

    # Engagement counts
    tweet.reply_count = legacy.get("reply_count", 0) or 0
    tweet.retweet_count = legacy.get("retweet_count", 0) or 0
    tweet.favorite_count = legacy.get("favorite_count", 0) or 0
    tweet.bookmark_count = legacy.get("bookmark_count", 0) or 0
    tweet.quote_count = legacy.get("quote_count", 0) or 0

    # View count (impressions)
    views = tweet_result.get("views", {})
    tweet.view_count = int(views.get("count", 0) or 0)

    # Other metadata
    tweet.lang = legacy.get("lang")
    tweet.source = tweet_result.get("source")
    tweet.possibly_sensitive = legacy.get("possibly_sensitive", False) or False

    # Reply info
    tweet.in_reply_to_status_id = legacy.get("in_reply_to_status_id_str")
    tweet.in_reply_to_user_id = legacy.get("in_reply_to_user_id_str")
    tweet.in_reply_to_screen_name = legacy.get("in_reply_to_screen_name")

    # Quote/retweet info
    tweet.is_quote_status = legacy.get("is_quote_status", False) or False
    tweet.quoted_status_id = legacy.get("quoted_status_id_str")
    tweet.retweeted_status_id = legacy.get("retweeted_status_id_str")

    # Build tweet URL
    if tweet.screen_name and tweet.id:
        tweet.tweet_url = f"https://x.com/{tweet.screen_name}/status/{tweet.id}"

    # Extract entities
    entities = legacy.get("entities", {})

    # Hashtags
    hashtag_data = entities.get("hashtags", [])
    tweet.hashtags = [h.get("text") for h in hashtag_data if h.get("text")]

    # URLs
    tweet.urls = entities.get("urls", [])

    # User mentions
    tweet.user_mentions = entities.get("user_mentions", [])

    # Extended entities for media
    extended_entities = legacy.get("extended_entities", {})
    media_data = extended_entities.get("media", [])

    if media_data:
        tweet.media = [_parse_media_from_response(m) for m in media_data]

    return tweet


def parse_tweets_from_timeline(data: dict) -> List[TwitterTweet]:
    """Parse multiple tweets from timeline response.

    Args:
        data: Raw timeline data from GraphQL response, typically containing
              timeline.instructions with entries

    Returns:
        List of TwitterTweet dataclass instances
    """
    tweets = []

    # Find instructions in response
    instructions = _find_nested_key(data, "instructions") or []

    if not instructions:
        # Try alternative structure
        instructions = data.get("timeline", {}).get("instructions", [])

    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue

        # Handle different instruction types
        entries = instruction.get("entries", [])

        # Some responses use addEntries type
        if instruction.get("type") == "TimelineAddEntries" and not entries:
            entries = instruction.get("entry", [])

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            # Get content
            content = entry.get("content", {})
            entry_type = content.get("entryType")

            # Handle tweet entries
            if entry_type == "TimelineTimelineItem":
                item_content = content.get("itemContent", {})
                tweet_results = item_content.get("tweet_results", {})

                if tweet_results:
                    parsed = parse_tweet_from_response({"tweet_results": tweet_results})
                    if parsed.id:
                        tweets.append(parsed)

            # Handle timeline modules (can contain multiple tweets)
            elif entry_type == "TimelineTimelineModule":
                items = content.get("items", [])
                for item in items:
                    item_content = item.get("item", {}).get("itemContent", {})
                    tweet_results = item_content.get("tweet_results", {})

                    if tweet_results:
                        parsed = parse_tweet_from_response({"tweet_results": tweet_results})
                        if parsed.id:
                            tweets.append(parsed)

    return tweets
