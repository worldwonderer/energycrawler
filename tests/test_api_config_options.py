# -*- coding: utf-8 -*-
"""Tests for /api/config/options payload."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app


def test_config_options_include_safety_profiles():
    client = TestClient(app)
    response = client.get("/api/config/options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    data = payload["data"]
    safety_values = [item["value"] for item in data["safety_profiles"]]
    assert safety_values == ["safe", "balanced", "aggressive"]
