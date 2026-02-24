# -*- coding: utf-8 -*-
"""Tests for command arg parsing edge cases."""

from __future__ import annotations

import pytest

import config
from cmd_arg.arg import parse_cmd


@pytest.mark.asyncio
async def test_parse_cmd_x_without_cookies_keeps_twitter_cookie(monkeypatch):
    monkeypatch.setattr(config, "COOKIES", "a1=xhs-cookie", raising=False)
    monkeypatch.setattr(config, "TWITTER_COOKIE", "auth_token=tok123; ct0=ct456", raising=False)
    monkeypatch.setattr(config, "TWITTER_AUTH_TOKEN", "tok123", raising=False)
    monkeypatch.setattr(config, "TWITTER_CT0", "ct456", raising=False)

    result = await parse_cmd(["--platform", "x", "--type", "search", "--keywords", "ai"])

    assert result.platform == "x"
    assert config.TWITTER_COOKIE.startswith("auth_token=tok123")
    assert config.TWITTER_AUTH_TOKEN == "tok123"
    assert config.TWITTER_CT0 == "ct456"
    assert config.COOKIES == "a1=xhs-cookie"


@pytest.mark.asyncio
async def test_parse_cmd_x_with_explicit_cookies_updates_twitter_auth(monkeypatch):
    monkeypatch.setattr(config, "COOKIES", "a1=xhs-cookie", raising=False)
    monkeypatch.setattr(config, "TWITTER_COOKIE", "", raising=False)
    monkeypatch.setattr(config, "TWITTER_AUTH_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "TWITTER_CT0", "", raising=False)

    explicit = "auth_token=newtok; ct0=newct0; lang=en"
    result = await parse_cmd(
        [
            "--platform",
            "x",
            "--type",
            "creator",
            "--creator_id",
            "elonmusk",
            "--cookies",
            explicit,
        ]
    )

    assert result.platform == "x"
    assert config.TWITTER_COOKIE == explicit
    assert config.TWITTER_AUTH_TOKEN == "newtok"
    assert config.TWITTER_CT0 == "newct0"
