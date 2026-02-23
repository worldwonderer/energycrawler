# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/store/twitter/__init__.py
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
# @Time    : 2025/2/17
# @Desc    : Twitter/X.com storage module

import json
from typing import Dict

import config
from var import source_keyword_var

from .twitter_store_impl import (
    TwitterCsvStoreImplement,
    TwitterJsonStoreImplement,
    TwitterDbStoreImplement,
    TwitterSqliteStoreImplement,
    TwitterMongoStoreImplement,
    TwitterExcelStoreImplement,
)
from base.base_crawler import AbstractStore


class TwitterStoreFactory:
    """Factory for creating Twitter store instances"""

    STORES = {
        "csv": TwitterCsvStoreImplement,
        "db": TwitterDbStoreImplement,
        "postgres": TwitterDbStoreImplement,
        "json": TwitterJsonStoreImplement,
        "sqlite": TwitterSqliteStoreImplement,
        "mongodb": TwitterMongoStoreImplement,
        "excel": TwitterExcelStoreImplement,
    }

    @staticmethod
    def create_store() -> AbstractStore:
        """Create a store instance based on config.SAVE_DATA_OPTION"""
        store_class = TwitterStoreFactory.STORES.get(config.SAVE_DATA_OPTION)
        if not store_class:
            raise ValueError(
                "[TwitterStoreFactory.create_store] Invalid save option. "
                "Supported: csv, db, json, sqlite, mongodb, excel, postgres"
            )
        return store_class()


async def update_twitter_tweet(tweet_item: Dict):
    """
    Update Twitter tweet data

    Args:
        tweet_item: Tweet data dictionary containing all tweet information

    Returns:
        None
    """
    media_list = tweet_item.get("media", [])
    media_urls = []
    video_urls = []

    for media in media_list:
        media_type = media.get("media_type", "")
        if media_type == "photo":
            media_urls.append(media.get("media_url", ""))
        elif media_type in ("video", "animated_gif"):
            video_url = media.get("video_url", "")
            if video_url:
                video_urls.append(video_url)

    local_db_item = {
        "tweet_id": tweet_item.get("id"),
        "tweet_id_str": tweet_item.get("id_str"),
        "text": tweet_item.get("text", ""),
        "created_at": tweet_item.get("created_at"),
        "user_id": tweet_item.get("user_id"),
        "screen_name": tweet_item.get("screen_name"),
        "name": tweet_item.get("name"),
        "reply_count": tweet_item.get("reply_count", 0),
        "retweet_count": tweet_item.get("retweet_count", 0),
        "favorite_count": tweet_item.get("favorite_count", 0),
        "bookmark_count": tweet_item.get("bookmark_count", 0),
        "quote_count": tweet_item.get("quote_count", 0),
        "view_count": tweet_item.get("view_count", 0),
        "lang": tweet_item.get("lang"),
        "source": tweet_item.get("source"),
        "in_reply_to_status_id": tweet_item.get("in_reply_to_status_id"),
        "in_reply_to_user_id": tweet_item.get("in_reply_to_user_id"),
        "in_reply_to_screen_name": tweet_item.get("in_reply_to_screen_name"),
        "is_quote_status": tweet_item.get("is_quote_status", False),
        "quoted_status_id": tweet_item.get("quoted_status_id"),
        "retweeted_status_id": tweet_item.get("retweeted_status_id"),
        "possibly_sensitive": tweet_item.get("possibly_sensitive", False),
        "tweet_url": tweet_item.get("tweet_url"),
        "hashtags": ",".join(tweet_item.get("hashtags", [])),
        "urls": json.dumps(tweet_item.get("urls", []), ensure_ascii=False),
        "user_mentions": json.dumps(tweet_item.get("user_mentions", []), ensure_ascii=False),
        "media_detail": json.dumps(media_list, ensure_ascii=False),
        "media_urls": ",".join(media_urls),
        "video_urls": ",".join(video_urls),
        "source_keyword": source_keyword_var.get(),
        "last_modify_ts": utils.get_current_timestamp(),
    }

    utils.logger.info(f"[store.twitter.update_twitter_tweet] twitter tweet: {local_db_item}")
    await TwitterStoreFactory.create_store().store_content(local_db_item)


async def batch_update_twitter_tweet_comments(tweet_id: str, comments: list):
    """
    Batch update Twitter tweet comments

    Args:
        tweet_id: Tweet ID
        comments: List of comment dictionaries

    Returns:
        None
    """
    if not comments:
        return
    for comment_item in comments:
        await update_twitter_tweet_comment(tweet_id, comment_item)


async def update_twitter_tweet_comment(tweet_id: str, comment_item: Dict):
    """
    Update Twitter tweet comment

    Args:
        tweet_id: Tweet ID
        comment_item: Comment data dictionary

    Returns:
        None
    """
    user_info = comment_item.get("user", {})
    local_db_item = {
        "comment_id": comment_item.get("id"),
        "tweet_id": tweet_id,
        "text": comment_item.get("text", ""),
        "created_at": comment_item.get("created_at"),
        "user_id": user_info.get("id"),
        "screen_name": user_info.get("screen_name"),
        "name": user_info.get("name"),
        "reply_count": comment_item.get("reply_count", 0),
        "favorite_count": comment_item.get("favorite_count", 0),
        "parent_comment_id": comment_item.get("parent_comment_id"),
        "last_modify_ts": utils.get_current_timestamp(),
    }
    utils.logger.info(f"[store.twitter.update_twitter_tweet_comment] twitter comment: {local_db_item}")
    await TwitterStoreFactory.create_store().store_comment(local_db_item)


async def save_twitter_creator(user_id: str, creator: Dict):
    """
    Save Twitter creator/user information

    Args:
        user_id: User ID
        creator: Creator data dictionary

    Returns:
        None
    """
    local_db_item = {
        "user_id": user_id,
        "screen_name": creator.get("screen_name"),
        "name": creator.get("name"),
        "description": creator.get("description"),
        "profile_image_url": creator.get("profile_image_url"),
        "profile_banner_url": creator.get("profile_banner_url"),
        "followers_count": creator.get("followers_count", 0),
        "friends_count": creator.get("friends_count", 0),
        "statuses_count": creator.get("statuses_count", 0),
        "media_count": creator.get("media_count", 0),
        "created_at": creator.get("created_at"),
        "location": creator.get("location"),
        "url": creator.get("url"),
        "verified": creator.get("verified", False),
        "verified_type": creator.get("verified_type"),
        "is_blue_verified": creator.get("is_blue_verified", False),
        "protected": creator.get("protected", False),
        "last_modify_ts": utils.get_current_timestamp(),
    }
    utils.logger.info(f"[store.twitter.save_twitter_creator] creator: {local_db_item}")
    await TwitterStoreFactory.create_store().store_creator(local_db_item)


# Import utils at the end to avoid circular import
from tools import utils
