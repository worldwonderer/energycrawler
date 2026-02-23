# -*- coding: utf-8 -*-
"""
Regression tests for Twitter/X field completeness fixes.
"""

from __future__ import annotations

import json

import pytest

import config
from media_platform.twitter.core import TwitterCrawler
from media_platform.twitter.models import parse_tweet_from_response
from media_platform.twitter.models import TwitterTweet, TwitterMedia
from store import twitter as twitter_store


def test_parse_tweet_from_response_extracts_animated_gif_video_url():
    data = {
        "rest_id": "1",
        "legacy": {
            "id_str": "1",
            "full_text": "gif tweet",
            "created_at": "Mon Feb 23 00:00:00 +0000 2026",
            "reply_count": 0,
            "retweet_count": 0,
            "favorite_count": 0,
            "bookmark_count": 0,
            "quote_count": 0,
            "entities": {"hashtags": [], "urls": [], "user_mentions": []},
            "extended_entities": {
                "media": [
                    {
                        "id_str": "m1",
                        "type": "animated_gif",
                        "media_url_https": "https://pbs.twimg.com/media/a.jpg",
                        "video_info": {
                            "duration_millis": 0,
                            "variants": [
                                {"type": "video/mp4", "bitrate": 0, "url": "https://video.twimg.com/a.mp4"}
                            ],
                        },
                    }
                ]
            },
        },
        "views": {"count": "1"},
        "core": {
            "user_results": {"result": {"rest_id": "u1", "legacy": {"screen_name": "alice", "name": "Alice"}}}
        },
    }

    tweet = parse_tweet_from_response(data)
    assert tweet.id == "1"
    assert len(tweet.media) == 1
    assert tweet.media[0].media_type == "animated_gif"
    assert tweet.media[0].video_url == "https://video.twimg.com/a.mp4"


@pytest.mark.asyncio
async def test_update_twitter_tweet_keeps_urls_mentions_and_media_detail(monkeypatch):
    captured = {}

    class _Store:
        async def store_content(self, item):
            captured.update(item)

    monkeypatch.setattr(twitter_store.TwitterStoreFactory, "create_store", staticmethod(lambda: _Store()))

    tweet_item = {
        "id": "11",
        "id_str": "11",
        "text": "hello",
        "created_at": "Mon Feb 23 00:00:00 +0000 2026",
        "user_id": "u1",
        "screen_name": "alice",
        "name": "Alice",
        "hashtags": ["ai"],
        "urls": [{"expanded_url": "https://example.com"}],
        "user_mentions": [{"screen_name": "bob"}],
        "media": [
            {
                "media_type": "photo",
                "media_url": "https://pbs.twimg.com/media/1.jpg",
                "display_url": "pic.twitter.com/1",
                "expanded_url": "https://x.com/pic/1",
                "width": 1080,
                "height": 720,
            },
            {
                "media_type": "animated_gif",
                "media_url": "https://pbs.twimg.com/media/2.jpg",
                "video_url": "https://video.twimg.com/2.mp4",
                "duration_ms": 1200,
            },
        ],
    }

    await twitter_store.update_twitter_tweet(tweet_item)

    assert captured["tweet_id"] == "11"
    assert captured["media_urls"] == "https://pbs.twimg.com/media/1.jpg"
    assert captured["video_urls"] == "https://video.twimg.com/2.mp4"
    assert json.loads(captured["urls"]) == [{"expanded_url": "https://example.com"}]
    assert json.loads(captured["user_mentions"]) == [{"screen_name": "bob"}]
    media_detail = json.loads(captured["media_detail"])
    assert len(media_detail) == 2
    assert media_detail[0]["display_url"] == "pic.twitter.com/1"
    assert media_detail[0]["width"] == 1080


@pytest.mark.asyncio
async def test_get_tweet_media_uses_video_url_for_animated_gif(monkeypatch, tmp_path):
    crawler = TwitterCrawler()

    requested_urls = []

    class _FakeClient:
        async def get_media(self, url):
            requested_urls.append(url)
            return b"binary"

    async def _noop_sleep(_=None):
        return None

    monkeypatch.setattr(config, "ENABLE_GET_MEIDAS", True)
    monkeypatch.setattr(config, "SAVE_DATA_PATH", str(tmp_path))
    monkeypatch.setattr("media_platform.twitter.core.safe_sleep", _noop_sleep)
    crawler.twitter_client = _FakeClient()

    tweet = TwitterTweet(
        id="tweet-1",
        media=[
            TwitterMedia(
                media_type="animated_gif",
                media_url="https://pbs.twimg.com/media/gif-thumb.jpg",
                video_url="https://video.twimg.com/tweet_video/a.mp4",
            )
        ],
    )

    await crawler._get_tweet_media(tweet)
    assert requested_urls == ["https://video.twimg.com/tweet_video/a.mp4"]
