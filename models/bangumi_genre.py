#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bangumi Genre 提取模块 - tag 白名单与 Genre 字符串生成
"""

import re
from typing import Dict, List

from .bangumi_volume_filter import _VOLUME_MARKER_RE

# 可作 Genre 的 Bangumi tag 白名单（按分类聚合）
BANGUMI_GENRE_WHITELIST = {
    "分类": ["小说", "画集", "绘本", "公式书", "写真", "其他"],
    "来源": ["游戏改", "小说改", "动画改", "影视改"],  # 移除 原创、漫画改（非类别）
    "题材": ["热血", "冒险", "魔幻", "神鬼", "搞笑", "萌系", "爱情", "科幻", "魔法",
             "格斗", "武侠", "机战", "战争", "竞技", "体育", "校园", "生活", "励志",
             "历史", "伪娘", "宅男", "腐男", "腐女", "耽美", "百合", "后宫", "治愈",
             "美食", "推理", "悬疑", "恐怖", "四格", "职场", "侦探", "社会", "音乐",
             "舞蹈", "杂志", "黑道", "穿越", "玄幻", "惊悚", "乙女"],
    "受众": ["少年", "少女", "青年", "BL", "一般向", "GL", "名著", "儿童", "女性", "TL"],
}


def extract_bangumi_genre(detail: Dict) -> str:
    """从 Bangumi API tags 提取 Genre：与白名单比对，按 tags 出现顺序去重

    Returns:
        str: 命中白名单的标签，用 ", " 分隔；无命中返回空字符串
    """
    api_tags = [tag["name"] for tag in detail.get("tags", [])]
    genre = []
    seen = set()
    for tag in api_tags:
        if tag in seen:
            continue
        for category in BANGUMI_GENRE_WHITELIST.values():
            if tag in category:
                genre.append(tag)
                seen.add(tag)
                break
    return ", ".join(genre) if genre else ""


# 名称中需清理的卷标/版本信息（如 (V01)）——在 _VOLUME_MARKER_RE 基础上补充
# 括号内带字母的卷标（(V01)/(Vol.1)），并清理正则移除后残留的空括号
_NAME_VOLUME_CLEAN_RE = re.compile(
    r"[（(]\s*(?:vol\.?\s*|V)\d+\s*[）)]"  # (V01) (Vol.1) （V2）
    r"|(?:vol\.?\s*|#)\d+",                # Vol.1 / #1（裸卷标）
    re.IGNORECASE,
)


def _clean_name_for_alias(name: str) -> str:
    """清理名称中的卷标/版本信息，返回清理后的名称（无效则返回空串）

    复用 _VOLUME_MARKER_RE（括号数字/第X卷/裸 V1）后再补 (V01) 形态并
    去除残留的空括号与首尾空白。
    """
    if not name:
        return ""
    cleaned = _VOLUME_MARKER_RE.sub("", name)
    cleaned = _NAME_VOLUME_CLEAN_RE.sub("", cleaned)
    cleaned = re.sub(r"[（(]\s*[）)]", "", cleaned)  # 清理残留空括号
    cleaned = re.sub(r"[（(][^（）()]*[）)]", "", cleaned)  # 去掉丛书名等带内容括号段，只留主名
    return cleaned.strip(" -_")


def extract_bangumi_aliases(detail: Dict) -> List[str]:
    """从 Bangumi 详情提取系列别名（infobox「别名」+ 日文原名）

    两个来源（按此顺序追加）：
    1. infobox 中 key=「别名」的字段：value 为 list，每项可能是
       {"v": "..."} 或 {"k": "来源", "v": "..."}，只取每项的 v 值
       （来源前缀 k 不拼进别名）
    2. detail["name"]（原名）：非空且与 name_cn 不同时作为别名加入
       （如 進撃の巨人、ガチアクタ），自动清理 (V01) 等卷标/版本信息

    返回去重保序的列表；空串、纯数字（如 2024）剔除；name_cn 本身不进结果。

    Args:
        detail: Bangumi 详情数据（含 infobox/name/name_cn）

    Returns:
        List[str]: 系列别名列表（无则空列表）
    """
    aliases = []

    # 1) infobox「别名」字段
    for item in detail.get("infobox", []) or []:
        if item.get("key") != "别名":
            continue
        value = item.get("value", [])
        if not isinstance(value, list):
            continue
        for entry in value:
            if isinstance(entry, dict) and entry.get("v"):
                alias = str(entry["v"]).strip()
                if alias:
                    aliases.append(alias)
            elif isinstance(entry, str) and entry.strip():
                aliases.append(entry.strip())

    # 2) 日文原名（与 name_cn 不同时作为别名）
    name = (detail.get("name") or "").strip()
    name_cn = (detail.get("name_cn") or "").strip()
    if name and name != name_cn:
        cleaned = _clean_name_for_alias(name)
        if cleaned:
            aliases.append(cleaned)
        # 名字里带括号（如「白いパイロット（手塚治虫漫画全集）」）时，
        # 括号内容（丛书名等有效文本）也作为独立别名；卷标括号(V01/第X卷等)跳过
        for bracket in re.findall(r"[（(]([^（）()]*)[）)]", name):
            b = bracket.strip()
            if b and not _VOLUME_MARKER_RE.search(b):
                aliases.append(b)

    # 去重保序 + 剔除纯数字/空串
    result = []
    seen = set()
    for alias in aliases:
        if not alias or alias in seen:
            continue
        if re.match(r"^\d+$", alias):
            continue
        result.append(alias)
        seen.add(alias)
    return result
