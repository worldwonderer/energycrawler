# -*- coding: utf-8 -*-
"""Tests for latest data preview/download API."""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
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


def test_latest_platform_x_does_not_match_xhs_by_substring(isolated_data_dir: Path):
    now = time.time()
    xhs_newer = isolated_data_dir / "xhs" / "newer.json"
    x_older = isolated_data_dir / "x" / "older.json"

    _write_json(xhs_newer, [{"id": "xhs"}])
    _write_json(x_older, [{"id": "x"}])
    _touch_mtime(xhs_newer, now)
    _touch_mtime(x_older, now - 10)

    client = TestClient(app)
    resp = client.get("/api/data/latest", params={"platform": "x"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["file"]["path"].startswith("x/")
    assert payload["data"]["data"][0]["id"] == "x"


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


def test_files_endpoint_supports_pagination_and_sorting(isolated_data_dir: Path):
    _write_json(isolated_data_dir / "xhs" / "c.json", [{"id": 3}])
    _write_json(isolated_data_dir / "xhs" / "a.json", [{"id": 1}])
    _write_json(isolated_data_dir / "xhs" / "b.json", [{"id": 2}])

    client = TestClient(app)
    resp_page1 = client.get(
        "/api/data/files",
        params={"sort_by": "name", "sort_order": "asc", "page": 1, "page_size": 2},
    )

    assert resp_page1.status_code == 200
    payload_page1 = resp_page1.json()
    assert payload_page1["success"] is True
    assert payload_page1["data"]["total"] == 3
    assert payload_page1["data"]["total_pages"] == 2
    assert [item["name"] for item in payload_page1["data"]["files"]] == ["a.json", "b.json"]

    resp_page2 = client.get(
        "/api/data/files",
        params={"sort_by": "name", "sort_order": "asc", "page": 2, "page_size": 2},
    )
    assert resp_page2.status_code == 200
    payload_page2 = resp_page2.json()
    assert [item["name"] for item in payload_page2["data"]["files"]] == ["c.json"]


def test_files_endpoint_keeps_default_sort_by_modified_desc(isolated_data_dir: Path):
    now = time.time()
    older = isolated_data_dir / "x" / "older.json"
    newer = isolated_data_dir / "x" / "newer.json"
    _write_json(older, [{"id": 1}])
    _write_json(newer, [{"id": 2}])
    _touch_mtime(older, now - 10)
    _touch_mtime(newer, now)

    client = TestClient(app)
    resp = client.get("/api/data/files")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["files"][0]["name"] == "newer.json"
    assert payload["data"]["files"][1]["name"] == "older.json"


def test_data_stats_supports_platform_and_date_range(isolated_data_dir: Path):
    day1 = datetime(2026, 2, 1, 8, 0, tzinfo=timezone.utc).timestamp()
    day2 = datetime(2026, 2, 2, 9, 0, tzinfo=timezone.utc).timestamp()
    day3 = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc).timestamp()

    xhs_file = isolated_data_dir / "xhs" / "xhs.json"
    x_file_json = isolated_data_dir / "x" / "x.json"
    x_file_csv = isolated_data_dir / "x" / "x.csv"
    twitter_file = isolated_data_dir / "twitter" / "tw.json"

    _write_json(xhs_file, [{"id": "xhs"}])
    _write_json(x_file_json, [{"id": "x"}])
    _write_csv(x_file_csv, [{"id": "1", "name": "a"}])
    _write_json(twitter_file, [{"id": "tw"}])

    _touch_mtime(xhs_file, day1)
    _touch_mtime(x_file_json, day2)
    _touch_mtime(x_file_csv, day2)
    _touch_mtime(twitter_file, day3)

    client = TestClient(app)
    resp = client.get(
        "/api/data/stats",
        params={"platform": "x", "date_from": "2026-02-02", "date_to": "2026-02-02"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["total_files"] == 2
    assert data["by_platform"] == {"x": 2}
    assert data["by_type"] == {"json": 1, "csv": 1}
    assert data["by_date"] == {"2026-02-02": 2}
    assert data["filters"]["platform"] == "x"
    assert data["filters"]["date_from"] == "2026-02-02"
    assert data["filters"]["date_to"] == "2026-02-02"


def test_data_stats_supports_from_to_alias(isolated_data_dir: Path):
    day3 = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc).timestamp()
    twitter_file = isolated_data_dir / "twitter" / "tw.json"
    _write_json(twitter_file, [{"id": "tw"}])
    _touch_mtime(twitter_file, day3)

    client = TestClient(app)
    resp = client.get(
        "/api/data/stats",
        params={"platform": "x", "from": "2026-02-03", "to": "2026-02-03"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["total_files"] == 1
    assert payload["data"]["by_platform"] == {"twitter": 1}
    assert payload["data"]["by_date"] == {"2026-02-03": 1}


def test_data_stats_rejects_invalid_date_range(isolated_data_dir: Path):
    _write_json(isolated_data_dir / "xhs" / "sample.json", [{"id": 1}])

    client = TestClient(app)
    resp = client.get(
        "/api/data/stats",
        params={"date_from": "2026-02-03", "date_to": "2026-02-01"},
    )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["success"] is False
    assert "date_from must be less than or equal to date_to" in payload["error"]["message"]
