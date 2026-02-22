#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check local links in markdown files."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from pathlib import Path


_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_IGNORE_PARTS = {".git", ".venv", "node_modules", "__pycache__"}


def _is_external(target: str) -> bool:
    if target.startswith("#"):
        return True
    parsed = urllib.parse.urlparse(target)
    return bool(parsed.scheme and parsed.scheme not in {"", "file"})


def _iter_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.md"):
        if any(part in _IGNORE_PARTS for part in path.parts):
            continue
        files.append(path)
    return files


def _normalize_target(target: str) -> str:
    decoded = urllib.parse.unquote(target.strip())
    decoded = decoded.split("#", 1)[0].split("?", 1)[0]
    return decoded


def find_missing_links(root: Path) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for md_file in _iter_markdown_files(root):
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        for raw_target in _LINK_RE.findall(content):
            if _is_external(raw_target):
                continue
            target = _normalize_target(raw_target)
            if not target:
                continue
            candidate = (md_file.parent / target).resolve()
            if not candidate.exists():
                missing.append(
                    {
                        "file": str(md_file.relative_to(root)),
                        "target": raw_target,
                    }
                )
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Check markdown local links")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    missing = find_missing_links(root)
    payload = {"root": str(root), "missing_links": missing}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif missing:
        print("Missing markdown links:")
        for item in missing:
            print(f"- {item['file']} -> {item['target']}")
    else:
        print("Markdown link check passed")

    raise SystemExit(1 if missing else 0)


if __name__ == "__main__":
    main()
