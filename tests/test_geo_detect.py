#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 IP 地理检测：主/备 API 判定中国大陆 + 失败降级（全部 mock 网络）"""

from unittest.mock import MagicMock, patch

import requests

from utils.geo_detect import IPAPI_URL, IPINFO_URL, detect_country_cn


def _mock_get(side_effect_map):
    """构造 mock requests.get：按 URL 返回对应响应或抛异常"""
    def side_effect(url, **kwargs):
        effect = side_effect_map[url]
        if isinstance(effect, Exception):
            raise effect
        return effect
    return side_effect


def _json_resp(data):
    resp = MagicMock()
    resp.json.return_value = data
    return resp


@patch("utils.geo_detect.requests.get")
def test_ipinfo_cn_returns_true(mock_get):
    """主 API 返回 CN → True（不请求备 API）"""
    mock_get.side_effect = _mock_get({IPINFO_URL: _json_resp({"country": "CN"})})
    assert detect_country_cn() is True
    mock_get.assert_called_once()


@patch("utils.geo_detect.requests.get")
def test_ipinfo_non_cn_returns_false(mock_get):
    """主 API 返回非 CN（如 US）→ False"""
    mock_get.side_effect = _mock_get({IPINFO_URL: _json_resp({"country": "US"})})
    assert detect_country_cn() is False


@patch("utils.geo_detect.requests.get")
def test_ipinfo_fails_falls_back_to_ipapi_cn(mock_get):
    """主 API 连接失败 → 备 API 返回 CN → True"""
    mock_get.side_effect = _mock_get({
        IPINFO_URL: requests.exceptions.ConnectionError("blocked"),
        IPAPI_URL: _json_resp({"countryCode": "CN"}),
    })
    assert detect_country_cn() is True


@patch("utils.geo_detect.requests.get")
def test_ipinfo_fails_ipapi_non_cn_returns_false(mock_get):
    """主 API 超时 → 备 API 返回非 CN → False"""
    mock_get.side_effect = _mock_get({
        IPINFO_URL: requests.exceptions.Timeout("timeout"),
        IPAPI_URL: _json_resp({"countryCode": "US"}),
    })
    assert detect_country_cn() is False


@patch("utils.geo_detect.requests.get")
def test_both_fail_returns_none(mock_get):
    """主备都失败 → None（调用方保持官方默认）"""
    mock_get.side_effect = _mock_get({
        IPINFO_URL: requests.exceptions.ConnectionError("blocked"),
        IPAPI_URL: requests.exceptions.Timeout("timeout"),
    })
    assert detect_country_cn() is None


@patch("utils.geo_detect.requests.get")
def test_invalid_json_falls_back(mock_get):
    """主 API 返回非 JSON → 降级备 API"""
    bad = MagicMock()
    bad.json.side_effect = ValueError("bad json")
    mock_get.side_effect = _mock_get({
        IPINFO_URL: bad,
        IPAPI_URL: _json_resp({"countryCode": "CN"}),
    })
    assert detect_country_cn() is True


@patch("utils.geo_detect.requests.get")
def test_http_error_falls_back(mock_get):
    """主 API HTTP 错误 → 降级备 API"""
    err = MagicMock()
    err.raise_for_status.side_effect = requests.exceptions.HTTPError("429")
    mock_get.side_effect = _mock_get({
        IPINFO_URL: err,
        IPAPI_URL: _json_resp({"countryCode": "CN"}),
    })
    assert detect_country_cn() is True
