# -*- coding: utf-8 -*-
"""
Unit tests for Twitter crawler creator/user_tweets mode behavior.
"""

import pytest

import config
from media_platform.twitter.core import TwitterCrawler
from media_platform.twitter.exception import TwitterAuthError
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


@pytest.mark.asyncio
async def test_get_user_tweets_resume_uses_checkpoint_cursor(monkeypatch):
    crawler = TwitterCrawler()
    crawler._user_ids = ["123456"]
    crawler._max_count = 1

    monkeypatch.setattr(config, "ENABLE_INCREMENTAL_CRAWL", True)
    monkeypatch.setattr(config, "RESUME_FROM_CHECKPOINT", True)

    call_state = {"cursor": None}

    class _FakeCheckpoint:
        def get_scope(self, _scope):
            return {"in_progress": True, "cursor": "CURSOR_RESUME", "latest_item_id": ""}

        def mark_scope_started(self, *_args, **_kwargs):
            return {}

        def mark_scope_progress(self, *_args, **_kwargs):
            return {}

        def mark_scope_completed(self, *_args, **_kwargs):
            return {}

    class _FakeClient:
        async def get_user_by_screen_name(self, _screen_name):
            return None

        async def get_user_tweets(self, user_id, count, cursor, include_replies):
            assert user_id == "123456"
            assert count == 1
            assert include_replies is False
            call_state["cursor"] = cursor
            return {"tweets": [TwitterTweet(id="tweet-1")], "has_more": False, "cursor": None}

    async def _fake_process_tweet(_tweet, _semaphore):
        return None

    crawler._checkpoint = _FakeCheckpoint()
    crawler.twitter_client = _FakeClient()
    crawler._process_tweet_async_task = _fake_process_tweet  # type: ignore[method-assign]

    await crawler.get_user_tweets()
    assert call_state["cursor"] == "CURSOR_RESUME"


@pytest.mark.asyncio
async def test_get_user_tweets_incremental_stops_at_known_marker(monkeypatch):
    crawler = TwitterCrawler()
    crawler._user_ids = ["123456"]
    crawler._max_count = 5

    monkeypatch.setattr(config, "ENABLE_INCREMENTAL_CRAWL", True)
    monkeypatch.setattr(config, "RESUME_FROM_CHECKPOINT", True)

    call_state = {"api_calls": 0, "processed": [], "completed_latest_id": None}

    class _FakeCheckpoint:
        def get_scope(self, _scope):
            return {"in_progress": False, "cursor": "", "latest_item_id": "old-2"}

        def mark_scope_started(self, *_args, **_kwargs):
            return {}

        def mark_scope_progress(self, *_args, **_kwargs):
            return {}

        def mark_scope_completed(self, *_args, **kwargs):
            call_state["completed_latest_id"] = kwargs.get("latest_item_id")
            return {}

    class _FakeClient:
        async def get_user_by_screen_name(self, _screen_name):
            return None

        async def get_user_tweets(self, user_id, count, cursor, include_replies):
            call_state["api_calls"] += 1
            assert user_id == "123456"
            assert include_replies is False
            assert count == 5
            assert cursor is None
            return {
                "tweets": [
                    TwitterTweet(id="new-1"),
                    TwitterTweet(id="old-2"),
                    TwitterTweet(id="old-3"),
                ],
                "has_more": True,
                "cursor": "CURSOR_NEXT",
            }

    async def _fake_process_tweet(tweet, _semaphore):
        call_state["processed"].append(tweet.id)

    crawler._checkpoint = _FakeCheckpoint()
    crawler.twitter_client = _FakeClient()
    crawler._process_tweet_async_task = _fake_process_tweet  # type: ignore[method-assign]

    await crawler.get_user_tweets()

    assert call_state["api_calls"] == 1
    assert call_state["processed"] == ["new-1"]
    assert call_state["completed_latest_id"] == "new-1"


@pytest.mark.asyncio
async def test_watchdog_check_x_auth_uses_cookie_pair_and_page_signal():
    crawler = TwitterCrawler()

    class _FakeClient:
        async def pong(self):
            return True

    class _FakeAdapter:
        def get_auth_cookies(self):
            return {"auth_token": "from-adapter", "ct0": "from-adapter"}

        async def verify_login_via_page(self):
            return True

    crawler.twitter_client = _FakeClient()
    crawler.energy_adapter = _FakeAdapter()
    crawler._auth_token = ""
    crawler._ct0 = ""

    assert await crawler._watchdog_check_x_auth() is True


@pytest.mark.asyncio
async def test_recover_runtime_auth_if_needed_respects_budget(monkeypatch):
    crawler = TwitterCrawler()
    monkeypatch.setattr(config, "AUTH_WATCHDOG_ENABLED", True)
    monkeypatch.setattr(config, "AUTH_WATCHDOG_MAX_RUNTIME_RECOVERIES", 1)

    call_state = {"recover_calls": 0}

    async def _fake_recover(_attempt):
        call_state["recover_calls"] += 1
        return True

    crawler._watchdog_recover_x_auth = _fake_recover  # type: ignore[method-assign]

    first = await crawler._recover_runtime_auth_if_needed(
        TwitterAuthError("Authentication failed: 401"),
        context="search",
        attempt=1,
    )
    second = await crawler._recover_runtime_auth_if_needed(
        TwitterAuthError("Authentication failed: 401"),
        context="search",
        attempt=2,
    )

    assert first is True
    assert second is False
    assert call_state["recover_calls"] == 1
