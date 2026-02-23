# -*- coding: utf-8 -*-
"""API tests for /api/config runtime snapshot."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from config import runtime_snapshot


def test_api_config_returns_sanitized_runtime_snapshot(monkeypatch):
    monkeypatch.setattr(runtime_snapshot.runtime_cfg, "PLATFORM", "xhs", raising=False)
    monkeypatch.setattr(runtime_snapshot.runtime_cfg, "CRAWLER_TYPE", "search", raising=False)
    monkeypatch.setattr(runtime_snapshot.runtime_cfg, "COOKIES", "a1=very-secret-cookie-value", raising=False)
    monkeypatch.setattr(runtime_snapshot.runtime_cfg, "TWITTER_AUTH_TOKEN", "twitter-secret-token", raising=False)
    monkeypatch.setattr(runtime_snapshot.runtime_cfg, "TWITTER_CT0", "", raising=False)
    monkeypatch.setattr(runtime_snapshot.runtime_cfg, "TWITTER_COOKIE", "", raising=False)
    monkeypatch.setattr(runtime_snapshot.db_config, "MYSQL_DB_PWD", "mysql-secret-password", raising=False)

    client = TestClient(app)
    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Runtime config snapshot"

    data = payload["data"]
    assert data["runtime"]["platform"] == "xhs"
    assert data["runtime"]["crawler_type"] == "search"

    xhs_cookie = data["auth"]["xhs_cookie"]
    assert xhs_cookie["configured"] is True
    assert xhs_cookie["masked"] != "a1=very-secret-cookie-value"
    assert "very-secret-cookie-value" not in xhs_cookie["masked"]

    twitter_auth_token = data["auth"]["twitter_auth_token"]
    assert twitter_auth_token["configured"] is True
    assert "twitter-secret-token" not in twitter_auth_token["masked"]

    twitter_ct0 = data["auth"]["twitter_ct0"]
    assert twitter_ct0 == {"configured": False, "masked": ""}

    mysql_password = data["storage"]["mysql"]["password"]
    assert mysql_password["configured"] is True
    assert "mysql-secret-password" not in mysql_password["masked"]


def test_api_config_openapi_includes_description_and_example():
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    operation = schema["paths"]["/api/config"]["get"]

    assert "sensitive fields" in operation["description"].lower()
    example = operation["responses"]["200"]["content"]["application/json"]["example"]
    assert example["success"] is True
    assert example["message"] == "Runtime config snapshot"
    assert "auth" in example["data"]
