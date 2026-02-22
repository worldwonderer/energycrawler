# -*- coding: utf-8 -*-
"""Tests for documentation tooling scripts."""

from pathlib import Path

from tools.check_markdown_links import find_missing_links
from tools.cleanup_report import (
    find_absolute_path_mentions,
    find_legacy_command_usage,
    find_stale_report_docs,
    find_trailing_whitespace,
    find_unreferenced_doc_images,
)


def test_markdown_link_checker_reports_missing_local_files(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "guide.md"
    md.write_text("[ok](./exists.md)\n[bad](./missing.md)\n", encoding="utf-8")
    (docs / "exists.md").write_text("# ok\n", encoding="utf-8")

    missing = find_missing_links(tmp_path)
    assert {"file": "docs/guide.md", "target": "./missing.md"} in missing
    assert {"file": "docs/guide.md", "target": "./exists.md"} not in missing


def test_cleanup_helpers_detect_unused_images_and_stale_docs(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    images_dir = docs_dir / "static" / "images"
    images_dir.mkdir(parents=True)
    used = images_dir / "used.png"
    unused = images_dir / "unused.png"
    used.write_text("x", encoding="utf-8")
    unused.write_text("x", encoding="utf-8")

    tracked = [
        tmp_path / "README.md",
        tmp_path / "notes" / "IMPLEMENTATION_SUMMARY.md",
    ]
    tracked[0].write_text("![img](docs/static/images/used.png)", encoding="utf-8")
    tracked[1].parent.mkdir(parents=True, exist_ok=True)
    tracked[1].write_text("stale", encoding="utf-8")
    corpus = tracked[0].read_text(encoding="utf-8")

    images = find_unreferenced_doc_images(tmp_path, corpus)
    assert "docs/static/images/unused.png" in images
    assert "docs/static/images/used.png" not in images

    stale = find_stale_report_docs(tmp_path, corpus, tracked)
    assert "notes/IMPLEMENTATION_SUMMARY.md" in stale


def test_cleanup_helpers_detect_legacy_commands(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "python3 scripts/energycrawler_cli.py energy ensure\n"
        "uv run energycrawler energy ensure\n",
        encoding="utf-8",
    )
    tracked = [readme]
    findings = find_legacy_command_usage(tmp_path, tracked)
    assert findings == [
        {
            "file": "README.md",
            "line": 1,
            "pattern": "python3 scripts/energycrawler_cli.py",
        }
    ]


def test_cleanup_helpers_detect_absolute_paths(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("cd /Users/demo/energycrawler\n", encoding="utf-8")
    tracked = [readme]
    findings = find_absolute_path_mentions(tmp_path, tracked)
    assert findings == [
        {
            "file": "README.md",
            "line": 1,
            "match": "/Users/demo/energycrawler",
        }
    ]


def test_cleanup_helpers_detect_trailing_whitespace(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("good\nbad  \n", encoding="utf-8")
    tracked = [readme]
    findings = find_trailing_whitespace(tmp_path, tracked)
    assert findings == [{"file": "README.md", "line": 2}]
