#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XHS signature runtime probe.

Checks whether `window.mnsv2` is available and compares runtime traits
against an optional local baseline file.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from energy_client.browser_interface import EnergyBrowserBackend


XHS_HOME_URL = "https://www.xiaohongshu.com/"
DEFAULT_BASELINE = PROJECT_ROOT / "data" / "xhs" / "signature_runtime_baseline.json"


@dataclass
class ProbeCheck:
    name: str
    ok: bool
    detail: str


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_baseline(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"baseline file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid baseline JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"baseline must be a JSON object: {path}")
    return data


def _execute_js_safe(backend: EnergyBrowserBackend, browser_id: str, script: str) -> Tuple[Any, str]:
    try:
        return backend.execute_js(browser_id, script), ""
    except Exception as exc:
        return None, str(exc)


def collect_runtime_probe(
    backend: EnergyBrowserBackend,
    browser_id: str,
    timeout_ms: int = 60000,
    required_globals: Optional[List[str]] = None,
    required_localstorage_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    required_globals = required_globals or ["mnsv2"]
    required_localstorage_keys = required_localstorage_keys or ["b1"]

    status_code = backend.navigate(browser_id, XHS_HOME_URL, timeout_ms=timeout_ms)

    runtime_script = """(() => {
      const out = {
        mnsv2_type: "undefined",
        mnsv2_source_length: 0,
        current_url: "",
        user_agent: "",
      };
      if (typeof window === "undefined") {
        return out;
      }
      out.mnsv2_type = typeof window.mnsv2;
      out.mnsv2_source_length = out.mnsv2_type === "function" ? String(window.mnsv2).length : 0;
      out.current_url = window.location ? window.location.href : "";
      out.user_agent = window.navigator ? window.navigator.userAgent : "";
      return out;
    })()"""
    runtime_data, runtime_error = _execute_js_safe(backend, browser_id, runtime_script)
    runtime_data = runtime_data if isinstance(runtime_data, dict) else {}

    presence_script = f"""(() => {{
      const globals = {json.dumps(required_globals)};
      const localStorageKeys = {json.dumps(required_localstorage_keys)};
      const out = {{ globals: {{}}, local_storage: {{}} }};
      for (const key of globals) {{
        out.globals[key] = typeof window !== "undefined" && typeof window[key] !== "undefined";
      }}
      for (const key of localStorageKeys) {{
        try {{
          out.local_storage[key] = typeof window !== "undefined" &&
            !!window.localStorage &&
            window.localStorage.getItem(key) !== null;
        }} catch (_) {{
          out.local_storage[key] = false;
        }}
      }}
      return out;
    }})()"""
    presence_data, presence_error = _execute_js_safe(backend, browser_id, presence_script)
    presence_data = presence_data if isinstance(presence_data, dict) else {}

    probe = {
        "status_code": status_code,
        "mnsv2_type": runtime_data.get("mnsv2_type", "undefined"),
        "mnsv2_source_length": _safe_int(runtime_data.get("mnsv2_source_length"), 0),
        "current_url": runtime_data.get("current_url", ""),
        "user_agent": runtime_data.get("user_agent", ""),
        "global_presence": presence_data.get("globals", {}),
        "local_storage_presence": presence_data.get("local_storage", {}),
        "errors": [e for e in [runtime_error, presence_error] if e],
    }
    return probe


def evaluate_probe(
    probe: Dict[str, Any],
    baseline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    baseline = baseline or {}
    checks: List[ProbeCheck] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append(ProbeCheck(name=name, ok=ok, detail=detail))

    status_code = _safe_int(probe.get("status_code"), 0)
    add("navigate_status", status_code == 200, f"status_code={status_code}")

    mnsv2_type = str(probe.get("mnsv2_type", "undefined"))
    add("mnsv2_type", mnsv2_type == "function", f"typeof window.mnsv2={mnsv2_type}")

    source_len = _safe_int(probe.get("mnsv2_source_length"), 0)
    add("mnsv2_source_length", source_len > 0, f"String(window.mnsv2).length={source_len}")

    required_globals = baseline.get("required_globals", [])
    global_presence = probe.get("global_presence") or {}
    for key in required_globals:
        add(
            f"baseline.global.{key}",
            bool(global_presence.get(key)),
            f"present={bool(global_presence.get(key))}",
        )

    required_ls_keys = baseline.get("required_localstorage_keys", [])
    local_storage_presence = probe.get("local_storage_presence") or {}
    for key in required_ls_keys:
        add(
            f"baseline.local_storage.{key}",
            bool(local_storage_presence.get(key)),
            f"present={bool(local_storage_presence.get(key))}",
        )

    expected_type = baseline.get("mnsv2_type")
    if expected_type:
        add(
            "baseline.mnsv2_type",
            mnsv2_type == expected_type,
            f"actual={mnsv2_type}, expected={expected_type}",
        )

    min_len = _safe_int(baseline.get("mnsv2_min_source_length"), 0)
    if min_len > 0:
        add(
            "baseline.mnsv2_min_source_length",
            source_len >= min_len,
            f"actual={source_len}, expected_min={min_len}",
        )

    errors = probe.get("errors") or []
    add("probe_errors", len(errors) == 0, f"errors={len(errors)}")

    return {
        "healthy": all(item.ok for item in checks),
        "checks": [asdict(item) for item in checks],
    }


def run_probe(
    host: str,
    port: int,
    timeout_sec: float,
    browser_id: Optional[str],
    headless: bool,
    baseline: Optional[Dict[str, Any]],
    keep_browser: bool,
) -> Dict[str, Any]:
    use_browser_id = browser_id or f"xhs_signature_probe_{uuid.uuid4().hex[:10]}"
    backend = EnergyBrowserBackend(host=host, port=port)
    created = False

    required_globals = sorted(set(["mnsv2", *(baseline or {}).get("required_globals", [])]))
    required_ls_keys = sorted(set(["b1", *((baseline or {}).get("required_localstorage_keys", []))]))

    try:
        backend.connect()
        created = backend.create_browser(use_browser_id, headless=headless)
        probe = collect_runtime_probe(
            backend=backend,
            browser_id=use_browser_id,
            timeout_ms=int(timeout_sec * 1000),
            required_globals=required_globals,
            required_localstorage_keys=required_ls_keys,
        )
    finally:
        if created and not keep_browser:
            try:
                backend.close_browser(use_browser_id)
            except Exception:
                pass
        try:
            backend.disconnect()
        except Exception:
            pass

    evaluation = evaluate_probe(probe, baseline)
    return {
        "host": host,
        "port": port,
        "browser_id": use_browser_id,
        "headless": headless,
        "created_browser": created,
        "probe": probe,
        "evaluation": evaluation,
        "healthy": evaluation["healthy"],
    }


def print_human(payload: Dict[str, Any]) -> None:
    probe = payload["probe"]
    evaluation = payload["evaluation"]
    print(f"browser_id={payload['browser_id']} created={payload['created_browser']}")
    print(f"navigate_status={probe.get('status_code')} mnsv2_type={probe.get('mnsv2_type')}")
    print(f"mnsv2_source_length={probe.get('mnsv2_source_length')}")
    for item in evaluation["checks"]:
        prefix = "OK" if item["ok"] else "FAIL"
        print(f"[{prefix}] {item['name']}: {item['detail']}")
    print("Signature runtime healthy." if payload["healthy"] else "Signature runtime unhealthy.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check XHS signature runtime health")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--timeout", type=float, default=8.0, help="Navigation timeout in seconds")
    parser.add_argument("--browser-id", default="", help="Reuse browser id (optional)")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--skip-baseline", action="store_true")
    parser.set_defaults(headless=True)
    head_mode = parser.add_mutually_exclusive_group()
    head_mode.add_argument("--headless", dest="headless", action="store_true", help="Run browser in headless mode")
    head_mode.add_argument("--headed", dest="headless", action="store_false", help="Run browser with GUI")
    parser.add_argument("--keep-browser", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    baseline_data: Optional[Dict[str, Any]] = None
    baseline_path = Path(args.baseline).resolve() if args.baseline else None
    if not args.skip_baseline and baseline_path is not None:
        baseline_data = load_baseline(baseline_path)

    payload = run_probe(
        host=args.host,
        port=args.port,
        timeout_sec=args.timeout,
        browser_id=args.browser_id or None,
        headless=args.headless,
        baseline=baseline_data,
        keep_browser=args.keep_browser,
    )
    payload["baseline_path"] = str(baseline_path) if baseline_path else ""
    payload["baseline_loaded"] = baseline_data is not None

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)

    if not payload["healthy"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
