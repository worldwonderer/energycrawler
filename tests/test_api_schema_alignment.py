# -*- coding: utf-8 -*-
"""Schema alignment checks between API and CLI capabilities."""

import pytest
from pydantic import ValidationError

from api.schemas import CrawlerStartRequest, SaveDataOptionEnum, SafetyProfileEnum


def test_api_save_option_supports_postgres():
    assert SaveDataOptionEnum.POSTGRES.value == "postgres"
    request = CrawlerStartRequest(
        platform="x",
        crawler_type="search",
        save_option="postgres",
    )
    assert request.save_option == SaveDataOptionEnum.POSTGRES


def test_api_safety_profile_supports_expected_values():
    request = CrawlerStartRequest(
        platform="xhs",
        crawler_type="search",
        save_option="json",
        safety_profile="aggressive",
    )
    assert request.safety_profile == SafetyProfileEnum.AGGRESSIVE


def test_api_safety_profile_rejects_unknown_value():
    with pytest.raises(ValidationError):
        CrawlerStartRequest(
            platform="xhs",
            crawler_type="search",
            save_option="json",
            safety_profile="turbo",
        )
