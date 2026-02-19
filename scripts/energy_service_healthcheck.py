#!/usr/bin/env python3
"""
Energy service health check:
1) TCP listener check
2) gRPC probe by create/close browser
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

import grpc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from energy_client import browser_pb2, browser_pb2_grpc


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str
    duration_ms: int


def check_tcp_listener(host: str, port: int, timeout: float) -> StepResult:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        ok = True
        detail = f"TCP listener reachable at {host}:{port}"
    except OSError as exc:
        ok = False
        detail = f"TCP listener unreachable at {host}:{port}: {exc}"
    duration_ms = int((time.monotonic() - started) * 1000)
    return StepResult(name="tcp_listener", ok=ok, detail=detail, duration_ms=duration_ms)


def _format_rpc_error(exc: grpc.RpcError) -> str:
    code = exc.code().name if exc.code() else "UNKNOWN"
    details = exc.details() or str(exc)
    return f"RPC error ({code}): {details}"


def check_grpc_probe(host: str, port: int, timeout: float) -> StepResult:
    started = time.monotonic()
    addr = f"{host}:{port}"
    browser_id = f"healthcheck_{uuid.uuid4().hex[:12]}"
    channel = grpc.insecure_channel(
        addr,
        options=[("grpc.enable_http_proxy", 0)],
    )
    created = False
    detail = ""
    ok = False

    try:
        grpc.channel_ready_future(channel).result(timeout=timeout)
        stub = browser_pb2_grpc.BrowserServiceStub(channel)

        create_resp = stub.CreateBrowser(
            browser_pb2.CreateBrowserRequest(browser_id=browser_id, headless=True),
            timeout=timeout,
        )
        if not create_resp.success:
            detail = f"CreateBrowser failed: {create_resp.error or 'success=false'}"
            return StepResult(
                name="grpc_probe",
                ok=False,
                detail=detail,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        created = True

        close_resp = stub.CloseBrowser(
            browser_pb2.CloseBrowserRequest(browser_id=browser_id),
            timeout=timeout,
        )
        if not close_resp.success:
            detail = f"CloseBrowser failed: {close_resp.error or 'success=false'}"
            ok = False
        else:
            ok = True
            detail = "gRPC probe passed: CreateBrowser + CloseBrowser succeeded"
    except grpc.FutureTimeoutError:
        detail = f"gRPC channel not ready within {timeout:.1f}s"
    except grpc.RpcError as exc:
        detail = _format_rpc_error(exc)
    except Exception as exc:  # pragma: no cover - defensive fallback
        detail = f"Unexpected probe error: {exc}"
    finally:
        if created and not ok:
            try:
                stub = browser_pb2_grpc.BrowserServiceStub(channel)
                stub.CloseBrowser(
                    browser_pb2.CloseBrowserRequest(browser_id=browser_id),
                    timeout=timeout,
                )
            except Exception:
                pass
        channel.close()

    duration_ms = int((time.monotonic() - started) * 1000)
    return StepResult(name="grpc_probe", ok=ok, detail=detail, duration_ms=duration_ms)


def build_payload(host: str, port: int, timeout: float, steps: List[StepResult]) -> dict:
    return {
        "host": host,
        "port": port,
        "timeout_sec": timeout,
        "healthy": all(step.ok for step in steps),
        "steps": [asdict(step) for step in steps],
    }


def print_human(payload: dict) -> None:
    for step in payload["steps"]:
        prefix = "OK" if step["ok"] else "FAIL"
        print(f"[{prefix}] {step['name']}: {step['detail']} ({step['duration_ms']}ms)")

    if payload["healthy"]:
        print("Health check passed.")
        return

    port = payload["port"]
    print("Health check failed.")
    print("Troubleshooting:")
    print(f"1) bash energy-service/start-macos.sh")
    print(f"2) bash scripts/ensure_energy_service.sh --port {port}")
    print(f"3) lsof -nP -iTCP:{port} -sTCP:LISTEN")


def main() -> None:
    parser = argparse.ArgumentParser(description="Health-check Energy gRPC service")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Per-step timeout seconds",
    )
    parser.add_argument("--skip-grpc-probe", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    steps = [check_tcp_listener(args.host, args.port, args.timeout)]
    if not args.skip_grpc_probe:
        steps.append(check_grpc_probe(args.host, args.port, args.timeout))

    payload = build_payload(args.host, args.port, args.timeout, steps)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)

    if not payload["healthy"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
