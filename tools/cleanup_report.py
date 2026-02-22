#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate cleanup and hygiene findings for the repository."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.parse
from pathlib import Path


_TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".go",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".txt",
    ".proto",
    ".js",
    ".ts",
}
_STALE_DOC_KEYWORDS = (
    "summary",
    "deliverable",
    "verification",
    "quick_reference",
    "implementation",
    "integration",
)
_LEGACY_COMMAND_PATTERNS = (
    "python3 scripts/energycrawler_cli.py",
    "python scripts/energycrawler_cli.py",
    "python3 scripts/energy_service_cli.py",
    "python scripts/energy_service_cli.py",
    "python3 scripts/auth_cli.py",
    "python scripts/auth_cli.py",
    ".venv/bin/python tests/e2e/run_xhs_x_crawl_flow.py",
)
_ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"/Users/[^\s\"']+"),
    re.compile(r"/private/var/folders/[^\s\"']+"),
)
_HYGIENE_IGNORE_FILES = {
    "tests/test_doc_tooling.py",
    "tools/cleanup_report.py",
}


def _git_ls_files(root: Path) -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    items = output.decode("utf-8", errors="ignore").split("\0")
    return [root / line for line in items if line.strip()]


def _build_corpus(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def _iter_text_file_lines(root: Path, tracked: list[Path]):
    for path in tracked:
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        for line_no, line in enumerate(content.splitlines(), start=1):
            yield rel, line_no, line


def _is_hygiene_ignored(rel_path: str) -> bool:
    return rel_path in _HYGIENE_IGNORE_FILES


def find_unreferenced_doc_images(root: Path, corpus: str) -> list[str]:
    images_dir = root / "docs" / "static" / "images"
    if not images_dir.exists():
        return []

    decoded_corpus = urllib.parse.unquote(corpus)
    candidates: list[str] = []
    for image_path in sorted(images_dir.glob("*")):
        if not image_path.is_file():
            continue
        rel_from_docs = image_path.relative_to(root / "docs").as_posix()
        checks = [
            image_path.name,
            rel_from_docs,
            image_path.relative_to(root).as_posix(),
            urllib.parse.quote(rel_from_docs),
            urllib.parse.quote(image_path.name),
        ]
        if not any(item in corpus or item in decoded_corpus for item in checks):
            candidates.append(image_path.relative_to(root).as_posix())
    return candidates


def find_stale_report_docs(root: Path, corpus: str, tracked: list[Path]) -> list[str]:
    candidates: list[str] = []
    for path in tracked:
        if path.suffix.lower() != ".md":
            continue
        name_lower = path.name.lower()
        if not any(keyword in name_lower for keyword in _STALE_DOC_KEYWORDS):
            continue
        rel = path.relative_to(root).as_posix()
        ref_count = corpus.count(rel) + corpus.count(path.name)
        if ref_count <= 1:
            candidates.append(rel)
    return sorted(set(candidates))


def find_legacy_command_usage(root: Path, tracked: list[Path]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel, line_no, line in _iter_text_file_lines(root, tracked):
        if _is_hygiene_ignored(rel):
            continue
        for pattern in _LEGACY_COMMAND_PATTERNS:
            if pattern in line:
                findings.append(
                    {
                        "file": rel,
                        "line": line_no,
                        "pattern": pattern,
                    }
                )
    return findings


def find_absolute_path_mentions(root: Path, tracked: list[Path]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel, line_no, line in _iter_text_file_lines(root, tracked):
        if _is_hygiene_ignored(rel):
            continue
        for pattern in _ABSOLUTE_PATH_PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(
                    {
                        "file": rel,
                        "line": line_no,
                        "match": match.group(0),
                    }
                )
    return findings


def find_trailing_whitespace(root: Path, tracked: list[Path]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel, line_no, line in _iter_text_file_lines(root, tracked):
        if _is_hygiene_ignored(rel):
            continue
        if line.rstrip(" \t") != line:
            findings.append(
                {
                    "file": rel,
                    "line": line_no,
                }
            )
    return findings


def generate_cleanup_report(root: Path) -> dict:
    tracked = _git_ls_files(root)
    corpus = _build_corpus(tracked)
    return {
        "root": str(root),
        "unreferenced_doc_images": find_unreferenced_doc_images(root, corpus),
        "stale_report_docs": find_stale_report_docs(root, corpus, tracked),
        "legacy_command_usage": find_legacy_command_usage(root, tracked),
        "absolute_path_mentions": find_absolute_path_mentions(root, tracked),
        "trailing_whitespace": find_trailing_whitespace(root, tracked),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report cleanup candidates")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = generate_cleanup_report(root)
    finding_keys = (
        "unreferenced_doc_images",
        "stale_report_docs",
        "legacy_command_usage",
        "absolute_path_mentions",
        "trailing_whitespace",
    )
    findings = [item for key in finding_keys for item in report[key]]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Cleanup report:")
        for key in finding_keys:
            items = report[key]
            print(f"- {key}: {len(items)}")
            for item in items:
                if isinstance(item, str):
                    print(f"  - {item}")
                    continue
                location = f"{item.get('file')}:{item.get('line')}"
                details = item.get("pattern") or item.get("match") or ""
                if details:
                    print(f"  - {location} ({details})")
                else:
                    print(f"  - {location}")

    if args.fail_on_findings and findings:
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
