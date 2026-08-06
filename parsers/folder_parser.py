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



# =====================================================================
# 宽松解析（parse_folder_name_lenient，2026-08-06 用户规则）——与旧函数并存
# =====================================================================
# 卷标正则：V/Vol/volume/卷/册/期/C/chapter + 数字/中文数字/全角数字。
# V04（V 直接跟数字）与 Vol.1 分开写；C97 是展会码（tag），C1-C9 才是卷标；支持 第01-12巻。
VOL_RE = re.compile(
    r"(?:"
    r"[Vv][Oo][Ll][Uu][Mm][Ee]\.?\s*[0-9０-９一二三四五六七八九十百]+|"
    r"[Vv][Oo][Ll]\.?\s*[0-9０-９一二三四五六七八九十百]+|"
    r"(?<![A-Za-z0-9])[Vv][0-9０-９]+|"
    r"[Cc][Hh][Aa][Pp][Tt][Ee][Rr]\.?\s*[0-9０-９]+|"
    r"[Cc][Hh]\.?\s*[0-9０-９]+|"
    r"(?<![A-Za-z0-9])[Cc][0-9０-９](?![0-9０-９])|"
    r"第\s*[0-9０-９一二三四五六七八九十百]+(?:\s*[-~—至]\s*[0-9０-９一二三四五六七八九十百]+)?\s*[巻卷话話]|"
    r"[0-9０-９一二三四五六七八九十百]+\s*[巻卷]|"
    r"[0-9０-９]+\s*[册冊]|[0-9０-９]+\s*[期]|[0-9０-９]+\s*[话話]|"
    r"[巻卷册冊期话話]\s*[0-9０-９一二三四五六七八九十百]+"
    r")",
    re.IGNORECASE,
)
# 黑名单词表：命中 → tag（语言/版本/来源/类型），不参与搜索
TAG_BLACKLIST = {
    "日", "中", "英", "汉", "繁", "简",
    "双语", "日文", "中文", "英文", "简中", "繁中", "日文原版", "日文版", "中文版", "英文版",
    "日版", "台版", "港版", "大陆版", "国漫", "日漫",
    "完全版", "爱藏版", "电子版", "文库版", "新装版", "纪念版", "收藏版", "典藏版",
    "全彩", "彩色版", "黑白", "扫描版", "修复版", "高清", "dx", "digital", "colored",
    "color", "full color", "remastered", "raw", "scan", "scans", "scanlation", "scanlator",
    "汉化", "汉化组", "生肉", "自购", "扫图", "自扫", "转载", "精排", "修复", "民间汉化",
    "完结", "连载中", "连载", "短篇", "短篇集", "单行本", "画集", "原画集", "设定集", "公式书",
    "番外", "外传", "特别篇", "总集篇", "同人", "合集", "精选集", "别册", "complete", "completed", "ongoing",
    "授权版", "官方", "台版授权",
}
COMPLETE_WORDS = ("全", "完结", "完", "end", "completed", "fin", "complete")
_HINTS_COMPLETE = ("完结", "end", "completed", "fin", "complete")   # tag 分支只认多字词
_HINTS_ONGOING = ("未完结", "连载中", "连载", "ongoing", "未完")
_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "零": 0}
_BRACKET_OPEN = set("[（(")
_BRACKET_CLOSE = set("]）)")
def _to_halfwidth(text):
    """全角字母/数字转半角"""
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)
def _extract_numbers(text):
    """提取卷标文本中的数字（含中文/全角数字）"""
    half = _to_halfwidth(text)
    nums = [int(d) for d in re.findall(r"\d+", half)]
    if not nums:
        m = re.search(r"[一二三四五六七八九十百零]+", half)
        if m:
            total = current = 0
            for ch in m.group(0):
                if ch in "十拾":
                    current = current * 10 if current else 10
                    total += current
                    current = 0
                elif ch in "百佰":
                    current = current * 100 if current else 100
                    total += current
                    current = 0
                else:
                    current += _CN_DIGITS.get(ch, 0)
            nums = [total + current]
    return nums
def _is_tag_content(text):
    """判断括号内容是否为 tag（黑名单命中或展会码 C97/C99/C100）"""
    t = text.strip()
    if not t:
        return False
    if t in TAG_BLACKLIST or re.match(r"^C\d{2,3}$", t, re.IGNORECASE):
        return True
    low = t.lower()
    return any(len(w) > 1 and w in low for w in TAG_BLACKLIST)
def _scan_brackets(text):
    """返回最外层括号组 (start, end)，支持嵌套"""
    spans = []
    i, n = 0, len(text)
    while i < n:
        if text[i] in _BRACKET_OPEN:
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if text[j] in _BRACKET_OPEN:
                    depth += 1
                elif text[j] in _BRACKET_CLOSE:
                    depth -= 1
                j += 1
            spans.append((i, j))
            i = j
        else:
            i += 1
    return spans
def _split_nested(content):
    """拆分可能嵌套的括号内容 → (最内层列表, 外层残留文本列表)"""
    spans = _scan_brackets(content)
    if not spans:
        return [content], []
    innermost, leftovers, last = [], [], 0
    for start, end in spans:
        piece = content[last:start].strip()
        if piece:
            leftovers.append(piece)
        sub_in, sub_left = _split_nested(content[start + 1:end - 1])
        innermost.extend(sub_in)
        leftovers.extend(sub_left)
        last = end
    tail = content[last:].strip()
    if tail:
        leftovers.append(tail)
    return innermost, leftovers
def _extract_inline_volume(text):
    """剥离正文内联卷标 → (剥离后文本, 卷标文本, 数字列表)"""
    matches = list(VOL_RE.finditer(text))
    if not matches:
        return text, None, []
    numbers = []
    for m in matches:
        numbers.extend(_extract_numbers(m.group(0)))
    stripped = re.sub(r"\s+", " ", (text[:matches[0].start()] + text[matches[-1].end():]).strip())
    return stripped.strip(" -–—·|"), text[matches[0].start():matches[-1].end()].strip(), numbers
def parse_folder_name_lenient(folder_name, folder_path=None):
    """宽松解析文件夹名（2026-08-06 规则），兼容多种主流格式。

    返回与 parse_folder_name 兼容的 dict，并新增 tags 字段。
    """
    name = (folder_name or "").strip()
    if not name:
        return None
    # 作者 = 第一个 [..]（无作者容忍）；[标题][作者][卷]… 相邻两括号 → U2 格式
    leading, rest, author = [], name, ""
    for _ in range(2):
        m = re.match(r"^\[([^\[\]]*)\]", rest)
        if not m:
            break
        leading.append(m.group(1).strip())
        rest = rest[m.end():].strip()
    series_prefix = leading[0] if len(leading) == 2 else ""
    if leading:
        author = leading[1] if len(leading) == 2 else leading[0]
    # 括号分组（嵌套取最内层）+ 非括号片段
    spans = _scan_brackets(rest)
    candidates = []
    for start, end in spans:
        innermost, leftovers = _split_nested(rest[start + 1:end - 1])
        candidates += innermost + leftovers
    plain_parts, last = [], 0
    for start, end in spans:
        plain_parts.append(rest[last:start])
        last = end
    plain_parts.append(rest[last:])
    # 主名：作者后、下一个括号前的内容原样保留；为空时取末尾残留
    if series_prefix:
        series_name = series_prefix
    else:
        series_raw = (plain_parts[0] if plain_parts else rest).strip()
        if not series_raw:
            series_raw = next((p.strip() for p in reversed(plain_parts) if p.strip()), "")
        series_name = _extract_inline_volume(series_raw)[0].strip()
    # 分类括号内容
    aliases, tags, extras = [], [], []
    vol_info = None
    total_volumes = 0
    complete = False
    vol_type = "连载"
    complete_hint = ongoing_hint = False
    for content in candidates:
        c = content.strip()
        if not c:
            continue
        if VOL_RE.search(c):
            vol_info = c
            nums = _extract_numbers(c)
            if nums:
                total_volumes = max(total_volumes, max(nums))
            if "+" in c:  # V02全+原画集 → 附加内容（可作 tag）
                for ep in (p.strip() for p in c.split("+")[1:]):
                    if ep:
                        extras.append(ep)
                        if ep not in tags:
                            tags.append(ep)
            if any(w in c.lower() for w in COMPLETE_WORDS):
                complete, vol_type = True, "已完结"
            else:
                complete, vol_type = False, "连载"
        elif c == "短篇":
            vol_info, total_volumes, vol_type, complete = c, 1, "短篇", False
        elif _is_tag_content(c):
            tags.append(c)
            low = c.lower()
            if any(w in low for w in _HINTS_COMPLETE):
                complete_hint = True
            if any(w in low for w in _HINTS_ONGOING):
                ongoing_hint = True
        else:
            aliases.append(c)
    # 非括号片段中的内联卷标（第01-12巻 / V01 / Vol.16 - Vol.17）
    inline_vol = None
    for part in plain_parts:
        _, vt, nums = _extract_inline_volume(part)
        if vt:
            inline_vol = inline_vol or vt
            for n in nums:
                total_volumes = max(total_volumes, n)
    if vol_info is None and inline_vol:
        vol_info = inline_vol
    # 完结判定：无「全/完结」字样 → 默认未完结（连载）
    if vol_info is None:
        if complete_hint and not ongoing_hint:
            complete, vol_type = True, "已完结"
        else:
            complete, vol_type = False, "连载"
    elif vol_type != "短篇" and complete_hint and not ongoing_hint:
        complete, vol_type = True, "已完结"
    elif vol_type != "短篇" and ongoing_hint:
        complete, vol_type = False, "连载"
    extras = list(dict.fromkeys(extras))
    aliases = list(dict.fromkeys(aliases))
    tags = list(dict.fromkeys(tags))
    return {
        "author": author,
        "series": series_name,
        "aliases": aliases,
        "tags": tags,
        "vol_info": vol_info,
        "total_volumes": total_volumes,
        "vol_type": vol_type,
        "complete": complete,
        "has_extras": bool(extras),
        "extras": "+".join(extras),
    }
