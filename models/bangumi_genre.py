#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bangumi Genre 提取模块 - tag 白名单与 Genre 字符串生成
"""

from typing import Dict

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
