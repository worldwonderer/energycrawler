# -*- coding: utf-8 -*-
"""
Unit tests for XHS client incremental creator pagination.
"""

from __future__ import annotations

import pytest

import config
from media_platform.xhs.client import XiaoHongShuClient


@pytest.mark.asyncio
async def test_get_all_notes_by_creator_supports_start_cursor_and_stop_marker(monkeypatch):
    client = XiaoHongShuClient.__new__(XiaoHongShuClient)  # bypass __init__ for isolated method test

    calls = {"cursor": [], "progress": [], "callback_note_ids": []}

    responses = [
        {
            "has_more": True,
            "cursor": "CURSOR_NEXT_1",
            "notes": [
                {"note_id": "note-new-3"},
                {"note_id": "note-known-2"},
            ],
        },
        {
            "has_more": True,
            "cursor": "CURSOR_NEXT_2",
            "notes": [{"note_id": "note-old-1"}],
        },
    ]

    async def _fake_get_notes_by_creator(user_id, cursor, page_size=30, xsec_token="", xsec_source="pc_feed"):
        assert user_id == "user-1"
        calls["cursor"].append(cursor)
        return responses.pop(0)

    async def _fake_callback(notes):
        calls["callback_note_ids"].extend([n.get("note_id") for n in notes])

    async def _fake_progress(cursor):
        calls["progress"].append(cursor)

    async def _noop_sleep(_):
        return None

    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 10)
    monkeypatch.setattr(client, "get_notes_by_creator", _fake_get_notes_by_creator)
    monkeypatch.setattr("media_platform.xhs.client.asyncio.sleep", _noop_sleep)

    result = await client.get_all_notes_by_creator(
        user_id="user-1",
        crawl_interval=0.0,
        callback=_fake_callback,
        start_cursor="CURSOR_RESUME",
        stop_note_id="note-known-2",
        progress_callback=_fake_progress,
    )

    assert calls["cursor"] == ["CURSOR_RESUME"]
    assert calls["callback_note_ids"] == ["note-new-3"]
    assert calls["progress"] == ["CURSOR_NEXT_1"]
    assert [n.get("note_id") for n in result] == ["note-new-3"]
