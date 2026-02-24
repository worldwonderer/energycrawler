# -*- coding: utf-8 -*-
"""Tests for energycrawler CLI data latest command."""

from __future__ import annotations

import argparse
import json
from urllib.parse import parse_qs, urlparse

from scripts import energycrawler_cli as cli


def _latest_args(**overrides) -> argparse.Namespace:
    base = {
        "api_base": "http://127.0.0.1:8080",
        "platform": None,
        "file_type": None,
        "limit": 100,
        "download": False,
        "output": None,
        "json": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_parser_includes_data_latest_command():
    parser = cli._build_parser()
    args = parser.parse_args(["data", "latest", "--platform", "xhs", "--limit", "5"])

    assert args.command == "data"
    assert args.data_command == "latest"
    assert args.platform == "xhs"
    assert args.limit == 5
    assert args.handler is cli._data_latest_cmd


def test_data_latest_preview_outputs_summary(monkeypatch, capsys):
    seen: dict[str, str] = {}
    payload = {
        "success": True,
        "data": {
            "total": 12,
            "file": {"name": "latest.json", "type": "json"},
        },
    }

    def _fake_fetch(url: str, *, timeout: float = cli.DEFAULT_API_TIMEOUT):
        seen["url"] = url
        return 200, json.dumps(payload).encode("utf-8"), {}

    monkeypatch.setattr(cli, "_api_fetch", _fake_fetch)

    code = cli._data_latest_cmd(_latest_args(platform="xhs", file_type="json", limit=3))

    assert code == 0
    stdout = capsys.readouterr().out
    assert "[data latest] file=latest.json" in stdout
    assert "[data latest] type=json" in stdout
    assert "[data latest] records=12" in stdout

    query = parse_qs(urlparse(seen["url"]).query)
    assert query["preview"] == ["true"]
    assert query["platform"] == ["xhs"]
    assert query["file_type"] == ["json"]
    assert query["limit"] == ["3"]


def test_data_latest_preview_outputs_json(monkeypatch, capsys):
    payload = {
        "success": True,
        "data": {
            "total": 2,
            "file": {"name": "latest.csv", "type": "csv"},
        },
        "message": "Latest file preview",
    }
    monkeypatch.setattr(
        cli,
        "_api_fetch",
        lambda *_args, **_kwargs: (200, json.dumps(payload).encode("utf-8"), {}),
    )

    code = cli._data_latest_cmd(_latest_args(json=True))

    assert code == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_data_latest_download_writes_file(monkeypatch, tmp_path, capsys):
    seen: dict[str, str] = {}

    def _fake_fetch(url: str, *, timeout: float = cli.DEFAULT_API_TIMEOUT):
        seen["url"] = url
        return 200, b"csv-content", {"content-disposition": 'attachment; filename="newest.csv"'}

    monkeypatch.setattr(cli, "_api_fetch", _fake_fetch)

    output_dir = tmp_path / "downloads"
    output_dir.mkdir()
    code = cli._data_latest_cmd(_latest_args(download=True, output=str(output_dir), platform="x"))

    assert code == 0
    downloaded = output_dir / "newest.csv"
    assert downloaded.exists()
    assert downloaded.read_bytes() == b"csv-content"
    assert "downloaded:" in capsys.readouterr().out

    query = parse_qs(urlparse(seen["url"]).query)
    assert query["platform"] == ["x"]
    assert "preview" not in query
    assert "limit" not in query


def test_data_latest_returns_nonzero_for_404(monkeypatch, capsys):
    error_payload = {"success": False, "error": {"message": "No data files found"}}
    monkeypatch.setattr(
        cli,
        "_api_fetch",
        lambda *_args, **_kwargs: (404, json.dumps(error_payload).encode("utf-8"), {}),
    )

    code = cli._data_latest_cmd(_latest_args(platform="xhs"))

    assert code == 4
    stderr = capsys.readouterr().err
    assert "No latest file found" in stderr
    assert "Actionable next steps:" in stderr
    assert "uv run energycrawler run --platform xhs --keywords" in stderr


def test_data_latest_returns_nonzero_when_api_unreachable(monkeypatch, capsys):
    def _raise_unreachable(*_args, **_kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(cli, "_api_fetch", _raise_unreachable)

    code = cli._data_latest_cmd(_latest_args())

    assert code == 2
    stderr = capsys.readouterr().err
    assert "API unreachable" in stderr
    assert "Actionable next steps:" in stderr
    assert "uv run uvicorn api.main:app --port 8080 --reload" in stderr
