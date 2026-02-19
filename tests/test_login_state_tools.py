# -*- coding: utf-8 -*-
"""
Unit tests for login-state helper functions.
"""

import scripts.check_login_state as login_state


def test_parse_cookie_header_extracts_pairs():
    cookie_map = login_state.parse_cookie_header("a=1; b=2; c=3")
    assert cookie_map["a"] == "1"
    assert cookie_map["b"] == "2"
    assert cookie_map["c"] == "3"


def test_check_x_env_state_uses_cookie_fallback(monkeypatch):
    monkeypatch.setattr(login_state.config, "TWITTER_COOKIE", "auth_token=aaa; ct0=bbb", raising=False)
    monkeypatch.setattr(login_state.config, "TWITTER_AUTH_TOKEN", "", raising=False)
    monkeypatch.setattr(login_state.config, "TWITTER_CT0", "", raising=False)
    ok, message = login_state.check_x_env_state()
    assert ok is True
    assert "auth_token + ct0" in message


def test_check_xhs_env_state_requires_a1(monkeypatch):
    monkeypatch.setattr(login_state.config, "COOKIES", "webId=abc", raising=False)
    ok, message = login_state.check_xhs_env_state()
    assert ok is False
    assert "missing a1" in message

    monkeypatch.setattr(login_state.config, "COOKIES", "webId=abc; a1=token", raising=False)
    ok, message = login_state.check_xhs_env_state()
    assert ok is True
    assert "a1 found" in message
