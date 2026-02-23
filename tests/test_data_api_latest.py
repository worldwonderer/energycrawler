# -*- coding: utf-8 -*-
"""Tests for latest data preview/download API."""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers import data as data_router_module


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys()) if rows else ["id"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _touch_mtime(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(data_router_module, "DATA_DIR", tmp_path)
    return tmp_path


def test_latest_preview_selects_newest_file(isolated_data_dir: Path):
    now = time.time()
    old_json = isolated_data_dir / "xhs" / "old.json"
    new_csv = isolated_data_dir / "x" / "new.csv"

    _write_json(old_json, [{"id": 1}, {"id": 2}])
    _write_csv(new_csv, [{"id": "10", "name": "alice"}, {"id": "11", "name": "bob"}])
    _touch_mtime(old_json, now - 60)
    _touch_mtime(new_csv, now)

    client = TestClient(app)
    resp = client.get("/api/data/latest")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["file"]["name"] == "new.csv"
    assert payload["data"]["file"]["type"] == "csv"
    assert payload["data"]["total"] == 2
    assert payload["data"]["data"][0]["id"] == "10"


def test_latest_preview_supports_platform_filter_and_limit(isolated_data_dir: Path):
    now = time.time()
    xhs_latest = isolated_data_dir / "xhs" / "latest.json"
    x_newer = isolated_data_dir / "x" / "newer.json"

    _write_json(xhs_latest, [{"id": 1}, {"id": 2}, {"id": 3}])
    _write_json(x_newer, [{"id": 9}])
    _touch_mtime(xhs_latest, now - 5)
    _touch_mtime(x_newer, now)

    client = TestClient(app)
    resp = client.get("/api/data/latest", params={"platform": "xhs", "limit": 1})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["file"]["name"] == "latest.json"
    assert payload["data"]["file"]["path"].startswith("xhs/")
    assert payload["data"]["total"] == 3
    assert len(payload["data"]["data"]) == 1


def test_latest_download_endpoint_returns_latest_file(isolated_data_dir: Path):
    now = time.time()
    older = isolated_data_dir / "xhs" / "older.json"
    newer = isolated_data_dir / "xhs" / "newer.json"

    _write_json(older, [{"id": 1}])
    _write_json(newer, [{"id": 2}])
    _touch_mtime(older, now - 30)
    _touch_mtime(newer, now)

    client = TestClient(app)
    resp = client.get("/api/data/latest/download", params={"platform": "xhs"})

    assert resp.status_code == 200
    assert "attachment; filename=\"newer.json\"" in resp.headers.get("content-disposition", "")
    assert b'"id": 2' in resp.content


def test_latest_returns_404_when_no_matching_files(isolated_data_dir: Path):
    client = TestClient(app)
    resp = client.get("/api/data/latest", params={"platform": "xhs"})

    assert resp.status_code == 404
    payload = resp.json()
    assert payload["success"] is False
    assert "No data files found" in payload["error"]["message"]


def test_latest_returns_400_for_unsupported_file_type(isolated_data_dir: Path):
    _write_json(isolated_data_dir / "xhs" / "sample.json", [{"id": 1}])

    client = TestClient(app)
    resp = client.get("/api/data/latest", params={"file_type": "txt"})

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["success"] is False
    assert "Unsupported file type" in payload["error"]["message"]
