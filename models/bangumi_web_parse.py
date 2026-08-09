#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bangumi 网页解析模块 - 信息栏作者提取（API infobox 无作者字段时的网页兜底）
"""

import re
from typing import List

# 作者类 tip 字段（与 extract_bangumi_authors 的 author_types 对应）
_WEB_AUTHOR_TIPS = (
    "作者|作画|原作|脚本|监督|导演|原著|插画"
    "|ストーリー|コミカライズ|原案|監督|演出|イラスト|キャラクターデザイン"
    "|メカニックデザイン|オリジナルキャラクターデザイン"
)
# 信息栏字段：<span class="tip">作者: </span> 后接该字段内容（到下一 tip 或 li 结束）
_WEB_AUTHOR_FIELD_RE = re.compile(
    r'<span class="tip">\s*(' + _WEB_AUTHOR_TIPS + r')\s*[:：]?\s*</span>'
    r'(.*?)(?=<span class="tip">|</li>|</ul>|$)',
    re.DOTALL | re.IGNORECASE,
)
# 字段内人物链接：<a href="/person/39" class="l">CLAMP</a>
_PERSON_LINK_RE = re.compile(r'<a[^>]+href="/person/\d+"[^>]*>(.*?)</a>', re.DOTALL)


def _parse_web_authors(html: str) -> List[str]:
    """从 Bangumi 网页信息栏 HTML 提取作者名列表

    匹配所有作者类 tip 字段（作者/原作/作画 等），提取字段内全部 /person/
    人物链接文本；同名去重保序。无匹配返回空列表。
    """
    if not html:
        return []
    authors = []
    for match in _WEB_AUTHOR_FIELD_RE.finditer(html):
        for name in _PERSON_LINK_RE.findall(match.group(2)):
            name = re.sub(r'<[^>]+>', '', name).strip()
            if name:
                authors.append(name)
    return list(dict.fromkeys(authors))
