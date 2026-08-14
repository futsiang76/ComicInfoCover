#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bangumi ComicInfo 构建模块 - 从详情数据生成 ComicInfo.xml 所需字段
"""

import re
from typing import Dict

from .author_utils import extract_bangumi_authors_by_type
from .bangumi_genre import extract_bangumi_aliases, extract_bangumi_genre


def build_comicinfo(detail: Dict, folder_info: Dict) -> Dict:
    """提取 ComicInfo.xml 所需字段

    角色归类：Bangumi 中的「作者」实际是作画者；故事创作者（原作/脚本等）
    归 Writer，绘画创作者（作者/作画等）归 Penciller。无任何作者时回退
    文件夹作者。

    Args:
        detail: Bangumi 详情数据（含 infobox/tags/summary 等）
        folder_info: 文件夹信息（series/author/complete/total_volumes 等）

    Returns:
        Dict: ComicInfo 字段字典
    """
    author_types = extract_bangumi_authors_by_type(detail)

    # 正确定义角色分类 - Bangumi中的"作者"实际上是作画者
    story_roles = ["原作", "监督", "监制", "脚本", "导演", "原著"]  # 故事创作者
    art_roles = ["作者", "作画", "制作", "插画", "绘制"]        # 绘画创作者

    # 按角色分类收集
    story_authors = []  # 故事相关（Writer）
    art_authors = []    # 绘画相关（Penciller）

    for role_type, authors in author_types.items():
        if role_type in story_roles:
            story_authors.extend(authors)
        elif role_type in art_roles:
            art_authors.extend(authors)

    # 去重
    story_authors = list(dict.fromkeys(story_authors))
    art_authors = list(dict.fromkeys(art_authors))

    # 应用规则
    if len(story_authors) == 0 and len(art_authors) == 0:
        # 没有任何作者信息，使用文件夹作者
        writer_str = folder_info["author"]
        penciller_str = ""
    elif len(story_authors) == 0 and len(art_authors) > 0:
        # 只有绘画作者（包括Bangumi的"作者"），全部放入Writer，Penciller留空
        writer_str = ", ".join(art_authors)
        penciller_str = ""
    elif len(story_authors) > 0 and len(art_authors) == 0:
        # 只有故事作者，全部放入Writer，Penciller留空
        writer_str = ", ".join(story_authors)
        penciller_str = ""
    else:
        # 同时有故事作者和绘画作者，分别放入对应字段
        writer_str = ", ".join(story_authors)
        penciller_str = ", ".join(art_authors)

    # 根据完结状态决定Volume字段
    # 如果已完结，填写总卷数；如果连载中，留空
    volume_value = str(folder_info["total_volumes"]) if folder_info["complete"] else ""

    # 基础信息
    info = {
        "Title": folder_info["series"],
        "Series": folder_info["series"],
        "Count": volume_value,  # 已完结填写总卷数，连载中留空
        "Volume": "",  # 单本书的卷数将在后续处理中填充
        "Writer": writer_str,
        "Penciller": penciller_str,
        "Publisher": "",
        "Summary": "",
        "Tags": "",
        "Genre": extract_bangumi_genre(detail),
        "LanguageISO": "zh-CN",
        "Format": "Zip",
        "Status": "Completed" if folder_info["complete"] else "Ongoing",
        "Web": f"https://bgm.tv/subject/{detail.get('id', '')}",
    }

    # 对于画集、设定集、番外等非单行本内容，清空Count和Volume字段
    if folder_info.get("is_non_volume", False):
        info["Count"] = ""
        info["Volume"] = ""

    # 补充简介（清理HTML标签）
    summary = detail.get("summary", "")
    if summary:
        clean_summary = re.sub(r'<.*?>', '', summary).strip()
        # 如果已完结，在summary最后添加"已完结"标记
        if folder_info["complete"]:
            if clean_summary:
                clean_summary = f"{clean_summary}\n已完结。"
            else:
                clean_summary = "已完结。"  # 如果简介为空，直接设置为"已完结。"
        info["Summary"] = clean_summary

    # 补充标签：命中 Genre 白名单的词从 Tags 移除，避免与 Genre 重复
    genre_tags = set(extract_bangumi_genre(detail).split(", "))
    tags = [tag["name"] for tag in detail.get("tags", []) if tag.get("count", 0) >= 2][:10]
    tags = [t for t in tags if t not in genre_tags]
    tags = [t for t in tags if not re.match(r"^\d+$", t)]  # 去掉纯数字（如 2024）
    remaining = list(tags)
    # 追加系列别名（infobox「别名」+ 日文原名）；与 Genre 词重复的别名同样剔除
    remaining.extend(a for a in extract_bangumi_aliases(detail) if a not in genre_tags)
    remaining.append(info["Status"])
    info["Tags"] = ",".join(dict.fromkeys(remaining))  # 去重（保留顺序）

    # 补充出版社
    for item in detail.get("infobox", []):
        if item.get("key") == "出版社":
            value = item.get("value", "")
            if isinstance(value, list):
                info["Publisher"] = ",".join([v.get("v", "") for v in value if v.get("v")])
            else:
                info["Publisher"] = value.strip()
            break

    return info
