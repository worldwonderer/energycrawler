# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/database/models.py
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

from sqlalchemy import BigInteger, Boolean, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class XhsCreator(Base):
    __tablename__ = "xhs_creator"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), index=True)
    nickname = Column(Text)
    avatar = Column(Text)
    ip_location = Column(Text)
    add_ts = Column(BigInteger)
    last_modify_ts = Column(BigInteger)
    desc = Column(Text)
    gender = Column(Text)
    follows = Column(Text)
    fans = Column(Text)
    interaction = Column(Text)
    tag_list = Column(Text)


class XhsNote(Base):
    __tablename__ = "xhs_note"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(255))
    nickname = Column(Text)
    avatar = Column(Text)
    ip_location = Column(Text)
    add_ts = Column(BigInteger)
    last_modify_ts = Column(BigInteger)
    note_id = Column(String(255), index=True)
    type = Column(Text)
    title = Column(Text)
    desc = Column(Text)
    video_url = Column(Text)
    time = Column(BigInteger, index=True)
    last_update_time = Column(BigInteger)
    liked_count = Column(Text)
    collected_count = Column(Text)
    comment_count = Column(Text)
    share_count = Column(Text)
    image_list = Column(Text)
    tag_list = Column(Text)
    note_url = Column(Text)
    source_keyword = Column(Text, default="")
    xsec_token = Column(Text)


class XhsNoteComment(Base):
    __tablename__ = "xhs_note_comment"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(255))
    nickname = Column(Text)
    avatar = Column(Text)
    ip_location = Column(Text)
    add_ts = Column(BigInteger)
    last_modify_ts = Column(BigInteger)
    comment_id = Column(String(255), index=True)
    create_time = Column(BigInteger, index=True)
    note_id = Column(String(255), index=True)
    content = Column(Text)
    sub_comment_count = Column(Integer)
    pictures = Column(Text)
    parent_comment_id = Column(String(255))
    like_count = Column(Text)


class TwitterTweet(Base):
    __tablename__ = "twitter_tweet"

    id = Column(Integer, primary_key=True)
    add_ts = Column(BigInteger)
    last_modify_ts = Column(BigInteger)
    tweet_id = Column(String(255), nullable=False, index=True, unique=True)
    tweet_id_str = Column(String(255), index=True)
    text = Column(Text)
    created_at = Column(Text)
    user_id = Column(String(255), index=True)
    screen_name = Column(String(255), index=True)
    name = Column(Text)
    reply_count = Column(Integer, default=0)
    retweet_count = Column(Integer, default=0)
    favorite_count = Column(Integer, default=0)
    bookmark_count = Column(Integer, default=0)
    quote_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)
    lang = Column(String(32))
    source = Column(Text)
    in_reply_to_status_id = Column(String(255), index=True)
    in_reply_to_user_id = Column(String(255), index=True)
    in_reply_to_screen_name = Column(String(255))
    is_quote_status = Column(Boolean, default=False)
    quoted_status_id = Column(String(255), index=True)
    retweeted_status_id = Column(String(255), index=True)
    possibly_sensitive = Column(Boolean, default=False)
    tweet_url = Column(Text)
    hashtags = Column(Text)
    media_urls = Column(Text)
    video_urls = Column(Text)
    source_keyword = Column(Text, default="")


class TwitterTweetComment(Base):
    __tablename__ = "twitter_tweet_comment"

    id = Column(Integer, primary_key=True)
    add_ts = Column(BigInteger)
    last_modify_ts = Column(BigInteger)
    comment_id = Column(String(255), nullable=False, index=True, unique=True)
    tweet_id = Column(String(255), index=True)
    text = Column(Text)
    created_at = Column(Text)
    user_id = Column(String(255), index=True)
    screen_name = Column(String(255), index=True)
    name = Column(Text)
    reply_count = Column(Integer, default=0)
    favorite_count = Column(Integer, default=0)
    parent_comment_id = Column(String(255), index=True)


class TwitterCreator(Base):
    __tablename__ = "twitter_creator"

    id = Column(Integer, primary_key=True)
    add_ts = Column(BigInteger)
    last_modify_ts = Column(BigInteger)
    user_id = Column(String(255), nullable=False, unique=True, index=True)
    screen_name = Column(String(255), index=True)
    name = Column(Text)
    description = Column(Text)
    profile_image_url = Column(Text)
    profile_banner_url = Column(Text)
    followers_count = Column(Integer, default=0)
    friends_count = Column(Integer, default=0)
    statuses_count = Column(Integer, default=0)
    media_count = Column(Integer, default=0)
    created_at = Column(Text)
    location = Column(Text)
    url = Column(Text)
    verified = Column(Boolean, default=False)
    verified_type = Column(Text)
    is_blue_verified = Column(Boolean, default=False)
    protected = Column(Boolean, default=False)
