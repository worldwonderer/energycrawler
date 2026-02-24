# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/api/routers/data.py
# GitHub: https://github.com/EnergyCrawler
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import json
import os
from csv import DictReader
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..response import success_response

router = APIRouter(prefix="/data", tags=["data"])

# Data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"
SUPPORTED_EXTENSIONS = {".json", ".csv", ".xlsx", ".xls"}
PREVIEW_SUPPORTED_EXTENSIONS = {".json", ".csv", ".xlsx", ".xls"}
SUPPORTED_FILE_TYPES = ", ".join(ext[1:] for ext in sorted(SUPPORTED_EXTENSIONS))
SUPPORTED_SORT_FIELDS = {"modified_at", "name", "size", "type", "record_count"}
SUPPORTED_SORT_ORDERS = {"asc", "desc"}


def _resolve_platform_roots(platform: Optional[str]) -> Optional[set[str]]:
    if not platform:
        return None

    normalized = platform.strip().lower()
    if not normalized:
        return None

    if normalized in {"x", "twitter"}:
        return {"x", "twitter"}
    if normalized in {"xhs", "xiaohongshu"}:
        return {"xhs", "xiaohongshu"}
    return {normalized}


def _normalize_file_type(file_type: Optional[str]) -> Optional[str]:
    if not file_type:
        return None

    normalized = file_type.lower().lstrip(".")
    if f".{normalized}" not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{file_type}'. "
                f"Supported types: {SUPPORTED_FILE_TYPES}"
            ),
        )
    return normalized


def _iter_data_files(platform: Optional[str] = None, file_type: Optional[str] = None) -> list[Path]:
    normalized_file_type = _normalize_file_type(file_type)
    if not DATA_DIR.exists():
        return []

    files: list[Path] = []
    platform_roots = _resolve_platform_roots(platform)

    for root, _dirs, filenames in os.walk(DATA_DIR):
        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename
            suffix = file_path.suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                continue

            rel_parts = file_path.relative_to(DATA_DIR).parts
            rel_root = rel_parts[0].lower() if rel_parts else ""
            if platform_roots and rel_root not in platform_roots:
                continue

            if normalized_file_type and suffix[1:] != normalized_file_type:
                continue

            files.append(file_path)

    return files


def _normalize_sort_field(sort_by: str) -> str:
    normalized = (sort_by or "").strip().lower()
    if normalized not in SUPPORTED_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported sort field '{sort_by}'. "
                f"Supported fields: {', '.join(sorted(SUPPORTED_SORT_FIELDS))}"
            ),
        )
    return normalized


def _normalize_sort_order(sort_order: str) -> str:
    normalized = (sort_order or "").strip().lower()
    if normalized not in SUPPORTED_SORT_ORDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported sort order '{sort_order}'. "
                f"Supported orders: {', '.join(sorted(SUPPORTED_SORT_ORDERS))}"
            ),
        )
    return normalized


def _sort_files(files: list[dict], *, sort_by: str, sort_order: str) -> None:
    reverse = sort_order == "desc"
    if sort_by in {"name", "type"}:
        files.sort(key=lambda x: str(x.get(sort_by, "")).lower(), reverse=reverse)
        return

    files.sort(
        key=lambda x: float(x.get(sort_by, -1) if x.get(sort_by) is not None else -1),
        reverse=reverse,
    )


def _parse_date_bound(value: Optional[str], *, is_end: bool) -> Optional[datetime]:
    if value is None:
        return None

    raw = value.strip()
    if not raw:
        return None

    try:
        if len(raw) == 10:
            parsed = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if is_end:
                return parsed + timedelta(days=1) - timedelta(microseconds=1)
            return parsed

        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid date value '{value}'. "
                "Use YYYY-MM-DD or ISO-8601 datetime."
            ),
        ) from exc


def _infer_platform_bucket(file_path: Path) -> Optional[str]:
    rel_path = str(file_path.relative_to(DATA_DIR)).lower()
    for platform in ["xhs", "x", "twitter"]:
        if platform in rel_path:
            return platform
    return None


def _resolve_safe_file_path(file_path: str) -> Path:
    full_path = (DATA_DIR / file_path).resolve()

    # Security check: ensure within DATA_DIR
    try:
        full_path.relative_to(DATA_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    return full_path


def _find_latest_file(platform: Optional[str] = None, file_type: Optional[str] = None) -> Path:
    files = _iter_data_files(platform=platform, file_type=file_type)
    if not files:
        filters = []
        if platform:
            filters.append(f"platform={platform}")
        if file_type:
            filters.append(f"file_type={file_type}")
        filter_msg = f" for filters ({', '.join(filters)})" if filters else ""
        raise HTTPException(status_code=404, detail=f"No data files found{filter_msg}")

    return max(files, key=lambda p: p.stat().st_mtime)


def _preview_file(full_path: Path, limit: int = 100) -> dict:
    suffix = full_path.suffix.lower()
    if suffix not in PREVIEW_SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Preview not supported for file type: {suffix.lstrip('.') or 'unknown'}",
        )

    try:
        if suffix == ".json":
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {"data": data[:limit], "total": len(data)}
                return {"data": data, "total": 1}

        if suffix == ".csv":
            with open(full_path, "r", encoding="utf-8") as f:
                reader = DictReader(f)
                rows = []
                for i, row in enumerate(reader):
                    if i >= limit:
                        break
                    rows.append(row)

            with open(full_path, "r", encoding="utf-8") as f:
                total = max(sum(1 for _ in f) - 1, 0)
            return {"data": rows, "total": total}

        # xlsx/xls
        df = pd.read_excel(full_path, nrows=limit)
        df_count = pd.read_excel(full_path, usecols=[0])
        total = len(df_count)
        rows = df.where(pd.notnull(df), None).to_dict(orient="records")
        return {
            "data": rows,
            "total": total,
            "columns": list(df.columns),
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _download_file(full_path: Path) -> FileResponse:
    return FileResponse(
        path=full_path,
        filename=full_path.name,
        media_type="application/octet-stream",
    )


def get_file_info(file_path: Path) -> dict:
    """Get file information"""
    stat = file_path.stat()
    record_count = None

    # Try to get record count
    try:
        if file_path.suffix.lower() == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    record_count = len(data)
                else:
                    record_count = 1
        elif file_path.suffix.lower() == ".csv":
            with open(file_path, "r", encoding="utf-8") as f:
                record_count = max(sum(1 for _ in f) - 1, 0)
    except Exception:
        pass

    return {
        "name": file_path.name,
        "path": str(file_path.relative_to(DATA_DIR)),
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "record_count": record_count,
        "type": file_path.suffix[1:] if file_path.suffix else "unknown",
    }


@router.get("/files")
async def list_data_files(
    platform: Optional[str] = None,
    file_type: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: Optional[int] = Query(default=None, ge=1, le=1000),
    sort_by: str = Query(default="modified_at"),
    sort_order: str = Query(default="desc"),
):
    """Get data file list"""
    files = []
    for file_path in _iter_data_files(platform=platform, file_type=file_type):
        try:
            files.append(get_file_info(file_path))
        except Exception:
            continue

    normalized_sort_by = _normalize_sort_field(sort_by)
    normalized_sort_order = _normalize_sort_order(sort_order)
    _sort_files(files, sort_by=normalized_sort_by, sort_order=normalized_sort_order)

    total = len(files)
    if page_size is None:
        paged_files = files
        total_pages = 1 if total > 0 else 0
    else:
        offset = (page - 1) * page_size
        paged_files = files[offset:offset + page_size]
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return success_response(
        {
            "files": paged_files,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "sort_by": normalized_sort_by,
            "sort_order": normalized_sort_order,
        },
        message="Data files",
    )


@router.get("/latest")
async def get_latest_file(
    platform: Optional[str] = None,
    file_type: Optional[str] = None,
    preview: bool = True,
    limit: int = Query(default=100, ge=1),
):
    """Get latest file preview or download"""
    latest_file = _find_latest_file(platform=platform, file_type=file_type)
    if not preview:
        return _download_file(latest_file)

    payload = _preview_file(latest_file, limit=limit)
    payload["file"] = get_file_info(latest_file)
    return success_response(payload, message="Latest file preview")


@router.get("/latest/download")
async def download_latest_file(platform: Optional[str] = None, file_type: Optional[str] = None):
    """Download latest file"""
    latest_file = _find_latest_file(platform=platform, file_type=file_type)
    return _download_file(latest_file)


@router.get("/files/{file_path:path}")
async def get_file_content(file_path: str, preview: bool = True, limit: int = Query(default=100, ge=1)):
    """Get file content or preview"""
    full_path = _resolve_safe_file_path(file_path)

    if preview:
        return success_response(_preview_file(full_path, limit=limit), message="File preview")

    return _download_file(full_path)


@router.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """Download file"""
    full_path = _resolve_safe_file_path(file_path)
    return _download_file(full_path)


@router.get("/stats")
async def get_data_stats(
    platform: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    from_param: Optional[str] = Query(default=None, alias="from"),
    to_param: Optional[str] = Query(default=None, alias="to"),
):
    """Get data statistics"""
    effective_date_from = date_from or from_param
    effective_date_to = date_to or to_param

    start_dt = _parse_date_bound(effective_date_from, is_end=False)
    end_dt = _parse_date_bound(effective_date_to, is_end=True)
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=400, detail="date_from must be less than or equal to date_to")

    if not DATA_DIR.exists():
        return success_response(
            {
                "total_files": 0,
                "total_size": 0,
                "by_platform": {},
                "by_type": {},
                "by_date": {},
                "filters": {
                    "platform": platform,
                    "date_from": effective_date_from,
                    "date_to": effective_date_to,
                },
            },
            message="Data statistics",
        )

    stats = {
        "total_files": 0,
        "total_size": 0,
        "by_platform": {},
        "by_type": {},
        "by_date": {},
        "filters": {
            "platform": platform,
            "date_from": effective_date_from,
            "date_to": effective_date_to,
        },
    }

    for file_path in _iter_data_files(platform=platform):
        try:
            stat = file_path.stat()
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if start_dt and modified_at < start_dt:
                continue
            if end_dt and modified_at > end_dt:
                continue

            stats["total_files"] += 1
            stats["total_size"] += stat.st_size

            file_type = file_path.suffix[1:].lower()
            stats["by_type"][file_type] = stats["by_type"].get(file_type, 0) + 1

            platform_bucket = _infer_platform_bucket(file_path)
            if platform_bucket:
                stats["by_platform"][platform_bucket] = stats["by_platform"].get(platform_bucket, 0) + 1

            date_bucket = modified_at.date().isoformat()
            stats["by_date"][date_bucket] = stats["by_date"].get(date_bucket, 0) + 1
        except Exception:
            continue

    return success_response(stats, message="Data statistics")
