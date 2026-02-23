# -*- coding: utf-8 -*-
"""
Unit tests for XHS JSON store creator persistence.
"""

import json
from pathlib import Path

import pytest

import config
from store.xhs._store_impl import XhsJsonStoreImplement
from var import crawler_type_var


@pytest.mark.asyncio
async def test_xhs_json_store_creator_writes_output(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SAVE_DATA_PATH", str(tmp_path))
    token = crawler_type_var.set("creator")
    try:
        store = XhsJsonStoreImplement()
        await store.store_creator({"user_id": "u1", "nickname": "author-1"})
        await store.store_creator({"user_id": "u2", "nickname": "author-2"})
    finally:
        crawler_type_var.reset(token)

    creators_dir = Path(tmp_path) / "xhs" / "json"
    files = list(creators_dir.glob("creator_creators_*.json"))
    assert len(files) == 1

    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert [item.get("user_id") for item in data] == ["u1", "u2"]
