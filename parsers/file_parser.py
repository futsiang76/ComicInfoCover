#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件名解析模块 - 处理文件名解析
"""

import os
import re
from typing import Dict, Optional


def parse_filename_info(filename: str) -> Optional[Dict]:
    """从不规范的文件名中提取作者和作品名信息
    
    格式: [作者] 作品名 [DL版] 或者 [作者] 作品名 [中文翻译] 等
    提取末尾的[DL版]、[中文翻译]等标记作为tags
    """
    # 移除文件扩展名
    base_name = os.path.splitext(filename)[0]
    
    # 匹配 [作者] 作品名 的格式，兼容作者[]后没有空格的情况
    match = re.match(r'^\[(.+?)\]\s*(.+?)(?:\s*\[.+?\])*$', base_name.strip())
    if not match:
        return None
    
    author = match.group(1).strip()
    series_part = match.group(2).strip()

    # 提取所有标签信息
    tags = []
    # 查找所有 [标签] 格式的内容
    tag_matches = re.findall(r'\[(.*?)\]', base_name)
    # 过滤掉作者标签（第一个标签）
    if tag_matches:
        tags = tag_matches[1:]  # 第一个是作者，后面的是标签
    
    # 清理系列名末尾的标签
    series = re.sub(r'\s*\[.+?\]$', '', series_part).strip()
    
    return {
        "author": author,
        "series": series,
        "tags": tags
    }

def parse_volume_from_filename(filename: str) -> Dict[str, str]:
    """从zip/cbz文件名中提取卷数信息"""
    # 移除文件扩展名
    base_name = os.path.splitext(filename)[0]
    
    # 匹配模式1: Vol 01, Vol. 01, Vol1 等格式
    vol_match = re.search(r'Vol\.?\s*(\d+)', base_name, re.IGNORECASE)
    if vol_match:
        return {
            "vol": f"V{vol_match.group(1).zfill(2)}",
            "volume_num": vol_match.group(1).zfill(2),
            "number": vol_match.group(1).zfill(2)
        }
    
    # 匹配模式2: 第01卷, 第1卷 等中文卷数格式
    volume_match = re.search(r'第\s*(\d+)\s*卷', base_name)
    if volume_match:
        return {
            "vol": f"V{volume_match.group(1).zfill(2)}",
            "volume_num": volume_match.group(1).zfill(2),
            "number": volume_match.group(1).zfill(2)
        }
    
    # 匹配模式3: 第01话, 第1话 等中文话数格式
    chapter_match = re.search(r'第\s*(\d+)\s*[话話]', base_name)
    if chapter_match:
        # 单话文件，不返回卷数信息
        return {
            "vol": "",
            "volume_num": "",
            "number": ""
        }
    
    # 匹配模式4: C01, C 01, C1 等单话格式
    c_match = re.search(r'C\s*(\d+)', base_name, re.IGNORECASE)
    if c_match:
        # 单话文件，不返回卷数信息
        return {
            "vol": "",
            "volume_num": "",
            "number": ""
        }
    
    # 匹配模式3: 直接数字开头或结尾
    number_match = re.search(r'(?:^|[^\d])(\d{1,3})(?:[^\d]|$)', base_name)
    if number_match and int(number_match.group(1)) <= 100:  # 限制合理范围
        return {
            "vol": f"V{number_match.group(1).zfill(2)}",
            "volume_num": number_match.group(1).zfill(2),
            "number": number_match.group(1).zfill(2)
        }
    
    # 默认返回（无法识别卷数）
    return {
        "vol": "",
        "volume_num": "",
        "number": ""
    }

def is_short_story_folder(folder_info: Dict) -> bool:
    """判断文件夹是否为短篇（短篇完结）。

    folder_info 来自 parse_folder_name_lenient（vol_type/vol_info/tags 字段），
    或 result 字典（tags 为逗号分隔字符串，short_story 布尔标记）。
    判定：
    - vol_type/vol_info 为「短篇」→ 短篇
    - tags 含精确「短篇」→ 短篇（覆盖 (V01全 短篇) 等卷分支短篇进 tags 的情况）
    - 无卷号时 tags 以「短篇」开头（短篇全/短篇集/短篇+xxx）→ 短篇变体
    - 有卷号的多卷系列（如 V10全 短篇集）不误判
    """
    if folder_info.get("vol_type") == "短篇" or folder_info.get("vol_info") == "短篇":
        return True
    if folder_info.get("short_story"):
        return True
    tags = folder_info.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    tags = [str(t) for t in tags if str(t).strip()]
    if "短篇" in tags:
        return True
    vol_info = folder_info.get("vol_info") or ""
    return not vol_info and any(t.startswith("短篇") for t in tags)


def generate_smart_title(filename: str, series_name: str, folder_info: Dict) -> tuple[str, bool]:
    """根据文件名智能生成Title
    
    规则：
    1. Vol 01.zip, V01.zip, 第1卷.zip → "Vol 01"
    2. Vol 01 + 描述文字.zip → "Vol 01 描述文字"
    3. C01.zip, 第01话.zip → "C 01"
    4. 短篇文件夹（(短篇)/(V01全 短篇)/(短篇全)）→ "系列名.短篇完结"
    5. 番外、设定集、其它不是单行本Vol或卷的，引用文件名。
    
    返回值：
    返回一个元组：(标题, 是否是非单行本内容)
    非单行本包括：画集、设定集、番外、外传、特典、附录等
    """
    base_name = os.path.splitext(filename)[0]
    
    # 检查是否为非单行本内容（画集、设定集、番外等）
    non_volume_keywords = ['画集', '设定集', '设定', '番外', '外传', '外伝', '特典', '附录', '资料集', '画集', '插画集', '原画集']
    is_non_volume = any(keyword in base_name for keyword in non_volume_keywords)
    
    # 规则0: 短篇完结 —— 文件夹解析为短篇（(短篇)/(V01全 短篇)/(短篇全) 等）→ 「系列名.短篇完结」
    # 与规则1的 (V01全) → 「系列名.单卷完结」对齐；短篇=一篇完，Title 带后缀（幂等），Series 保持裸名
    if is_short_story_folder(folder_info):
        if series_name.endswith(".短篇完结"):
            return series_name, is_non_volume
        return f"{series_name}.短篇完结", is_non_volume
    
    # 规则1: 单行本格式 - Vol 01, V01, 第1卷等
    vol_match = re.search(r'(Vol\.?\s*\d+|V\d+|第\s*\d+\s*卷)', base_name, re.IGNORECASE)
    if vol_match:
        vol_text = vol_match.group(1)
        # 规范化格式
        if vol_text.upper().startswith('VOL'):
            match = re.search(r'\d+', vol_text)
            if match:
                vol_text = 'Vol ' + match.group().zfill(2)
            else:
                vol_text = 'Vol 01'  # 默认值
        elif vol_text.upper().startswith('V') and len(vol_text) > 1:
            vol_text = 'Vol ' + vol_text[1:].zfill(2)
        elif '卷' in vol_text:
            match = re.search(r'\d+', vol_text)
            if match:
                vol_text = 'Vol ' + match.group().zfill(2)
            else:
                vol_text = 'Vol 01'  # 默认值
        
        # 获取Vol后面的所有文本（包括描述文字）
        vol_end_pos = vol_match.end()
        after_vol_text = base_name[vol_end_pos:].strip()
        
        # 特殊处理：如果文件名包含(V01全)、(Vol01全)、(Vol 01全)等模式
        full_volume_pattern = r'\(V\d+全\)|\(Vol\d+全\)|\(Vol\s*\d+全\)'
        if re.search(full_volume_pattern, base_name):
            # 直接使用"系列名.单卷完结"格式
            return f"{series_name}.单卷完结", is_non_volume
        
        # 特殊处理：单卷完结 + 括号内补充信息（如 (V01全 缺Part2-3)）→ 同样视为单卷完结
        # 括号内以「V0*1全 / Vol 0*1全」（数字=1，单卷）开头，其后补充信息（缺卷说明等）不进 Title
        single_vol_supplement_pattern = r'\(V0*1全[^)]*\)|\(Vol\s*0*1全[^)]*\)'
        if re.search(single_vol_supplement_pattern, base_name):
            return f"{series_name}.单卷完结", is_non_volume
        
        # 剥离括号内容：括号内补充信息（缺卷说明/标签等）不进 Title
        # 覆盖两种形态：卷号被括号包住（如 (V03全 缺V2)），或括号在卷号之后（如 Vol 01 (描述)）
        if after_vol_text:
            paren_start = base_name.rfind('(', 0, vol_match.start())
            if paren_start != -1:
                paren_end = base_name.find(')', vol_match.end())
                if paren_end != -1:
                    # 卷号位于括号内（如 (V03全 缺V2)）→ 剔除整个括号内容，只留括号后的文字
                    after_vol_text = base_name[paren_end + 1:].strip()
            after_vol_text = re.sub(r'\([^)]*\)', '', after_vol_text).strip()
        
        # 如果Vol后面有非括号的内容，保留它
        if after_vol_text and not re.match(r'^\[.*?\]$', after_vol_text):
            return f"{vol_text} {after_vol_text}", is_non_volume
        else:
            return vol_text, is_non_volume
    
    # 规则2: 单话格式 - C01, 第01话等
    chapter_match = re.search(r'(C\d+|第\s*\d+\s*话)', base_name, re.IGNORECASE)
    if chapter_match:
        chapter_text = chapter_match.group(1)
        # 规范化格式
        if chapter_text.upper().startswith('C'):
            chapter_text = 'C ' + chapter_text[1:].zfill(2)
        elif '话' in chapter_text:
            # 保留原有的中文格式，不强制转换为C格式
            match = re.search(r'\d+', chapter_text)
            if match:
                # 保持"第XX话"的格式
                chapter_text = '第' + match.group() + '话'
            else:
                # 无法提取数字，使用原始文件名
                return base_name, is_non_volume

        # 提取C02后面的描述文字
        after_chapter_match = re.search(r'(C\d+|第\s*\d+\s*话)(.*)', base_name, re.IGNORECASE)
        if after_chapter_match and after_chapter_match.group(2).strip():
            after_text = after_chapter_match.group(2).strip()
            # 如果后面有非括号的内容，保留它
            if after_text and not re.match(r'^\[.*?\]$', after_text):
                return f"{chapter_text} {after_text}", is_non_volume        
        
        return chapter_text, is_non_volume
    
    # 规则3: 番外、设定集等额外内容
    extra_keywords = ['番外', '设定集', '设定', '外传', '外伝', '特典', '附录', '资料集', '画集', '插画集', '原画集']
    for keyword in extra_keywords:
        if keyword in base_name:
            return base_name, True  # 明确标记为非单行本
    
    # 规则4: 其他情况 - 使用文件名
    # 如果文件名包含作者信息，移除作者信息部分
    clean_name = re.sub(r'^\[.*?\]\s*', '', base_name).strip()
    if clean_name:
        return clean_name, is_non_volume
    else:
        return base_name, is_non_volume

def parse_folder_from_filename(folder_path: str) -> Optional[Dict]:
    """当文件夹命名不规范时，尝试从文件名提取信息"""
    try:
        # 获取文件夹下的第一个zip/cbz文件
        files = os.listdir(folder_path)
        zip_files = [f for f in files if f.lower().endswith(('.zip', '.cbz', '.cbr', '.rar'))]

        if not zip_files:
            return None

        # 使用第一个zip文件提取信息
        first_file = zip_files[0]
        file_info = parse_filename_info(first_file)

        if not file_info:
            return None

        # 从文件名提取信息，不打印日志
        # 文件名只有单卷信息，不能判定已完结 → complete=False（未完结语义）
        return {
            "author": file_info["author"],
            "series": file_info["series"],
            "vol_info": "V01",
            "total_volumes": 1,
            "vol_type": "连载",
            "complete": False,
            "has_extras": False,
            "extras": "",
            "from_filename": True
        }
    except Exception as e:
        print(f"❌ 从文件名提取信息失败: {str(e)}")
        return None


def parse_folder_tags_from_name(folder_name: str) -> list:
    """从文件夹名中提取 [ ] 内的标签信息

    规则：
    - 出现在 (V\\d+全) 之前的 [ ] 内容都视作标签
    - 分隔符 × 保持原样
    - 示例：
      \"[武井宏之] 通灵王 (V35全)\" → [\"武井宏之\"]
      \"[武井宏之×xxx] 作品名 (V05全)\" → [\"武井宏之×xxx\"]
      \"[武井宏之] 通灵王 [DL版] (V35全)\" → [\"武井宏之\", \"DL版\"]
    """
    # 截取 (V\\d+全) 之前的部分
    vol_match = re.search(r'\(V\d+全\)', folder_name)
    if vol_match:
        prefix = folder_name[:vol_match.start()]
    else:
        prefix = folder_name

    # 提取所有 [内容]
    tags = re.findall(r'\[([^\]]+)\]', prefix)
    return [t.strip() for t in tags if t.strip()]