#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作者名工具 - 清洗/拆分/匹配/分析作者信息
"""

import re
from typing import Dict, List, Optional

from zhconv import convert
from thefuzz import fuzz
from config import AUTHOR_MATCH_THRESHOLD

def _clean_author_name(author_name: str) -> str:
    """清理作者名字，移除括号及其内容
    
    Args:
        author_name: 作者名字
        
    Returns:
        str: 清理后的作者名字
    """
    if not author_name:
        return ""
    
    # 先移除全角括号及其内容（包括嵌套）：「」『』【】（）
    # 循环反复剥离最内层括号段直到无可剥离内容，处理嵌套括号
    # （如 "(Mark Gatiss (Author), Steven Moffat (Creator))" 需剥两轮）
    # 注意：[^（）]* 用「不含任何括号字符」而非「不含右括号」，
    # 否则 "([^)]*)" 会跨过嵌套左括号、从第一个 ( 匹配到第一个 )，剥不干净
    while True:
        new_name = author_name
        new_name = re.sub(r'（[^（）]*）', '', new_name)  # 全角圆括号
        new_name = re.sub(r'「[^「」]*」', '', new_name)  # 全角方括号
        new_name = re.sub(r'『[^『』]*』', '', new_name)  # 全角双引号
        new_name = re.sub(r'【[^【】]*】', '', new_name)  # 全角方头括号
        new_name = re.sub(r'\([^()]*\)', '', new_name)  # 半角括号
        if new_name == author_name:
            break
        author_name = new_name

    # 兜底：清除任何残留的半角/全角括号字符（如不成对的多余右括号）
    author_name = re.sub(r'[()（）「」『』【】]', '', author_name)

    # 清理多余空格
    author_name = author_name.strip()
    
    return author_name


def _split_authors( author_string: str) -> List[str]:
    """分割作者字符串，处理各种分隔符
    
    Args:
        author_string: 作者字符串
        
    Returns:
        List[str]: 分割后的作者列表
    """
    if not author_string or not author_string.strip():
        return []
    
    # 定义常见的作者分隔符（注意：不包含可能出现在人名中的符号，
    # 如 "·"（U+00B7）、"・"（U+30FB 日文中点，スティーヴン・モファット 的组成部分）、"与"、"和"）
    separators = [
        '、',      # 中文顿号
        '，',      # 全角逗号
        ',',       # 半角逗号
        '×',       # 乘号
        '*',       # 星号
        '#',       # 井号
        '&',       # 与符号
        '/',       # 斜杠
        '\\',      # 反斜杠
        '+',       # 加号
    ]
    
    # 先整体剥离括号注释（如 "(Mark Gatiss (Author), Steven Moffat (Creator))"），
    # 否则括号内的逗号/顿号会被当作作者分隔符，产生残留片段
    author_string = _clean_author_name(author_string)
    if not author_string:
        return []
    
    # 使用正则表达式分割
    pattern = '|'.join(re.escape(sep) for sep in separators)
    authors = re.split(pattern, author_string)
    
    # 清理并过滤空字符串（此时已无括号，仅 strip 即可）
    authors = [author.strip() for author in authors if author.strip()]
    
    # 过滤清理后的空字符串
    authors = [author for author in authors if author]
    
    return authors


# ----------------------------------------------------------------------
# Bangumi 人物职务 → ComicInfo 角色字段 统一映射
# （persons 端点的 relation 与 infobox 的 key 共用同一张表做同义归一；
#   出版社/连载杂志/书系/出品方等非人物职务不在表中，天然被过滤）
# ----------------------------------------------------------------------
PERSON_ROLE_TO_FIELD = {
    # Writer（故事创作）
    "原作": "Writer",
    "脚本": "Writer",
    "监督": "Writer",
    "监制": "Writer",
    "导演": "Writer",
    "原著": "Writer",
    # Penciller（绘画创作；persons「作者」= infobox「作画」同义归一）
    "作者": "Penciller",
    "作画": "Penciller",
    "插画": "Penciller",
    "绘制": "Penciller",
    # Colorist（上色）
    "上色": "Colorist",
    "色彩": "Colorist",
    # 其它人物职务（保持现有行为不变）
    "墨线": "Inker",
    "字母": "Letterer",
    "封面": "CoverArtist",
    "编辑": "Editor",
    # 日文 infobox key
    "ストーリー": "Writer",           # Story/故事
    "原案": "Writer",                 # Original Plan/原案
    "監督": "Writer",                 # Director/监督
    "演出": "Writer",                 # Direction/演出
    "コミカライズ": "Penciller",       # Comicalize/漫画化
    "イラスト": "Penciller",           # Illustration/插画
    "キャラクターデザイン": "Penciller",  # Character Design
    "メカニックデザイン": "Penciller",    # Mechanic Design
    "オリジナルキャラクターデザイン": "Penciller",  # Original Character Design
}

# 主要三栏（Writer/Penciller/Colorist）+ 既有次要职务栏位
_AUTHOR_FIELDS = ["Writer", "Penciller", "Colorist",
                  "Inker", "Letterer", "CoverArtist", "Editor"]


def _infobox_value_names(value) -> List[str]:
    """提取 infobox 字段值中的人名列表（兼容 list[dict{v}] / list[str] / str）"""
    names = []
    if isinstance(value, list):
        for v in value:
            if isinstance(v, dict):
                v_value = v.get("v")
                if isinstance(v_value, str) and v_value.strip():
                    names.append(v_value)
            elif isinstance(v, str) and v.strip():
                names.append(v)
    elif isinstance(value, str) and value.strip():
        names.append(value)
    return names


def extract_bangumi_authors_merged(detail: Optional[Dict],
                                   persons: Optional[List[Dict]] = None) -> Dict[str, List[str]]:
    """合并 infobox + persons 两端点作者，按人物职务分类（Writer/Penciller/Colorist 为主）

    规则：
    - infobox 优先、persons 补充，两端点每次都合并（非「缺才补」按需优化）；
    - persons 只保留人物职务（作者/原作/作画/脚本/插画/上色/色彩/监督/导演/原著等），
      出版社/连载杂志/书系/出品方等非人物职务一律过滤；
    - 同一人名跨端点只进一个字段（优先 infobox 的职务映射）；
    - relation 命名不一致以同义归一（如 persons「作者」= infobox「作画」→ Penciller）；
    - 多作者按 _split_authors 分隔符集合拆分。

    Args:
        detail: Bangumi 详情（含 infobox；可空）
        persons: /v0/subjects/{id}/persons 返回的人物列表（可空）

    Returns:
        Dict[str, List[str]]: 按角色字段分类的作者名列表（保序去重）
    """
    fields: Dict[str, List[str]] = {f: [] for f in _AUTHOR_FIELDS}
    seen = set()  # 跨端点去重：同一个人只进一个字段

    def _add(field: str, raw_name: str) -> None:
        for name in _split_authors(raw_name):
            if name and name not in seen:
                seen.add(name)
                fields[field].append(name)

    # 1. infobox（优先映射）
    for item in (detail or {}).get("infobox", []) or []:
        key = item.get("key", "")
        field = PERSON_ROLE_TO_FIELD.get(key)
        if not field:
            continue
        for raw_name in _infobox_value_names(item.get("value", "")):
            _add(field, raw_name)

    # 2. persons（补充；同名人已进字段则跳过）
    for person in persons or []:
        if not isinstance(person, dict):
            continue
        name = person.get("name", "")
        field = PERSON_ROLE_TO_FIELD.get(person.get("relation", ""))
        if not field or not name:
            continue
        _add(field, name)

    return fields


def extract_bangumi_authors(detail: Optional[Dict],
                            persons: Optional[List[Dict]] = None) -> List[str]:
    """从Bangumi详情中提取所有作者名（flat，匹配用）

    infobox + persons 两端点人物职务合并；persons 提供时把人物职务并入，
    避免文件夹作者=原作（infobox 仅作画）时匹配失败。

    Args:
        detail: Bangumi 详情（含 infobox；可空）
        persons: /v0/subjects/{id}/persons 人物列表（可空）

    Returns:
        List[str]: 去重保序的作者名列表
    """
    authors = []
    for names in extract_bangumi_authors_merged(detail, persons).values():
        for name in names:
            if name not in authors:
                authors.append(name)
    return authors


def extract_bangumi_authors_by_type( detail: Dict) -> Dict[str, List[str]]:
    """从Bangumi详情中按类型提取作者信息"""
    author_types = {}
    infobox = detail.get("infobox", [])
    
    # 定义不同类型的作者字段
    type_mapping = {
        # 中文
        "原作": "原作",
        "作者": "作者", 
        "作画": "作画",
        "脚本": "脚本",
        "插画": "插画",
        "监督": "监督",
        "导演": "导演",
        "原著": "原著",
        # 日文
        "ストーリー": "原作",          # Story/故事
        "コミカライズ": "作画",        # Comicalize/漫画化
        "原案": "原作",                # Original Plan/原案
        "監督": "监督",                # Director/监督
        "演出": "监督",                # Direction/演出
        "イラスト": "插画",            # Illustration/插画
        "キャラクターデザイン": "作画",  # Character Design
        "メカニックデザイン": "作画",    # Mechanic Design
        "オリジナルキャラクターデザイン": "作画",  # Original Character Design
    }
    
    for item in infobox:
        key = item.get("key", "")
        if key in type_mapping:
            value = item.get("value", "")
            authors = []
            
                            # 处理列表/字符串格式
            if isinstance(value, list):
                for v in value:
                    if isinstance(v, dict):
                        v_value = v.get("v")
                        if isinstance(v_value, str) and v_value.strip():
                            # 分割并清理作者名字
                            authors.extend(_split_authors(v_value))
            elif isinstance(value, str):
                if value.strip():
                    # 分割并清理作者名字
                    authors.extend(_split_authors(value))
            
            if authors:
                # 使用标准化的类型名
                standard_type = type_mapping[key]
                if standard_type not in author_types:
                    author_types[standard_type] = []
                author_types[standard_type].extend(authors)
    
    # 去重
    for key in author_types:
        author_types[key] = list(dict.fromkeys(author_types[key]))
    
    return author_types


def analyze_bangumi_author_types( detail: Dict) -> Dict[str, List[str]]:
    """分析Bangumi返回的所有作者类型（用于调试和了解数据结构）"""
    author_info = {}
    infobox = detail.get("infobox", [])
    
    # 收集所有可能的作者相关字段
    for item in infobox:
        key = item.get("key", "")
        # 匹配所有可能的作者类型关键词
        if any(keyword in key for keyword in ["作者", "作画", "原作", "脚本", "监督", "导演", "原著", "插画", "绘制", "制作"]):
            value = item.get("value", "")
            authors = []
            
            if isinstance(value, list):
                for v in value:
                    if isinstance(v, dict):
                        v_value = v.get("v")
                        if isinstance(v_value, str) and v_value.strip():
                            authors.append(v_value.strip())
            elif isinstance(value, str):
                if value.strip():
                    authors.append(value.strip())
            
            if authors:
                author_info[key] = authors
    
    return author_info


def filter_results_by_author(search_results: List[Dict], folder_author: str,
                             extract_authors, threshold: int = AUTHOR_MATCH_THRESHOLD) -> List[Dict]:
    """过滤搜索结果：逐个提取作者并与文件夹作者比对，返回作者匹配项

    公共过滤层，Bangumi 与 manhuagui 复用：调用方传入 extract_authors(result)
    提取单个结果的作者列表——Bangumi 经详情接口提取，manhuagui 直接从搜索项的
    author 字段提取。无作者的结果不参与比对，直接过滤。

    Args:
        search_results: 搜索结果列表
        folder_author: 文件夹作者名
        extract_authors: 可调用对象，输入单个结果 dict，返回作者名列表
        threshold: 作者匹配阈值

    Returns:
        List[Dict]: 作者匹配的搜索结果
    """
    matching_results = []
    for result in search_results:
        authors = extract_authors(result)
        if authors and match_author(folder_author, authors):
            matching_results.append(result)
    return matching_results


def match_author( folder_author: str, bangumi_authors: List[str]) -> bool:
    """验证作者名是否匹配（任一作者≥阈值即匹配）"""
    if not bangumi_authors:
        return False
    
    # 处理文件夹中的多个作者（统一使用 _split_authors 的分隔符集合）
    folder_authors = _split_authors(folder_author)
    
    # 转换文件夹作者名为中文
    folder_authors_cn = [convert(author, "zh-cn") for author in folder_authors]
    
    # 检查每个文件夹作者是否与Bangumi中的任一作者匹配（忽略英文大小写）
    for folder_author_cn in folder_authors_cn:
        for bgm_author in bangumi_authors:
            bgm_author_cn = convert(bgm_author, "zh-cn")
            # 计算作者名匹配度（忽略英文大小写）
            score = max(
                fuzz.ratio(folder_author_cn.lower(), bgm_author_cn.lower()),
                fuzz.partial_ratio(folder_author_cn.lower(), bgm_author_cn.lower())
            )
            if score >= AUTHOR_MATCH_THRESHOLD:
                print(f"✅ 作者匹配成功: 文件夹[{folder_author}] ↔ Bangumi[{bgm_author}] (匹配度: {score}%)")
                return True
    
    print(f"❌ 作者匹配失败: 文件夹[{folder_author}] ≠ Bangumi[{', '.join(bangumi_authors)}]")
    return False

