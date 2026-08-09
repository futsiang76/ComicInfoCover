#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bangumi 搜索卷号过滤模块 - 剔除系列单卷条目的形态特征判定
"""

import re
from typing import Dict, List


# 「卷号标记」正则：括号数字 / 中文卷册话 / 西文卷标记（不区分大小写）
# 注：中文卷册话用 [1-9]\d* 排除「第0卷」——第0卷属一卷全特殊卷（如 进击的巨人 第0卷），
# 按用户实测结论应保留，不视为系列单卷标记
_VOLUME_MARKER_RE = re.compile(
    r"[（(]\s*\d+\s*[）)]"            # 括号数字：(1) (2) （3）
    r"|第\s*[1-9]\d*\s*[卷册话]"       # 中文卷册话：第1卷 / 第2册 / 第3话
    r"|(?:vol\.?\s*\d+|#\d+|V\d+)",   # 西文卷标记：Vol.1 / Vol 1 / #1 / V1
    re.IGNORECASE,
)


def _has_volume_marker(name: str) -> bool:
    """判断名称是否带「卷号标记」（系列单卷的形态特征）

    匹配模式（name 或 name_cn 任一命中即算带标记）：
    - 括号数字：(1) (2) （3）
    - 中文卷册话：第1卷 / 第2册 / 第3话（第0卷不匹配，属一卷全特殊卷）
    - 西文卷标记：Vol.1 / Vol 1 / #1 / V1（不区分大小写）

    Args:
        name: 作品名称（name 或 name_cn）

    Returns:
        bool: True 表示名称带卷号标记
    """
    if not name:
        return False
    return bool(_VOLUME_MARKER_RE.search(name))


def _filter_series_volumes(items: List[Dict]) -> List[Dict]:
    """逐条过滤：剔除 series=False 且名称带「卷号标记」的系列单卷条目

    最终规则（用户拍板 2026-08-05，替代结果数阈值启发式）：
    - series=True（系列条目）→ 保留
    - series=False 且名称带卷号标记（系列的单卷）→ 过滤
    - series=False 但无卷号标记（外传/原画集/设定集/一卷全独立作品）→ 保留

    series 字段由搜索列表（v0/search/subjects）直接提供，无需调详情接口；
    每个条目独立判定，不依赖结果集大小。卷号标记见 _has_volume_marker。

    Args:
        items: 搜索结果列表（元素含 series/name/name_cn 字段）

    Returns:
        List[Dict]: 过滤后的结果列表
    """
    return [item for item in items
            if item.get("series", False) is not False
            or not (_has_volume_marker(item.get("name") or "")
                    or _has_volume_marker(item.get("name_cn") or ""))]
