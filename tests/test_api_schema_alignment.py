# -*- coding: utf-8 -*-
"""Schema alignment checks between API and CLI capabilities."""

from api.schemas import CrawlerStartRequest, SaveDataOptionEnum


def test_api_save_option_supports_postgres():
    assert SaveDataOptionEnum.POSTGRES.value == "postgres"
    request = CrawlerStartRequest(
        platform="x",
        crawler_type="search",
        save_option="postgres",
    )
    assert request.save_option == SaveDataOptionEnum.POSTGRES
