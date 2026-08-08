#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件夹名解析模块 - 只解析文件夹名
"""

import os
import re
from typing import Dict, Optional

from config import FOLDER_PATTERN

# 「卷标类片段」正则：括号数字 / 中文卷册话 / 西文卷标记（不区分大小写）。
# 与 bangumi_fetcher 的 _VOLUME_MARKER_RE 同源语义：V01 / (V02全) / 第1卷 等
# 是卷标不是别名，不应进入 aliases 参与搜索。
_VOLUME_MARKER_RE = re.compile(
    r"[（(]\s*\d+\s*[）)]"            # 括号数字：(1) (2) （3）
    r"|第\s*[1-9]\d*\s*[卷册话]"       # 中文卷册话：第1卷 / 第2册 / 第3话
    r"|(?:vol\.?\s*\d+|#\d+|V\d+)",   # 西文卷标记：Vol.1 / Vol 1 / #1 / V1
    re.IGNORECASE,
)


def _is_volume_marker(text: str) -> bool:
    """判断片段是否为卷标类内容（不进别名）"""
    return bool(_VOLUME_MARKER_RE.search(text or ""))


def _extract_aliases_from_series(series_name: str, author: str = "") -> tuple:
    """从系列名中提取非中文原名/译名作为别名，返回 (中文主名, 别名列表)

    规则：
    - 中文片段（含中文标点/全角符号）合并为中文主名
    - 连续的非中文片段（日文假名/英文/数字）提取为别名
    - 非中文片段若与作者名相同（大小写不敏感）→ 并入系列名（作者是身份不是别名）
    - 卷标类片段（V01/(V02全)/第1卷 等）不进别名
    - 无非中文片段时，series 保持原样
    """
    # 交替拆出中文段和非中文段（\u3000-\u303f 中文标点、\uff00-\uffef 全角符号）
    parts = re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+|[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', series_name)
    main_parts = []
    alias_parts = []
    author_key = author.strip().lower()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.match(r'^[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+$', part):
            main_parts.append(part)
        elif _is_volume_marker(part):
            continue  # 卷标类片段既不进别名也不并入系列名
        elif author_key and part.lower() == author_key:
            main_parts.append(part)  # 与作者名相同的片段并入系列名
        else:
            alias_parts.append(part)
    main_name = ''.join(main_parts).strip()
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
    main_series, series_aliases = _extract_aliases_from_series(series_name, match.group("author"))
    # 合并括号别名 + 非中文别名，去重保序；卷标类片段（如 V01）不进别名
    aliases = list(dict.fromkeys(
        alias for alias in (aliases + series_aliases) if not _is_volume_marker(alias)
    ))
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

# 宽松解析（2026-08-06 规则）已拆至 folder_parser_lenient，此处仅重导出。
# 括号规则见 folder_parser_lenient.parse_folder_name_lenient（2026-08-09 更新）。
from .folder_parser_lenient import parse_folder_name_lenient  # noqa: E402,F401
