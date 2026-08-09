#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IP 地理检测模块 - 判断出口 IP 是否中国大陆

启动时用于选择默认 Bangumi 数据源：大陆 → 镜像，非大陆 → 官方。
主 API ipinfo.io（大陆实测 ~1.0s），失败降级 ip-api.com（大陆实测 ~4.4s）。
网络类错误不重试，报回即止。
"""

from typing import Optional

import requests

# 主/备 IP 检测 API（返回国家码字段不同：ipinfo 用 country，ip-api 用 countryCode）
IPINFO_URL = "https://ipinfo.io/json"
IPAPI_URL = "http://ip-api.com/json/?lang=zh-CN"
# 单次请求超时（秒）：主备各独立计时，最坏 ~10s 后返回 None
GEO_TIMEOUT = 5


def _fetch_json(url: str) -> Optional[dict]:
    """GET 并解析 JSON 字典；网络/超时/解析失败返回 None（不重试）

    Args:
        url: 检测 API 地址

    Returns:
        Optional[dict]: 响应 JSON 字典；失败返回 None
    """
    try:
        resp = requests.get(url, timeout=GEO_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.exceptions.RequestException, ValueError):
        return None
    return data if isinstance(data, dict) else None


def detect_country_cn() -> Optional[bool]:
    """检测当前出口 IP 是否中国大陆

    主 API ipinfo.io（{"country": "CN"}）→ 备 API ip-api.com
    （{"countryCode": "CN"}）；两者都失败返回 None，由调用方决定默认源。
    网络类错误不重试。

    Returns:
        Optional[bool]: True=中国大陆；False=非大陆；None=检测失败
    """
    data = _fetch_json(IPINFO_URL)
    if data is not None:
        return data.get("country") == "CN"
    data = _fetch_json(IPAPI_URL)
    if data is not None:
        return data.get("countryCode") == "CN"
    return None
