# -*- coding: utf-8 -*-
"""Unit tests for XHS signature pipeline helpers."""

from media_platform.xhs.energy_client_adapter import (
    build_sign_digest,
    canonical_sign_input,
    infer_data_type,
    normalize_mnsv2_result,
)


def test_canonical_sign_input_post_dict():
    uri = "/api/sns/web/v1/search/notes"
    payload = {"keyword": "test", "page": 1}
    result = canonical_sign_input(uri, payload, "POST")
    assert result == '/api/sns/web/v1/search/notes{"keyword":"test","page":1}'


def test_canonical_sign_input_get_dict():
    uri = "/api/sns/web/v1/search/notes"
    params = {"keyword": "a b", "tags": ["x", "y"], "empty": None}
    result = canonical_sign_input(uri, params, "GET")
    assert result.startswith(f"{uri}?")
    assert "keyword=a%20b" in result
    assert "tags=x%2Cy" in result
    assert "empty=" in result


def test_build_sign_digest():
    assert build_sign_digest("test") == "098f6bcd4621d373cade4e832627b4f6"


def test_infer_data_type():
    assert infer_data_type({"k": "v"}) == "object"
    assert infer_data_type(["a"]) == "object"
    assert infer_data_type("abc") == "string"
    assert infer_data_type(None) == "string"


def test_normalize_mnsv2_result():
    assert normalize_mnsv2_result('"abc"') == "abc"
    assert normalize_mnsv2_result("'abc'") == "abc"
    assert normalize_mnsv2_result("abc") == "abc"
    assert normalize_mnsv2_result("") == ""
