# -*- coding: utf-8 -*-
"""Auth routers for XHS QR login flow."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from ..schemas.auth import (
    XhsQrSessionStartRequest,
    XhsQrSessionStartResponse,
    XhsQrCreateResponse,
    XhsQrStatusResponse,
    XhsQrCancelResponse,
    XhsEnergySyncRequest,
    XhsEnergySyncResponse,
)
from ..services import qr_auth_service
from ..services.xhs_qr_auth_service import XhsQrAuthError, XhsQrSessionNotFoundError


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/xhs/qr/session/start", response_model=XhsQrSessionStartResponse)
async def start_xhs_qr_session(
    request: Optional[XhsQrSessionStartRequest] = None,
):
    try:
        return await qr_auth_service.start_session(
            headless=request.headless if request else None
        )
    except XhsQrAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/xhs/qr/session/{session_id}/qrcode", response_model=XhsQrCreateResponse)
async def create_xhs_qrcode(session_id: str):
    try:
        return await qr_auth_service.create_qrcode(session_id)
    except XhsQrSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except XhsQrAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/xhs/qr/session/{session_id}/status", response_model=XhsQrStatusResponse)
async def poll_xhs_qr_status(session_id: str):
    try:
        return await qr_auth_service.poll_status(session_id)
    except XhsQrSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except XhsQrAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/xhs/qr/session/{session_id}/cancel", response_model=XhsQrCancelResponse)
async def cancel_xhs_qr_session(session_id: str):
    try:
        return await qr_auth_service.cancel_session(session_id)
    except XhsQrSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/xhs/energy/sync", response_model=XhsEnergySyncResponse)
async def sync_xhs_energy_login(request: XhsEnergySyncRequest):
    try:
        return await qr_auth_service.sync_from_energy_browser(
            browser_id=request.browser_id,
            verify_login=request.verify_login,
        )
    except XhsQrAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
