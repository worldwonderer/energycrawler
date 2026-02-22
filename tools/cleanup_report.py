#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate cleanup candidates for docs/static assets."""

from __future__ import annotations

import argparse
import json
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


def generate_cleanup_report(root: Path) -> dict:
    tracked = _git_ls_files(root)
    corpus = _build_corpus(tracked)
    return {
        "root": str(root),
        "unreferenced_doc_images": find_unreferenced_doc_images(root, corpus),
        "stale_report_docs": find_stale_report_docs(root, corpus, tracked),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report cleanup candidates")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = generate_cleanup_report(root)
    findings = report["unreferenced_doc_images"] + report["stale_report_docs"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Cleanup report:")
        print(f"- unreferenced doc images: {len(report['unreferenced_doc_images'])}")
        for item in report["unreferenced_doc_images"]:
            print(f"  - {item}")
        print(f"- stale report docs: {len(report['stale_report_docs'])}")
        for item in report["stale_report_docs"]:
            print(f"  - {item}")

    if args.fail_on_findings and findings:
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
