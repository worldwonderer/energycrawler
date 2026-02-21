#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run XHS QR login flow via EnergyCrawler API.

Flow:
1) POST /api/auth/xhs/qr/session/start
2) POST /api/auth/xhs/qr/session/{session_id}/qrcode
3) GET  /api/auth/xhs/qr/session/{session_id}/status (poll)
4) POST /api/auth/xhs/qr/session/{session_id}/cancel (optional)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from energy_client.client import BrowserClient


def _request_json(client: httpx.Client, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
    response = client.request(method, url, **kwargs)
    body = response.text
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {url} failed [{response.status_code}]: {body[:400]}")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {url} returned invalid JSON: {body[:400]}") from exc


def _write_local_qr_page(qr_url: str, qr_id: str, session_id: str) -> Path:
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>XHS QR Login</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f5f5;
      color: #111;
    }}
    .wrap {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .card {{
      background: #fff;
      border-radius: 16px;
      padding: 20px;
      width: min(92vw, 420px);
      box-shadow: 0 8px 30px rgba(0,0,0,.12);
      text-align: center;
    }}
    #qrcode {{
      width: 320px;
      height: 320px;
      margin: 12px auto 10px;
      background: #fff;
      padding: 10px;
      border-radius: 12px;
      border: 1px solid #eee;
      box-sizing: border-box;
    }}
    .hint {{
      color: #666;
      font-size: 13px;
      line-height: 1.45;
    }}
    .mono {{
      font-family: ui-monospace, Menlo, Monaco, monospace;
      font-size: 12px;
      color: #999;
      word-break: break-all;
      margin-top: 6px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h2 style="margin: 0 0 8px;">小红书扫码登录</h2>
      <div class="hint">请用小红书 App 扫描下方二维码并确认登录</div>
      <div id="qrcode"></div>
      <div class="hint">扫码后脚本会自动轮询并写入 .env 的 COOKIES</div>
      <div class="mono">qr_id: {qr_id}</div>
      <div class="mono">session: {session_id}</div>
    </div>
  </div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
  <script>
    new QRCode(document.getElementById("qrcode"), {{
      text: {json.dumps(qr_url, ensure_ascii=False)},
      width: 300,
      height: 300,
      colorDark: "#000000",
      colorLight: "#ffffff",
      correctLevel: QRCode.CorrectLevel.M
    }});
  </script>
</body>
</html>
"""
    out = Path(tempfile.gettempdir()) / f"xhs_qr_login_{int(time.time() * 1000)}.html"
    out.write_text(page, encoding="utf-8")
    return out


def _open_qr_in_energy(
    host: str,
    port: int,
    browser_id: str,
    qr_url: str,
    session_id: str,
    qr_id: str,
    open_mode: str,
) -> tuple[int, str]:
    client = BrowserClient(host, port)
    client.connect()
    try:
        if open_mode == "qr":
            local_page = _write_local_qr_page(qr_url, qr_id=qr_id, session_id=session_id)
            target_url = local_page.resolve().as_uri()
        else:
            target_url = qr_url
        status = client.navigate(browser_id, target_url, timeout_ms=60000)
        return status, target_url
    finally:
        client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run XHS QR login flow from API")
    parser.add_argument("--api-base", default="http://localhost:8080", help="EnergyCrawler API base URL")
    parser.add_argument("--session-id", default="", help="Reuse an existing session id")
    parser.add_argument("--browser-id", default="", help="Browser id for reused session")
    parser.add_argument("--headless", action="store_true", help="Request headless browser for session start")
    parser.add_argument("--energy-host", default="localhost", help="Energy service host for opening QR")
    parser.add_argument("--energy-port", type=int, default=50051, help="Energy service port for opening QR")
    parser.add_argument(
        "--energy-open-mode",
        choices=["qr", "direct"],
        default="qr",
        help="Open a local QR display page (qr) or open XHS mobile login URL directly (direct)",
    )
    parser.add_argument(
        "--open-in-energy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open QR URL in the Energy browser window automatically",
    )
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds")
    parser.add_argument("--timeout-sec", type=float, default=180.0, help="Polling timeout in seconds")
    parser.add_argument(
        "--keep-session",
        action="store_true",
        help="Do not cancel session when flow exits",
    )
    parser.add_argument("--json", action="store_true", help="Print final JSON payload")
    args = parser.parse_args()

    base = args.api_base.rstrip("/")
    start_url = f"{base}/api/auth/xhs/qr/session/start"

    payload: Dict[str, Any] = {"success": False}
    session_id = args.session_id.strip()
    browser_id = args.browser_id.strip()
    qrcode_resp: Dict[str, Any]
    final_status: Dict[str, Any]

    with httpx.Client(timeout=30.0) as client:
        if not session_id:
            start_resp = _request_json(client, "POST", start_url, json={"headless": args.headless})
            session_id = str(start_resp.get("session_id", "")).strip()
            browser_id = str(start_resp.get("browser_id", "")).strip()
            if not session_id:
                raise RuntimeError(f"Missing session_id in start response: {start_resp}")
            print(f"[start] session_id={session_id} browser_id={browser_id}")
        else:
            print(f"[start] using existing session_id={session_id} browser_id={browser_id or '<unknown>'}")

        qrcode_url = f"{base}/api/auth/xhs/qr/session/{session_id}/qrcode"
        qrcode_resp = _request_json(client, "POST", qrcode_url)
        qr_url = qrcode_resp.get("qr_url", "")
        print(f"[qrcode] qr_id={qrcode_resp.get('qr_id')} code={qrcode_resp.get('code')}")
        print(f"[qrcode] scan_url={qr_url}")
        if args.open_in_energy and browser_id and qr_url:
            try:
                status, opened_url = _open_qr_in_energy(
                    args.energy_host,
                    args.energy_port,
                    browser_id,
                    qr_url,
                    session_id=session_id,
                    qr_id=str(qrcode_resp.get("qr_id", "")),
                    open_mode=args.energy_open_mode,
                )
                print(
                    f"[energy] opened {args.energy_open_mode} page in browser_id={browser_id} "
                    f"(status={status})"
                )
                if args.energy_open_mode == "direct":
                    print("[energy] this is direct mobile-login page, not QR image")
                else:
                    print(f"[energy] qr_display_url={opened_url}")
            except Exception as exc:
                print(f"[energy] failed to open QR page in Energy: {exc}")
        elif args.open_in_energy and not browser_id:
            print("[energy] skip auto-open because browser_id is unknown; provide --browser-id")

        status_url = f"{base}/api/auth/xhs/qr/session/{session_id}/status"
        started = time.monotonic()
        final_status = {}
        while True:
            final_status = _request_json(client, "GET", status_url)
            code_status = int(final_status.get("code_status", -1))
            login_success = bool(final_status.get("login_success", False))
            message = final_status.get("message", "")
            print(
                f"[status] code_status={code_status} login_success={login_success} "
                f"cookies={final_status.get('cookie_count', 0)} message={message}"
            )
            if login_success:
                payload = {
                    "success": True,
                    "session_id": session_id,
                    "qrcode": qrcode_resp,
                    "status": final_status,
                }
                break
            if time.monotonic() - started > args.timeout_sec:
                raise TimeoutError(
                    f"polling timeout after {args.timeout_sec:.1f}s, last_status={final_status}"
                )
            time.sleep(max(0.2, args.poll_interval))

        if not args.keep_session:
            cancel_url = f"{base}/api/auth/xhs/qr/session/{session_id}/cancel"
            cancel_resp = _request_json(client, "POST", cancel_url)
            print(f"[cancel] {cancel_resp.get('message', 'ok')}")
            payload["cancel"] = cancel_resp

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "[done] QR login success. COOKIES should be persisted to .env. "
            "You can verify with: uv run python scripts/check_login_state.py --skip-browser-check"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        raise SystemExit(1) from exc
