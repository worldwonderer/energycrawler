# -*- coding: utf-8 -*-
"""Helpers for updating key/value pairs in a .env file."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict


def quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def upsert_env_values(env_path: Path, updates: Dict[str, str]) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated_keys = set()

    for i, line in enumerate(lines):
        for key, value in updates.items():
            if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                lines[i] = f"{key}={quote_env_value(value)}"
                updated_keys.add(key)

    for key, value in updates.items():
        if key not in updated_keys:
            lines.append(f"{key}={quote_env_value(value)}")

    content = "\n".join(lines).strip()
    env_path.write_text((content + "\n") if content else "", encoding="utf-8")
