# -*- coding: utf-8 -*-
"""Unit tests for XHS signature runtime probe helpers."""

from __future__ import annotations

import json

import pytest

import scripts.check_xhs_signature_runtime as runtime_probe


def test_load_baseline_success(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"mnsv2_type": "function", "mnsv2_min_source_length": 1}),
        encoding="utf-8",
    )
    baseline = runtime_probe.load_baseline(baseline_path)
    assert baseline["mnsv2_type"] == "function"


def test_load_baseline_invalid_json(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError):
        runtime_probe.load_baseline(baseline_path)


def test_evaluate_probe_success_with_baseline():
    probe = {
        "status_code": 200,
        "mnsv2_type": "function",
        "mnsv2_source_length": 1234,
        "global_presence": {"mnsv2": True},
        "local_storage_presence": {"b1": True},
        "errors": [],
    }
    baseline = {
        "mnsv2_type": "function",
        "mnsv2_min_source_length": 10,
        "required_globals": ["mnsv2"],
        "required_localstorage_keys": ["b1"],
    }
    result = runtime_probe.evaluate_probe(probe, baseline)
    assert result["healthy"] is True


def test_evaluate_probe_detects_baseline_mismatch():
    probe = {
        "status_code": 200,
        "mnsv2_type": "undefined",
        "mnsv2_source_length": 0,
        "global_presence": {"mnsv2": False},
        "local_storage_presence": {"b1": False},
        "errors": ["Execute JS failed"],
    }
    baseline = {
        "mnsv2_type": "function",
        "mnsv2_min_source_length": 10,
        "required_globals": ["mnsv2"],
        "required_localstorage_keys": ["b1"],
    }
    result = runtime_probe.evaluate_probe(probe, baseline)
    assert result["healthy"] is False
    failed_checks = [item for item in result["checks"] if not item["ok"]]
    assert failed_checks
