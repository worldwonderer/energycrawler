# -*- coding: utf-8 -*-
"""Unit tests for CookieCloud runtime sync."""

from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from tools import cookiecloud_sync


def _enable_cookiecloud(monkeypatch) -> None:
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_ENABLED", True, raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_FORCE_SYNC", False, raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_SERVER", "http://127.0.0.1:8088", raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_UUID", "demo-uuid", raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_PASSWORD", "demo-password", raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_TIMEOUT_SEC", 5.0, raising=False)


def _pkcs7_pad(data: bytes) -> bytes:
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len]) * pad_len


def _encrypt_cookiecloud_payload(cookie_data: dict, uuid: str, password: str) -> str:
    payload = json.dumps({"cookie_data": cookie_data}, ensure_ascii=False).encode("utf-8")
    salt = b"12345678"
    key_iv = cookiecloud_sync._bytes_to_key(  # noqa: SLF001
        cookiecloud_sync._cookiecloud_key(uuid, password),  # noqa: SLF001
        salt,
        output=48,
    )
    key = key_iv[:32]
    iv = key_iv[32:]
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(_pkcs7_pad(payload)) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + ciphertext).decode("utf-8")


def test_sync_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_ENABLED", False, raising=False)
    result = cookiecloud_sync.sync_cookiecloud_login_state("x")
    assert result.skipped is True
    assert result.applied is False
    assert "disabled" in result.message.lower()


def test_sync_skips_when_required_settings_missing(monkeypatch):
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_ENABLED", True, raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIES", "", raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_SERVER", "", raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_UUID", "", raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_PASSWORD", "", raising=False)

    result = cookiecloud_sync.sync_cookiecloud_login_state("xhs")
    assert result.applied is False
    assert "missing" in result.message.lower()


def test_sync_skips_when_explicit_cookie_header_provided(monkeypatch):
    _enable_cookiecloud(monkeypatch)
    called = {"value": False}

    def _fake_fetch(*_args, **_kwargs):
        called["value"] = True
        return {}, "stub"

    monkeypatch.setattr(cookiecloud_sync, "_fetch_cookie_data", _fake_fetch, raising=False)

    result = cookiecloud_sync.sync_cookiecloud_login_state(
        "x",
        explicit_cookie_header="auth_token=from-request; ct0=from-request",
    )
    assert result.skipped is True
    assert called["value"] is False


def test_sync_x_applies_cookie_and_token_pair(monkeypatch):
    _enable_cookiecloud(monkeypatch)
    monkeypatch.setattr(cookiecloud_sync.config, "TWITTER_COOKIE", "", raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "TWITTER_AUTH_TOKEN", "", raising=False)
    monkeypatch.setattr(cookiecloud_sync.config, "TWITTER_CT0", "", raising=False)

    cookie_data = {
        "twitter.com": [
            {"domain": ".twitter.com", "name": "auth_token", "value": "auth-123"},
            {"domain": ".twitter.com", "name": "ct0", "value": "ct0-456"},
            {"domain": ".twitter.com", "name": "kdt", "value": "kdt-789"},
        ]
    }

    monkeypatch.setattr(
        cookiecloud_sync,
        "_fetch_cookie_data",
        lambda **_kwargs: (cookie_data, "stub"),
        raising=False,
    )

    result = cookiecloud_sync.sync_cookiecloud_login_state("x")
    assert result.applied is True
    assert result.cookie_count == 3
    assert cookiecloud_sync.config.TWITTER_AUTH_TOKEN == "auth-123"
    assert cookiecloud_sync.config.TWITTER_CT0 == "ct0-456"
    assert "auth_token=auth-123" in cookiecloud_sync.config.TWITTER_COOKIE


def test_sync_xhs_applies_cookie_header(monkeypatch):
    _enable_cookiecloud(monkeypatch)
    monkeypatch.setattr(cookiecloud_sync.config, "COOKIES", "", raising=False)

    cookie_data = {
        ".xiaohongshu.com": [
            {"domain": ".xiaohongshu.com", "name": "a1", "value": "a1-token"},
            {"domain": ".xiaohongshu.com", "name": "webId", "value": "web-id"},
        ]
    }

    monkeypatch.setattr(
        cookiecloud_sync,
        "_fetch_cookie_data",
        lambda **_kwargs: (cookie_data, "stub"),
        raising=False,
    )

    result = cookiecloud_sync.sync_cookiecloud_login_state("xhs")
    assert result.applied is True
    assert result.cookie_count == 2
    assert "a1=a1-token" in cookiecloud_sync.config.COOKIES


def test_sync_respects_force_sync(monkeypatch):
    _enable_cookiecloud(monkeypatch)
    monkeypatch.setattr(cookiecloud_sync.config, "TWITTER_COOKIE", "auth_token=old; ct0=old", raising=False)
    cookie_data = {
        ".x.com": [
            {"domain": ".x.com", "name": "auth_token", "value": "new-auth"},
            {"domain": ".x.com", "name": "ct0", "value": "new-ct0"},
        ]
    }
    monkeypatch.setattr(
        cookiecloud_sync,
        "_fetch_cookie_data",
        lambda **_kwargs: (cookie_data, "stub"),
        raising=False,
    )

    skipped = cookiecloud_sync.sync_cookiecloud_login_state("x")
    assert skipped.skipped is True
    assert "already present" in skipped.message.lower()
    assert cookiecloud_sync.config.TWITTER_AUTH_TOKEN != "new-auth"

    monkeypatch.setattr(cookiecloud_sync.config, "COOKIECLOUD_FORCE_SYNC", True, raising=False)
    forced = cookiecloud_sync.sync_cookiecloud_login_state("x")
    assert forced.applied is True
    assert cookiecloud_sync.config.TWITTER_AUTH_TOKEN == "new-auth"


def test_cookiecloud_decrypt_payload_supports_standard_format():
    cookie_data = {
        ".x.com": [
            {"domain": ".x.com", "name": "auth_token", "value": "abc"},
            {"domain": ".x.com", "name": "ct0", "value": "def"},
        ]
    }
    encrypted = _encrypt_cookiecloud_payload(cookie_data, "demo-uuid", "demo-password")
    decrypted = cookiecloud_sync._decrypt_cookiecloud_payload(encrypted, "demo-uuid", "demo-password")  # noqa: SLF001
    assert decrypted == cookie_data
