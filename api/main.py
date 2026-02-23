# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Repository: https://github.com/EnergyCrawler/EnergyCrawler/blob/main/api/main.py
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

"""
EnergyCrawler API Server
Start command: uvicorn api.main:app --port 8080 --reload
Or: python -m api.main
"""
import asyncio
from pathlib import Path
import subprocess

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.runtime_snapshot import API_CONFIG_RESPONSE_EXAMPLE, build_public_runtime_config

from .routers import crawler_router, data_router, websocket_router, auth_router
from .response import ApiError, error_response, status_to_error_code, success_response
from .schemas import SaveDataOptionEnum

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_CHECK_TIMEOUT_SECONDS = 30.0
ENV_CHECK_OUTPUT_LIMIT = 500
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
SAVE_OPTION_LABELS = {
    SaveDataOptionEnum.JSON.value: "JSON File",
    SaveDataOptionEnum.CSV.value: "CSV File",
    SaveDataOptionEnum.EXCEL.value: "Excel File",
    SaveDataOptionEnum.SQLITE.value: "SQLite Database",
    SaveDataOptionEnum.DB.value: "MySQL Database",
    SaveDataOptionEnum.MONGODB.value: "MongoDB Database",
    SaveDataOptionEnum.POSTGRES.value: "PostgreSQL Database",
}

app = FastAPI(
    title="EnergyCrawler API",
    description="API for controlling EnergyCrawler tasks and auth flows",
    version="1.0.0",
)

# CORS configuration - allow frontend dev server access
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(crawler_router, prefix="/api")
app.include_router(data_router, prefix="/api")
app.include_router(websocket_router, prefix="/api")
app.include_router(auth_router, prefix="/api")


@app.exception_handler(ApiError)
async def handle_api_error(_request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.code, exc.message, details=exc.details),
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(_request: Request, exc: HTTPException):
    message = "Request failed"
    details = None
    code = status_to_error_code(exc.status_code)

    if isinstance(exc.detail, dict):
        message = str(exc.detail.get("message") or exc.detail.get("error") or message)
        details = exc.detail.get("details")
        if isinstance(exc.detail.get("code"), str):
            code = exc.detail["code"]
    elif isinstance(exc.detail, list):
        message = "Request failed"
        details = exc.detail
    elif exc.detail is not None:
        message = str(exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(code, message, details=details),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_response(
            "VALIDATION_ERROR",
            "Request validation failed",
            details=exc.errors(),
        ),
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(_request: Request, _exc: Exception):
    return JSONResponse(
        status_code=500,
        content=error_response("INTERNAL_ERROR", "Internal server error"),
    )


@app.get("/")
async def root():
    """API root endpoint."""
    return success_response(
        {
            "service": "EnergyCrawler API",
            "version": "1.0.0",
            "docs": "/docs",
        },
        message="Service info",
    )


@app.get("/api/health")
async def health_check():
    return success_response({"status": "ok"}, message="Service healthy")


def _truncate_output(value: str) -> str:
    return value[:ENV_CHECK_OUTPUT_LIMIT]


@app.get("/api/env/check")
async def check_environment():
    """Check if EnergyCrawler environment is configured correctly"""
    try:
        process = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "main.py",
            "--help",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=ENV_CHECK_TIMEOUT_SECONDS,
        )

        stdout_text = stdout.decode("utf-8", errors="ignore")
        stderr_text = stderr.decode("utf-8", errors="ignore")
        if process.returncode == 0:
            return success_response(
                {
                    "output": _truncate_output(stdout_text),
                },
                message="EnergyCrawler environment configured correctly",
            )

        error_msg = stderr_text or stdout_text
        raise ApiError(
            status_code=500,
            code="ENV_CHECK_FAILED",
            message="Environment check failed",
            details=_truncate_output(error_msg),
        )
    except asyncio.TimeoutError:
        raise ApiError(
            status_code=504,
            code="ENV_CHECK_TIMEOUT",
            message="Environment check timeout",
            details=f"Command execution exceeded {int(ENV_CHECK_TIMEOUT_SECONDS)} seconds",
        )
    except FileNotFoundError:
        raise ApiError(
            status_code=500,
            code="UV_NOT_FOUND",
            message="uv command not found",
            details="Please ensure uv is installed and configured in system PATH",
        )
    except ApiError:
        raise
    except Exception as e:
        raise ApiError(
            status_code=500,
            code="ENV_CHECK_ERROR",
            message="Environment check error",
            details=str(e),
        ) from e


@app.get("/api/config/platforms")
async def get_platforms():
    """Get list of supported platforms"""
    return success_response({
        "platforms": [
            {"value": "xhs", "label": "Xiaohongshu", "icon": "book-open"},
            {"value": "x", "label": "X (Twitter)", "icon": "message-circle"},
        ]
    }, message="Supported platforms")


@app.get(
    "/api/config",
    summary="Get runtime config snapshot (sanitized)",
    description=(
        "Return effective runtime configuration used by the API/crawler. "
        "Sensitive fields (cookies/tokens/passwords) are masked and never exposed in plaintext."
    ),
    responses={
        200: {
            "description": "Sanitized runtime configuration snapshot",
            "content": {
                "application/json": {
                    "example": success_response(
                        API_CONFIG_RESPONSE_EXAMPLE,
                        message="Runtime config snapshot",
                    )
                }
            },
        }
    },
)
async def get_runtime_config():
    """Get sanitized runtime configuration snapshot."""
    return success_response(
        build_public_runtime_config(),
        message="Runtime config snapshot",
    )


@app.get("/api/config/options")
async def get_config_options():
    """Get all configuration options"""
    return success_response({
        "login_types": [
            {"value": "cookie", "label": "Cookie Login"},
        ],
        "crawler_types": [
            {"value": "search", "label": "Search Mode"},
            {"value": "detail", "label": "Detail Mode"},
            {"value": "creator", "label": "Creator Mode"},
        ],
        "save_options": [
            {"value": option.value, "label": SAVE_OPTION_LABELS[option.value]}
            for option in SaveDataOptionEnum
        ],
    }, message="Config options")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
