# -*- coding: utf-8 -*-
"""
Unit tests for Twitter crawler creator/user_tweets mode behavior.
"""

import pytest

import config
from media_platform.twitter.core import TwitterCrawler
from media_platform.twitter.field import TwitterCrawlerMode
from media_platform.twitter.models import TwitterTweet, TwitterUser


def test_creator_type_maps_to_user_tweets_mode(monkeypatch):
    monkeypatch.setattr(config, "CRAWLER_TYPE", "creator")
    crawler = TwitterCrawler()
    assert crawler._get_crawler_mode() == TwitterCrawlerMode.USER_TWEETS


@pytest.mark.asyncio
async def test_get_user_tweets_resolves_screen_name_and_uses_resolved_id():
    crawler = TwitterCrawler()
    crawler._user_ids = ["elonmusk"]
    crawler._max_count = 1

    call_state = {"resolved": None, "stored_user_id": None}

    class _FakeClient:
        async def get_user_by_screen_name(self, screen_name):
            assert screen_name == "elonmusk"
            return TwitterUser(id="44196397", screen_name="elonmusk")

        async def get_user_tweets(self, user_id, count, cursor, include_replies):
            call_state["resolved"] = user_id
            assert count == 1
            assert cursor is None
            assert include_replies is False
            return {"tweets": [TwitterTweet(id="tweet-1")], "has_more": False, "cursor": None}

    async def _fake_store_user(user):
        call_state["stored_user_id"] = user.id

    async def _fake_process_tweet(_tweet, _semaphore):
        return None

    crawler.twitter_client = _FakeClient()
    crawler._store_user = _fake_store_user  # type: ignore[method-assign]
    crawler._process_tweet_async_task = _fake_process_tweet  # type: ignore[method-assign]

    await crawler.get_user_tweets()

    assert call_state["resolved"] == "44196397"
    assert call_state["stored_user_id"] == "44196397"


@pytest.mark.asyncio
async def test_get_user_tweets_keeps_numeric_user_id():
    crawler = TwitterCrawler()
    crawler._user_ids = ["123456"]
    crawler._max_count = 1

    call_state = {"resolved": None, "lookup_called": False}

    class _FakeClient:
        async def get_user_by_screen_name(self, _screen_name):
            call_state["lookup_called"] = True
            return None

        async def get_user_tweets(self, user_id, count, cursor, include_replies):
            call_state["resolved"] = user_id
            assert count == 1
            assert cursor is None
            assert include_replies is False
            return {"tweets": [TwitterTweet(id="tweet-1")], "has_more": False, "cursor": None}

    async def _fake_process_tweet(_tweet, _semaphore):
        return None

    crawler.twitter_client = _FakeClient()
    crawler._process_tweet_async_task = _fake_process_tweet  # type: ignore[method-assign]

    await crawler.get_user_tweets()

    assert call_state["lookup_called"] is False
    assert call_state["resolved"] == "123456"


@pytest.mark.asyncio
async def test_close_is_idempotent():
    crawler = TwitterCrawler()
    close_calls = {"client": 0, "disconnect": 0}

    class _FakeClient:
        def close(self):
            close_calls["client"] += 1

    class _FakeAdapter:
        browser = None
        browser_id = "browser-1"

        def disconnect(self):
            close_calls["disconnect"] += 1

    crawler.twitter_client = _FakeClient()
    crawler.energy_adapter = _FakeAdapter()

    await crawler.close()
    await crawler.close()

    assert close_calls["client"] == 1
    assert close_calls["disconnect"] == 1
