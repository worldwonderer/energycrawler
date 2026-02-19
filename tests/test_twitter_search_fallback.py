# -*- coding: utf-8 -*-
"""
Unit tests for SearchTimeline query-id fallback logic.
"""

import pytest

import media_platform.twitter.client as twitter_client_module
from media_platform.twitter.client import TwitterClient
from media_platform.twitter.exception import TwitterNotFoundError


class _DummyEnergyAdapter:
    async def get_user_agent(self) -> str:
        return "test-agent"

    async def generate_transaction_id(self, method: str, path: str) -> str:
        return f"{method}:{path}"


def _timeline_with_single_tweet(tweet_id: str = "1") -> dict:
    return {
        "data": {
            "timeline_payload": {
                "instructions": [
                    {
                        "type": "TimelineAddEntries",
                        "entries": [
                            {
                                "entryId": f"tweet-{tweet_id}",
                                "content": {
                                    "entryType": "TimelineTimelineItem",
                                    "itemContent": {
                                        "tweet_results": {
                                            "result": {
                                                "rest_id": tweet_id,
                                                "legacy": {
                                                    "id_str": tweet_id,
                                                    "full_text": "hello",
                                                    "created_at": "Wed Oct 10 20:19:24 +0000 2018",
                                                    "reply_count": 0,
                                                    "retweet_count": 0,
                                                    "favorite_count": 0,
                                                    "bookmark_count": 0,
                                                    "quote_count": 0,
                                                    "entities": {"hashtags": [], "urls": [], "user_mentions": []},
                                                },
                                                "views": {"count": "1"},
                                                "core": {
                                                    "user_results": {
                                                        "result": {
                                                            "rest_id": "u1",
                                                            "legacy": {"screen_name": "alice", "name": "Alice"},
                                                        }
                                                    }
                                                },
                                            }
                                        }
                                    },
                                },
                            }
                        ],
                    }
                ]
            }
        }
    }


@pytest.mark.asyncio
async def test_search_timeline_fallback_to_second_candidate(monkeypatch):
    client = TwitterClient(energy_adapter=_DummyEnergyAdapter())
    attempts = []
    primaries = []

    monkeypatch.setattr(
        twitter_client_module,
        "get_search_timeline_operation_paths",
        lambda: ["bad/SearchTimeline", "good/SearchTimeline"],
    )
    monkeypatch.setattr(
        twitter_client_module,
        "refresh_search_timeline_query_ids",
        lambda: [],
    )
    monkeypatch.setattr(
        twitter_client_module,
        "set_primary_search_timeline_query_id",
        lambda query_id: primaries.append(query_id),
    )

    async def fake_request(_method, _operation, _variables, _features=None, operation_path=None):
        attempts.append(operation_path)
        if operation_path == "bad/SearchTimeline":
            raise TwitterNotFoundError("Resource not found: SearchTimeline")
        return _timeline_with_single_tweet("11")

    client._request = fake_request  # type: ignore[method-assign]
    result = await client.search_tweets("keyword", count=5)

    assert attempts == ["bad/SearchTimeline", "good/SearchTimeline"]
    assert [tweet.id for tweet in result["tweets"]] == ["11"]
    assert primaries == ["good"]


@pytest.mark.asyncio
async def test_search_timeline_refreshes_query_ids_when_all_candidates_fail(monkeypatch):
    client = TwitterClient(energy_adapter=_DummyEnergyAdapter())
    attempts = []
    primaries = []

    monkeypatch.setattr(
        twitter_client_module,
        "get_search_timeline_operation_paths",
        lambda: ["old/SearchTimeline"],
    )
    monkeypatch.setattr(
        twitter_client_module,
        "refresh_search_timeline_query_ids",
        lambda: ["old", "fresh"],
    )
    monkeypatch.setattr(
        twitter_client_module,
        "set_primary_search_timeline_query_id",
        lambda query_id: primaries.append(query_id),
    )

    async def fake_request(_method, _operation, _variables, _features=None, operation_path=None):
        attempts.append(operation_path)
        if operation_path != "fresh/SearchTimeline":
            raise TwitterNotFoundError("Resource not found: SearchTimeline")
        return _timeline_with_single_tweet("22")

    client._request = fake_request  # type: ignore[method-assign]
    result = await client.search_tweets("keyword", count=5)

    assert attempts == ["old/SearchTimeline", "fresh/SearchTimeline"]
    assert [tweet.id for tweet in result["tweets"]] == ["22"]
    assert primaries == ["fresh"]
