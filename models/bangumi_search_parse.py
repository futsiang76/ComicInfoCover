#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bangumi v2 GET 搜索响应解析模块
"""

from typing import Dict, List


def _parse_search_response(data: Dict) -> List[Dict]:
    """解析 v2 GET 搜索响应，并做字段映射对齐 v0 POST 契约

    v2 GET {base}/search/subject/{kw} 响应：
        {"results": <总数 int>, "list": [...]}
    - 真实条目在 list 字段（results 是 int 总数，非列表）
    - 条目字段与 v0 POST 不同（v0: data[].name/name_cn；v2: list[].name/name_cn）

    返回的条目保留后续处理所需字段（id/name/name_cn/summary/images/
    date/country/infobox/volumes 等），images 归一为可能缺失的安全访问。
    """
    items = data.get("list", [])
    if not isinstance(items, list):
        return []
    results = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        # images 缺失时补空 dict，保持后续 .get("large"/"common") 安全
        item.setdefault("images", {})
        results.append(item)
    return results
