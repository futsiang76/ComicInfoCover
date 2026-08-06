#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作者名工具 - 清洗/拆分/匹配/分析作者信息
"""

import re
from typing import Dict, List

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
    # 使用非贪婪匹配，从外层开始
    author_name = re.sub(r'（[^）]*）', '', author_name)  # 全角圆括号
    author_name = re.sub(r'「[^」]*」', '', author_name)  # 全角方括号
    author_name = re.sub(r'『[^』]*』', '', author_name)  # 全角双引号
    author_name = re.sub(r'【[^】]*】', '', author_name)  # 全角方头括号
    
    # 移除半角括号及其内容：()
    author_name = re.sub(r'\([^)]*\)', '', author_name)
    
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
    
    # 定义常见的作者分隔符（注意：不包含可能出现在人名中的符号，如"·"、"与"、"和"）
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
        '・',      # 全角中点（日文）
    ]
    
    # 使用正则表达式分割
    pattern = '|'.join(re.escape(sep) for sep in separators)
    authors = re.split(pattern, author_string)
    
    # 清理并过滤空字符串
    authors = [_clean_author_name(author.strip()) for author in authors if author.strip()]
    
    # 过滤清理后的空字符串
    authors = [author for author in authors if author]
    
    return authors


def extract_bangumi_authors( detail: Dict) -> List[str]:
    """从Bangumi详情中提取所有作者名"""
    authors = []
    infobox = detail.get("infobox", [])
    
    # 扩展的作者类型匹配，按优先级排序
    author_types = [
        # 中文
        "作者", "作画", "原作", "脚本", "监督", "导演", "原著", "插画",
        # 日文
        "ストーリー", "コミカライズ", "原案", "脚本", "監督", "演出", "原作", "イラスト",
        "キャラクターデザイン", "メカニックデザイン", "オリジナルキャラクターデザイン"
    ]
    
    for author_type in author_types:
        for item in infobox:
            if item.get("key") == author_type:
                value = item.get("value", "")
                # 处理列表/字符串格式
                if isinstance(value, list):
                    for v in value:
                        if isinstance(v, dict):
                            v_value = v.get("v")
                            if isinstance(v_value, str) and v_value.strip():
                                # 分割并清理作者名字
                                authors.extend(_split_authors(v_value))
                elif isinstance(value, str) and value.strip():
                    # 分割并清理作者名字
                    authors.extend(_split_authors(value))
    
    # 去重并返回
    return list(dict.fromkeys(authors))


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
    
    # 处理文件夹中的多个作者（用×或&或/分隔）
    folder_authors = []
    if "×" in folder_author:
        folder_authors = [author.strip() for author in folder_author.split("×")]
    elif "&" in folder_author:
        folder_authors = [author.strip() for author in folder_author.split("&")]
    elif "/" in folder_author:
        folder_authors = [author.strip() for author in folder_author.split("/")]
    else:
        folder_authors = [folder_author.strip()]
    
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

