# -*- coding: utf-8 -*-
"""
Unit tests for crawl checkpoint manager.
"""

from __future__ import annotations

import json

import config
from tools.crawl_checkpoint import CrawlCheckpointManager


def test_checkpoint_path_resolution_with_save_data_path(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SAVE_DATA_PATH", str(tmp_path), raising=False)
    monkeypatch.setattr(config, "CRAWLER_CHECKPOINT_PATH", "", raising=False)

    manager = CrawlCheckpointManager()
    state = manager.mark_scope_started(
        "x:search:test",
        platform="x",
        crawler_type="search",
        cursor="CURSOR_1",
    )
    assert state["in_progress"] is True

    checkpoint_file = tmp_path / "checkpoints" / "crawl_state.json"
    assert checkpoint_file.exists()

    payload = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    assert "x:search:test" in payload["scopes"]


def test_checkpoint_lifecycle_roundtrip(tmp_path):
    checkpoint_file = tmp_path / "state.json"
    manager = CrawlCheckpointManager(str(checkpoint_file))

    manager.mark_scope_started(
        "x:user_tweets:1",
        platform="x",
        crawler_type="creator",
        cursor="CURSOR_A",
    )
    manager.mark_scope_progress(
        "x:user_tweets:1",
        cursor="CURSOR_B",
        latest_item_id="200",
    )
    manager.mark_scope_completed(
        "x:user_tweets:1",
        latest_item_id="201",
    )

    state = manager.get_scope("x:user_tweets:1")
    assert state["in_progress"] is False
    assert state["cursor"] == ""
    assert state["latest_item_id"] == "201"
