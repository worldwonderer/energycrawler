# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/store/twitter/twitter_store_impl.py
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

# @Time    : 2025/2/17
# @Desc    : Twitter/X.com storage implementation classes

import json
from typing import Dict, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from base.base_crawler import AbstractStore
from database.db_session import get_session
from database.mongodb_store_base import MongoDBStoreBase
from tools.async_file_writer import AsyncFileWriter
from tools.time_util import get_current_timestamp
from var import crawler_type_var
from tools import utils


class TwitterCsvStoreImplement(AbstractStore):
    """Twitter CSV storage implementation"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="twitter", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        """
        Store tweet content to CSV file

        Args:
            content_item: Tweet content data
        """
        await self.writer.write_to_csv(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        Store comment data to CSV file

        Args:
            comment_item: Comment data
        """
        await self.writer.write_to_csv(item_type="comments", item=comment_item)

    async def store_creator(self, creator_item: Dict):
        """
        Store creator data to CSV file

        Args:
            creator_item: Creator data
        """
        await self.writer.write_to_csv(item_type="creators", item=creator_item)

    def flush(self):
        """Flush data to file"""
        pass


class TwitterJsonStoreImplement(AbstractStore):
    """Twitter JSON storage implementation"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="twitter", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        """
        Store tweet content to JSON file

        Args:
            content_item: Tweet content data
        """
        await self.writer.write_single_item_to_json(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        Store comment data to JSON file

        Args:
            comment_item: Comment data
        """
        await self.writer.write_single_item_to_json(item_type="comments", item=comment_item)

    async def store_creator(self, creator_item: Dict):
        """
        Store creator data to JSON file

        Args:
            creator_item: Creator data
        """
        await self.writer.write_single_item_to_json(item_type="creators", item=creator_item)

    def flush(self):
        """Flush data to JSON file"""
        pass


class TwitterDbStoreImplement(AbstractStore):
    """Twitter database storage implementation"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def store_content(self, content_item: Dict):
        """
        Store tweet content to database

        Args:
            content_item: Tweet content data
        """
        from database.models import TwitterTweet

        tweet_id = content_item.get("tweet_id")
        if not tweet_id:
            return

        async with get_session() as session:
            if await self._content_exists(session, TwitterTweet, "tweet_id", tweet_id):
                await self._update_content(session, content_item, TwitterTweet)
            else:
                await self._add_content(session, content_item, TwitterTweet)

    async def _add_content(self, session: AsyncSession, content_item: Dict, model_class):
        """Add new content to database"""
        from database.models import TwitterTweet

        add_ts = int(get_current_timestamp())
        last_modify_ts = int(get_current_timestamp())

        tweet = TwitterTweet(
            add_ts=add_ts,
            last_modify_ts=last_modify_ts,
            tweet_id=content_item.get("tweet_id"),
            tweet_id_str=content_item.get("tweet_id_str"),
            text=content_item.get("text"),
            created_at=content_item.get("created_at"),
            user_id=content_item.get("user_id"),
            screen_name=content_item.get("screen_name"),
            name=content_item.get("name"),
            reply_count=content_item.get("reply_count", 0),
            retweet_count=content_item.get("retweet_count", 0),
            favorite_count=content_item.get("favorite_count", 0),
            bookmark_count=content_item.get("bookmark_count", 0),
            quote_count=content_item.get("quote_count", 0),
            view_count=content_item.get("view_count", 0),
            lang=content_item.get("lang"),
            source=content_item.get("source"),
            in_reply_to_status_id=content_item.get("in_reply_to_status_id"),
            in_reply_to_user_id=content_item.get("in_reply_to_user_id"),
            in_reply_to_screen_name=content_item.get("in_reply_to_screen_name"),
            is_quote_status=content_item.get("is_quote_status", False),
            quoted_status_id=content_item.get("quoted_status_id"),
            retweeted_status_id=content_item.get("retweeted_status_id"),
            possibly_sensitive=content_item.get("possibly_sensitive", False),
            tweet_url=content_item.get("tweet_url"),
            hashtags=content_item.get("hashtags"),
            media_urls=content_item.get("media_urls"),
            video_urls=content_item.get("video_urls"),
            source_keyword=content_item.get("source_keyword", ""),
        )
        session.add(tweet)

    async def _update_content(self, session: AsyncSession, content_item: Dict, model_class):
        """Update existing content in database"""
        from database.models import TwitterTweet

        tweet_id = content_item.get("tweet_id")
        last_modify_ts = int(get_current_timestamp())
        update_data = {
            "last_modify_ts": last_modify_ts,
            "reply_count": content_item.get("reply_count", 0),
            "retweet_count": content_item.get("retweet_count", 0),
            "favorite_count": content_item.get("favorite_count", 0),
            "bookmark_count": content_item.get("bookmark_count", 0),
            "quote_count": content_item.get("quote_count", 0),
            "view_count": content_item.get("view_count", 0),
        }
        stmt = update(TwitterTweet).where(TwitterTweet.tweet_id == tweet_id).values(**update_data)
        await session.execute(stmt)

    async def _content_exists(self, session: AsyncSession, model_class, field_name: str, value: str) -> bool:
        """Check if content exists in database"""
        stmt = select(model_class).where(getattr(model_class, field_name) == value)
        result = await session.execute(stmt)
        return result.first() is not None

    async def store_comment(self, comment_item: Dict):
        """
        Store comment to database

        Args:
            comment_item: Comment data
        """
        from database.models import TwitterTweetComment

        if not comment_item:
            return

        async with get_session() as session:
            comment_id = comment_item.get("comment_id")
            if not comment_id:
                return

            if await self._content_exists(session, TwitterTweetComment, "comment_id", comment_id):
                await self._update_comment(session, comment_item, TwitterTweetComment)
            else:
                await self._add_comment(session, comment_item, TwitterTweetComment)

    async def _add_comment(self, session: AsyncSession, comment_item: Dict, model_class):
        """Add new comment to database"""
        from database.models import TwitterTweetComment

        add_ts = int(get_current_timestamp())
        last_modify_ts = int(get_current_timestamp())

        comment = TwitterTweetComment(
            add_ts=add_ts,
            last_modify_ts=last_modify_ts,
            comment_id=comment_item.get("comment_id"),
            tweet_id=comment_item.get("tweet_id"),
            text=comment_item.get("text"),
            created_at=comment_item.get("created_at"),
            user_id=comment_item.get("user_id"),
            screen_name=comment_item.get("screen_name"),
            name=comment_item.get("name"),
            reply_count=comment_item.get("reply_count", 0),
            favorite_count=comment_item.get("favorite_count", 0),
            parent_comment_id=comment_item.get("parent_comment_id"),
        )
        session.add(comment)

    async def _update_comment(self, session: AsyncSession, comment_item: Dict, model_class):
        """Update existing comment in database"""
        from database.models import TwitterTweetComment

        comment_id = comment_item.get("comment_id")
        last_modify_ts = int(get_current_timestamp())
        update_data = {
            "last_modify_ts": last_modify_ts,
            "reply_count": comment_item.get("reply_count", 0),
            "favorite_count": comment_item.get("favorite_count", 0),
        }
        stmt = update(TwitterTweetComment).where(
            TwitterTweetComment.comment_id == comment_id
        ).values(**update_data)
        await session.execute(stmt)

    async def store_creator(self, creator_item: Dict):
        """
        Store creator to database

        Args:
            creator_item: Creator data
        """
        from database.models import TwitterCreator

        user_id = creator_item.get("user_id")
        if not user_id:
            return

        async with get_session() as session:
            if await self._content_exists(session, TwitterCreator, "user_id", user_id):
                await self._update_creator(session, creator_item, TwitterCreator)
            else:
                await self._add_creator(session, creator_item, TwitterCreator)

    async def _add_creator(self, session: AsyncSession, creator_item: Dict, model_class):
        """Add new creator to database"""
        from database.models import TwitterCreator

        add_ts = int(get_current_timestamp())
        last_modify_ts = int(get_current_timestamp())

        creator = TwitterCreator(
            add_ts=add_ts,
            last_modify_ts=last_modify_ts,
            user_id=creator_item.get("user_id"),
            screen_name=creator_item.get("screen_name"),
            name=creator_item.get("name"),
            description=creator_item.get("description"),
            profile_image_url=creator_item.get("profile_image_url"),
            profile_banner_url=creator_item.get("profile_banner_url"),
            followers_count=creator_item.get("followers_count", 0),
            friends_count=creator_item.get("friends_count", 0),
            statuses_count=creator_item.get("statuses_count", 0),
            media_count=creator_item.get("media_count", 0),
            created_at=creator_item.get("created_at"),
            location=creator_item.get("location"),
            url=creator_item.get("url"),
            verified=creator_item.get("verified", False),
            verified_type=creator_item.get("verified_type"),
            is_blue_verified=creator_item.get("is_blue_verified", False),
            protected=creator_item.get("protected", False),
        )
        session.add(creator)

    async def _update_creator(self, session: AsyncSession, creator_item: Dict, model_class):
        """Update existing creator in database"""
        from database.models import TwitterCreator

        user_id = creator_item.get("user_id")
        last_modify_ts = int(get_current_timestamp())
        update_data = {
            "last_modify_ts": last_modify_ts,
            "screen_name": creator_item.get("screen_name"),
            "name": creator_item.get("name"),
            "description": creator_item.get("description"),
            "profile_image_url": creator_item.get("profile_image_url"),
            "profile_banner_url": creator_item.get("profile_banner_url"),
            "followers_count": creator_item.get("followers_count", 0),
            "friends_count": creator_item.get("friends_count", 0),
            "statuses_count": creator_item.get("statuses_count", 0),
            "media_count": creator_item.get("media_count", 0),
            "location": creator_item.get("location"),
            "url": creator_item.get("url"),
            "verified": creator_item.get("verified", False),
            "verified_type": creator_item.get("verified_type"),
            "is_blue_verified": creator_item.get("is_blue_verified", False),
            "protected": creator_item.get("protected", False),
        }
        stmt = update(TwitterCreator).where(TwitterCreator.user_id == user_id).values(**update_data)
        await session.execute(stmt)

    async def get_all_content(self) -> List[Dict]:
        """Get all content from database"""
        from database.models import TwitterTweet

        async with get_session() as session:
            stmt = select(TwitterTweet)
            result = await session.execute(stmt)
            return [item.__dict__ for item in result.scalars().all()]

    async def get_all_comments(self) -> List[Dict]:
        """Get all comments from database"""
        from database.models import TwitterTweetComment

        async with get_session() as session:
            stmt = select(TwitterTweetComment)
            result = await session.execute(stmt)
            return [item.__dict__ for item in result.scalars().all()]


class TwitterSqliteStoreImplement(TwitterDbStoreImplement):
    """Twitter SQLite storage implementation (inherits from DB implementation)"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class TwitterMongoStoreImplement(AbstractStore):
    """Twitter MongoDB storage implementation"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mongo_store = MongoDBStoreBase(collection_prefix="twitter")

    async def store_content(self, content_item: Dict):
        """
        Store tweet content to MongoDB

        Args:
            content_item: Tweet content data
        """
        tweet_id = content_item.get("tweet_id")
        if not tweet_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="contents",
            query={"tweet_id": tweet_id},
            data=content_item
        )
        utils.logger.info(f"[TwitterMongoStoreImplement.store_content] Saved tweet {tweet_id} to MongoDB")

    async def store_comment(self, comment_item: Dict):
        """
        Store comment to MongoDB

        Args:
            comment_item: Comment data
        """
        comment_id = comment_item.get("comment_id")
        if not comment_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="comments",
            query={"comment_id": comment_id},
            data=comment_item
        )
        utils.logger.info(f"[TwitterMongoStoreImplement.store_comment] Saved comment {comment_id} to MongoDB")

    async def store_creator(self, creator_item: Dict):
        """
        Store creator information to MongoDB

        Args:
            creator_item: Creator data
        """
        user_id = creator_item.get("user_id")
        if not user_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="creators",
            query={"user_id": user_id},
            data=creator_item
        )
        utils.logger.info(f"[TwitterMongoStoreImplement.store_creator] Saved creator {user_id} to MongoDB")


class TwitterExcelStoreImplement:
    """Twitter Excel storage implementation - Global singleton"""

    def __new__(cls, *args, **kwargs):
        from store.excel_store_base import ExcelStoreBase
        return ExcelStoreBase.get_instance(
            platform="twitter",
            crawler_type=crawler_type_var.get()
        )
