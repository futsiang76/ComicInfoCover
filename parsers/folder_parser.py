#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件夹名解析模块 - 只解析文件夹名
"""

import os
import re
from typing import Dict, Optional

from config import FOLDER_PATTERN


def _extract_aliases_from_series(series_name: str) -> tuple:
    """从系列名中提取非中文原名/译名作为别名，返回 (中文主名, 别名列表)

    规则：
    - 中文片段（含中文标点/全角符号）合并为中文主名
    - 连续的非中文片段（日文假名/英文/数字）提取为别名
    - 无非中文片段时，series 保持原样
    """
    # 交替拆出中文段和非中文段（\u3000-\u303f 中文标点、\uff00-\uffef 全角符号）
    parts = re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+|[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', series_name)
    chinese_parts = []
    alias_parts = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.match(r'^[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+$', part):
            chinese_parts.append(part)
        else:
            alias_parts.append(part)
    main_name = ''.join(chinese_parts).strip()
    if not main_name:
        return series_name, []  # 全非中文，保持原样
    return main_name, alias_parts


def parse_folder_name(folder_name: str, folder_path: Optional[str] = None) -> Optional[Dict]:
    """解析文件夹名，提取系列名、作者、卷数信息、完结状态"""
    match = re.match(FOLDER_PATTERN, folder_name.strip())
    if not match:
        return None
    
    vol_info = match.group("vol_info").strip()
    
    # 解析总卷数和类型
    # 首先检查是否包含"全"字，表示已完结
    if "全" in vol_info:
        # 提取V后面的数字（忽略空格和其他字符）
        vol_match = re.search(r'V(\d+)', vol_info)
        if vol_match:
            total_volumes = int(vol_match.group(1))
        else:
            # 如果vol_info中没有卷数信息，尝试从系列名中提取
            series_with_vol = match.group("series").strip()
            vol_match = re.search(r'V(\d+)', series_with_vol)
            if vol_match:
                total_volumes = int(vol_match.group(1))
            else:
                # 如果系列名中没有卷数信息，尝试从完整的文件夹名中提取
                full_folder_name = folder_name.strip()
                vol_match = re.search(r'V(\d+)', full_folder_name)
                if vol_match:
                    total_volumes = int(vol_match.group(1))
                else:
                    # 当vol_info为"全"时，尝试计算文件夹中的漫画文件数作为总卷数
                    if folder_path and os.path.exists(folder_path):
                        comic_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.zip', '.cbz', '.cbr', '.rar'))]
                        file_count = len(comic_files)
                        if file_count > 0:
                            total_volumes = file_count
                        else:
                            total_volumes = 1
                    else:
                        total_volumes = 1
        vol_type = "已完结"
    elif vol_info.startswith("V"):
        # 提取V后面的数字（忽略空格和其他字符）
        vol_match = re.search(r'V(\d+)', vol_info)
        if vol_match:
            total_volumes = int(vol_match.group(1))
        else:
            total_volumes = 1
        vol_type = "连载"
    elif vol_info == "短篇":
        total_volumes = 1
        vol_type = "短篇"
    else:
        total_volumes = 1
        vol_type = "未知"
    
    # 判断完结状态
    is_complete = bool(match.group("complete")) or "全" in vol_info
    
    # 如果有额外内容（设定集、番外等）
    extras = match.group("extras") if match.group("extras") else ""
    
    # 提取系列名和别名
    series_with_aliases = match.group("series").strip()
    
    # 检查系列名中是否包含方括号别名
    aliases = []
    series_name = series_with_aliases
    
    # 匹配格式：系列名 [别名1] [别名2] ...
    alias_pattern = r'\s*\[(.+?)\]'
    alias_matches = re.findall(alias_pattern, series_with_aliases)
    
    if alias_matches:
        # 提取别名
        aliases = alias_matches
        # 从系列名中移除别名部分
        series_name = re.sub(alias_pattern, '', series_with_aliases).strip()
    
    # 增强：从系列名中提取非中文原名/译名作为别名（如「全职猎人 HUNTER×HUNTER」→ HUNTER×HUNTER）
    main_series, series_aliases = _extract_aliases_from_series(series_name)
    aliases = list(dict.fromkeys(aliases + series_aliases))  # 合并括号别名 + 非中文别名，去重保序
    series_name = main_series
    
    return {
        "author": match.group("author").strip(),
        "series": series_name,
        "aliases": aliases,
        "vol_info": vol_info,
        "total_volumes": total_volumes,
        "vol_type": vol_type,
        "complete": is_complete,
        "has_extras": bool(extras),
        "extras": extras
    }