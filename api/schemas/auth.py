# -*- coding: utf-8 -*-
"""Schemas for XHS QR login APIs."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class XhsQrSessionStartRequest(BaseModel):
    headless: Optional[bool] = Field(
        default=None,
        description="Optional override for Energy browser headless mode.",
    )


class XhsQrSessionStartResponse(BaseModel):
    success: bool = True
    session_id: str
    browser_id: str
    cookie_count: int


class XhsQrCreateResponse(BaseModel):
    success: bool = True
    session_id: str
    qr_url: str
    qr_id: str
    code: str
    expires_in_sec: int


class XhsQrStatusResponse(BaseModel):
    success: bool = True
    session_id: str
    code_status: int
    login_success: bool
    qr_id: Optional[str] = None
    cookie_count: int = 0
    login_info: Optional[dict] = None
    message: str = ""


class XhsQrCancelResponse(BaseModel):
    success: bool = True
    session_id: str
    message: str


class XhsEnergySyncRequest(BaseModel):
    browser_id: str = Field(
        default="manual_login_xhs",
        description="Existing Energy browser_id that already finished XHS login.",
    )
    verify_login: bool = Field(
        default=True,
        description="Whether to verify login status via XHS selfinfo API before persisting cookies.",
    )


class XhsEnergySyncResponse(BaseModel):
    success: bool = True
    browser_id: str
    login_success: bool
    cookie_count: int
    message: str
