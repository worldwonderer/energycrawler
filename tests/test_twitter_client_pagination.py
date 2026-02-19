# -*- coding: utf-8 -*-
"""
Unit tests for TwitterClient pagination and cursor extraction.
"""

import pytest

from media_platform.twitter.client import TwitterClient


class _DummyEnergyAdapter:
    async def get_user_agent(self) -> str:
        return "test-agent"

    async def generate_transaction_id(self, method: str, path: str) -> str:
        return f"{method}:{path}"


def _tweet_result(tweet_id: str, screen_name: str, text: str) -> dict:
    return {
        "rest_id": tweet_id,
        "legacy": {
            "id_str": tweet_id,
            "full_text": text,
            "created_at": "Wed Oct 10 20:19:24 +0000 2018",
            "reply_count": 1,
            "retweet_count": 2,
            "favorite_count": 3,
            "bookmark_count": 0,
            "quote_count": 0,
            "entities": {"hashtags": [], "urls": [], "user_mentions": []},
        },
        "views": {"count": "11"},
        "core": {
            "user_results": {
                "result": {
                    "rest_id": f"user-{screen_name}",
                    "legacy": {"screen_name": screen_name, "name": screen_name.title()},
                }
            }
        },
    }


def _tweet_entry(tweet_id: str, screen_name: str, text: str) -> dict:
    return {
        "entryId": f"tweet-{tweet_id}",
        "content": {
            "entryType": "TimelineTimelineItem",
            "itemContent": {
                "tweet_results": {"result": _tweet_result(tweet_id, screen_name, text)},
            },
        },
    }


def _cursor_entry(value: str) -> dict:
    return {
        "entryId": "cursor-bottom-1",
        "content": {
            "entryType": "TimelineTimelineCursor",
            "cursorType": "Bottom",
            "value": value,
        },
    }


def _timeline_response(entries: list[dict]) -> dict:
    return {
        "data": {
            "timeline_payload": {
                "instructions": [
                    {
                        "type": "TimelineAddEntries",
                        "entries": entries,
                    }
                ]
            }
        }
    }


@pytest.mark.asyncio
async def test_search_tweets_extracts_cursor_and_limits_count():
    client = TwitterClient(energy_adapter=_DummyEnergyAdapter())

    async def fake_request(_method, operation, _variables, _features=None):
        assert operation == "SearchTimeline"
        return _timeline_response(
            [
                _tweet_entry("1", "alice", "hello"),
                _tweet_entry("2", "bob", "world"),
                _tweet_entry("3", "carol", "third"),
                _cursor_entry("CURSOR_NEXT"),
            ]
        )

    client._request = fake_request  # type: ignore[method-assign]
    result = await client.search_tweets("python", count=2)

    assert [tweet.id for tweet in result["tweets"]] == ["1", "2"]
    assert result["cursor"] == "CURSOR_NEXT"
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_get_user_tweets_returns_page_contract_and_operation():
    client = TwitterClient(energy_adapter=_DummyEnergyAdapter())
    call_state = {}

    async def fake_request(_method, operation, variables, _features=None):
        call_state["operation"] = operation
        call_state["count"] = variables["count"]
        return _timeline_response([_tweet_entry("10", "dave", "single page")])

    client._request = fake_request  # type: ignore[method-assign]
    result = await client.get_user_tweets(user_id="123", count=7, include_replies=True)

    assert call_state["operation"] == "UserTweetsAndReplies"
    assert call_state["count"] == 7
    assert [tweet.id for tweet in result["tweets"]] == ["10"]
    assert result["cursor"] is None
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_get_tweet_replies_excludes_focal_tweet():
    client = TwitterClient(energy_adapter=_DummyEnergyAdapter())

    async def fake_request(_method, operation, _variables, _features=None):
        assert operation == "TweetDetail"
        return _timeline_response(
            [
                _tweet_entry("111", "owner", "main tweet"),
                _tweet_entry("222", "replier", "reply tweet"),
                _cursor_entry("CURSOR_REPLY_NEXT"),
            ]
        )

    client._request = fake_request  # type: ignore[method-assign]
    result = await client.get_tweet_replies(tweet_id="111", count=20)

    assert [tweet.id for tweet in result["tweets"]] == ["222"]
    assert result["cursor"] == "CURSOR_REPLY_NEXT"
    assert result["has_more"] is True
