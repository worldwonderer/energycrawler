# -*- coding: utf-8 -*-
"""
Regression tests for XHS field and flow completeness fixes.
"""

from __future__ import annotations

import json

import pytest

import config
from media_platform.xhs.core import XiaoHongShuCrawler
from store import xhs as xhs_store
from store.xhs._store_impl import XhsDbStoreImplement


class _CaptureStore:
    def __init__(self) -> None:
        self.comments = []
        self.creators = []

    async def store_comment(self, item):
        self.comments.append(item)

    async def store_creator(self, item):
        self.creators.append(item)


@pytest.mark.asyncio
async def test_update_xhs_note_sub_comment_sets_parent_comment_id(monkeypatch):
    capture = _CaptureStore()
    monkeypatch.setattr(xhs_store.XhsStoreFactory, "create_store", staticmethod(lambda: capture))

    sub_comment = {
        "id": "sub-1",
        "create_time": 1,
        "content": "hello",
        "user_info": {"user_id": "u1", "nickname": "n1", "image": "a1"},
        "pictures": [],
    }

    await xhs_store.update_xhs_note_sub_comment(
        note_id="note-1",
        root_comment_id="root-1",
        sub_comment=sub_comment,
    )

    assert len(capture.comments) == 1
    assert capture.comments[0]["parent_comment_id"] == "root-1"


@pytest.mark.asyncio
async def test_save_creator_handles_missing_interactions_and_tags(monkeypatch):
    capture = _CaptureStore()
    monkeypatch.setattr(xhs_store.XhsStoreFactory, "create_store", staticmethod(lambda: capture))

    creator = {
        "basicInfo": {
            "nickname": "author",
            "gender": 1,
            "images": ["https://example.com/a.png"],
            "desc": "bio",
            "ipLocation": "广东",
        },
        "interactions": None,
        "tags": None,
    }

    await xhs_store.save_creator("creator-1", creator)

    assert len(capture.creators) == 1
    creator_item = capture.creators[0]
    assert creator_item["user_id"] == "creator-1"
    assert creator_item["avatar"] == "https://example.com/a.png"
    assert creator_item["follows"] == 0
    assert creator_item["fans"] == 0
    assert creator_item["interaction"] == 0
    assert json.loads(creator_item["tag_list"]) == {}


@pytest.mark.asyncio
async def test_get_notice_media_downloads_video_when_image_list_empty(monkeypatch):
    crawler = XiaoHongShuCrawler()

    class _FakeClient:
        async def get_note_media(self, _url):
            return b"binary-media"

    crawler.xhs_client = _FakeClient()

    calls = {"video": 0}

    async def _fake_store_video(_note_id, _content, _ext):
        calls["video"] += 1

    async def _noop_sleep(_=None):
        return None

    monkeypatch.setattr(config, "ENABLE_GET_MEIDAS", True)
    monkeypatch.setattr(xhs_store, "get_video_url_arr", lambda _detail: ["https://example.com/video.mp4"])
    monkeypatch.setattr(xhs_store, "update_xhs_note_video", _fake_store_video)
    monkeypatch.setattr("media_platform.xhs.core.safe_sleep", _noop_sleep)

    await crawler.get_notice_media({"note_id": "note-1", "image_list": []})
    assert calls["video"] == 1


@pytest.mark.asyncio
async def test_get_specified_notes_reads_xhs_specified_note_url_list(monkeypatch):
    crawler = XiaoHongShuCrawler()
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 1)
    monkeypatch.setattr(
        config,
        "XHS_SPECIFIED_NOTE_URL_LIST",
        ["https://www.xiaohongshu.com/explore/note001?xsec_token=tok&xsec_source=pc_search"],
    )

    calls = {"details": 0}

    async def _fake_detail_task(note_id, xsec_source, xsec_token, semaphore):
        assert note_id == "note001"
        assert xsec_source == "pc_search"
        assert xsec_token == "tok"
        calls["details"] += 1
        return {"note_id": note_id, "xsec_token": xsec_token}

    async def _noop_store(_item):
        return None

    async def _noop_media(_detail):
        return None

    async def _noop_batch(_ids, _tokens):
        return None

    monkeypatch.setattr(crawler, "get_note_detail_async_task", _fake_detail_task)
    monkeypatch.setattr(xhs_store, "update_xhs_note", _noop_store)
    monkeypatch.setattr(crawler, "get_notice_media", _noop_media)
    monkeypatch.setattr(crawler, "batch_get_note_comments", _noop_batch)

    await crawler.get_specified_notes()
    assert calls["details"] == 1


def test_xhs_db_normalize_json_text_avoids_double_encoding():
    normalized = XhsDbStoreImplement._normalize_json_text('{"info":"tag"}')
    assert normalized == '{"info":"tag"}'

    normalized_dict = XhsDbStoreImplement._normalize_json_text({"info": "tag"})
    assert json.loads(normalized_dict) == {"info": "tag"}


def test_split_new_notes_before_marker_stops_at_known_note():
    notes = [
        {"id": "note-new-3"},
        {"id": "note-known-2"},
        {"id": "note-old-1"},
    ]
    new_notes, marker_found = XiaoHongShuCrawler._split_new_notes_before_marker(notes, "note-known-2")
    assert marker_found is True
    assert [n["id"] for n in new_notes] == ["note-new-3"]


@pytest.mark.asyncio
async def test_create_xhs_client_prefers_explicit_cookie_values_over_runtime_cookie_refresh():
    crawler = XiaoHongShuCrawler()
    crawler._cookie_header = "a1=config-a1; web_session=config-session; id_token=config-id-token"

    class _FakeEnergyAdapter:
        def get_cookies(self):
            # Simulate runtime cookie refresh after page load (anonymous/session-rotated values)
            return {
                "a1": "runtime-a1",
                "web_session": "runtime-session",
                "id_token": "runtime-id-token",
                "acw_tc": "runtime-acw",
            }

    crawler.energy_adapter = _FakeEnergyAdapter()

    client = await crawler._create_xhs_client()
    assert client.cookie_dict["a1"] == "config-a1"
    assert client.cookie_dict["web_session"] == "config-session"
    assert client.cookie_dict["id_token"] == "config-id-token"
    # Runtime-only cookies should still be retained.
    assert client.cookie_dict["acw_tc"] == "runtime-acw"
