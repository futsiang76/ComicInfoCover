#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML模板处理器模块 - 负责XML模板的创建和数据填充
"""

import re
from typing import Any, Dict

from config import COMICINFO_TEMPLATE, SHORT_STORY_TEMPLATE


class XMLTemplateHandler:
    """XML模板处理器类"""
    
    def __init__(self):
        """初始化处理器"""
        pass
    
    def create_base_template(self, folder_info: Dict[str, Any], is_short_story: bool = False) -> Dict[str, Any]:
        """创建基础模板
        
        Args:
            folder_info: 文件夹信息字典
            is_short_story: 是否为短篇内容
            
        Returns:
            Dict[str, Any]: ComicInfo基础数据字典
        """
        # 根据 folder_info 自动判定短篇（宽松解析会写入 vol_type/vol_info/tags）
        is_short_story = is_short_story or (
            folder_info.get("vol_type") == "短篇"
            or folder_info.get("vol_info") == "短篇"
            or "短篇" in (folder_info.get("tags") or [])
        )

        if is_short_story:
            template = SHORT_STORY_TEMPLATE.copy()
        else:
            template = COMICINFO_TEMPLATE.copy()
        
        # 填充基础信息（短篇保留 SHORT_STORY_TEMPLATE 的 Tags）
        template.update({
            "Title": folder_info["series"],
            "Series": folder_info["series"],
            "Writer": folder_info["author"],
            "Penciller": folder_info["author"],  # Writer/Penciller 单向补齐
            "Summary": "",
            "Tags": "短篇" if is_short_story else "",
        })
        
        # 设置卷数信息
        if is_short_story:
            template.update({
                "Count": "1",  # 短篇 = 一卷全
                "Volume": "",  # 短篇不显示Volume
                "Status": "Completed"  # 短篇默认已完成
            })
        else:
            # 已完结填写总卷数，连载中留空
            # 检查是否为已完结状态（complete标志为True或vol_info包含"全"）
            is_completed = folder_info["complete"] or ("全" in (folder_info.get("vol_info") or ""))
            volume_value = str(folder_info["total_volumes"]) if is_completed else ""
            template.update({
                "Count": volume_value,  # 系列总卷数
                "Status": "Completed" if is_completed else "Ongoing"
            })
        
        return template
    
    def create_bangumi_template(self, bangumi_data: Dict[str, Any], folder_info: Dict[str, Any]) -> Dict[str, Any]:
        """创建Bangumi数据模板
        
        Args:
            bangumi_data: Bangumi数据字典
            folder_info: 文件夹信息字典
            
        Returns:
            Dict[str, Any]: 填充Bangumi数据的ComicInfo字典
        """
        template = self.create_base_template(folder_info)
        
        # 填充Bangumi数据
        template.update({
            "Title": bangumi_data.get("name_cn") or bangumi_data.get("name") or folder_info["series"],
            "Series": bangumi_data.get("name_cn") or bangumi_data.get("name") or folder_info["series"],
            "Summary": bangumi_data.get("summary", ""),
            "Web": f"https://bgm.tv/subject/{bangumi_data['id']}" if bangumi_data.get("id") else ""
        })
        
        # 处理作者信息 - 使用BangumiFetcher的方法（infobox + persons 两端点合并）
        from models.bangumi_fetcher import BangumiFetcher, extract_bangumi_genre
        from models.author_utils import extract_bangumi_authors_merged
        from models.bangumi_genre import extract_bangumi_aliases
        fetcher = BangumiFetcher()

        # persons 端点每次都调（与 infobox 一起），失败静默返回 []
        subject_id = bangumi_data.get("id")
        persons = fetcher.get_manga_persons(int(subject_id)) if subject_id else []

        # 两端点合并分类：Writer=原作/脚本/监督/导演/原著，Penciller=作者/作画/插画，
        # Colorist=上色/色彩；同名跨端点去重（优先 infobox 映射）
        fields = extract_bangumi_authors_merged(bangumi_data, persons)
        story_authors = fields["Writer"]
        art_authors = fields["Penciller"]
        color_authors = fields["Colorist"]

        # 应用规则（Writer/Penciller 单向补齐：无画师时画师填原作，反之亦然）
        if not story_authors and not art_authors:
            # 没有任何作者信息，使用文件夹作者，同时填充Writer和Penciller
            template["Writer"] = folder_info["author"]
            template["Penciller"] = folder_info["author"]
        elif not story_authors and art_authors:
            # 只有绘画作者，同时填充Writer和Penciller
            template["Writer"] = ", ".join(art_authors)
            template["Penciller"] = ", ".join(art_authors)
        elif story_authors and not art_authors:
            # 只有故事作者，同时填充Writer和Penciller
            template["Writer"] = ", ".join(story_authors)
            template["Penciller"] = ", ".join(story_authors)
        else:
            # 同时有故事作者和绘画作者，分别放入对应字段
            template["Writer"] = ", ".join(story_authors)
            template["Penciller"] = ", ".join(art_authors)
        template["Colorist"] = ", ".join(color_authors)
        
        # 处理标签（复用 bangumi_fetcher 的 Genre 白名单 + Tags 截断逻辑）
        genre_str = extract_bangumi_genre(bangumi_data)
        template["Genre"] = genre_str

        if bangumi_data.get("tags"):
            genre_tags = set(genre_str.split(", "))
            # 截断 + 移除 Genre 命中词（与 bangumi_fetcher 的 Tags 逻辑一致）
            tags = [tag["name"] for tag in bangumi_data["tags"] if tag.get("count", 0) >= 2][:10]
            tags = [t for t in tags if t not in genre_tags]
            tags = [t for t in tags if not re.match(r"^\d+$", t)]  # 去掉纯数字（如 2024）
            remaining = list(tags)
            # 追加系列别名（infobox「别名」+ 日文原名）；与 Genre 词重复的别名同样剔除
            remaining.extend(a for a in extract_bangumi_aliases(bangumi_data) if a not in genre_tags)
            remaining.append(template.get("Status", ""))
            template["Tags"] = ", ".join(dict.fromkeys(remaining))
        
        # 处理年份信息
        if bangumi_data.get("date"):
            year_month = self._extract_year_month(bangumi_data["date"])
            template.update(year_month)
        
        return template
    
    def create_local_template(self, folder_info: Dict[str, Any]) -> Dict[str, Any]:
        """创建本地数据模板（搜索失败时使用）
        
        Args:
            folder_info: 文件夹信息字典
            
        Returns:
            Dict[str, Any]: 使用本地数据的ComicInfo字典
        """
        template = self.create_base_template(folder_info)
        
        # 处理多作者情况（复用 author_utils._split_authors 统一拆分入口）
        from models.author_utils import _split_authors
        author = folder_info["author"]
        authors = _split_authors(author) or [author.strip()]

        # 当不确定作者角色时，将所有作者都放在Writer和Penciller字段中
        all_authors = ", ".join(authors)
        
        # 使用文件夹信息填充（Tags 沿用 create_base_template 的结果，短篇保留"短篇"）
        template.update({
            "Title": folder_info["series"],
            "Series": folder_info["series"],
            "Writer": all_authors,  # Writer字段包含所有作者
            "Penciller": all_authors,  # Penciller字段也包含所有作者
            "Summary": "",
            "Web": "",
            "Rating": ""
        })
        
        return template
    
    def _extract_authors_from_infobox(self, infobox_data: list) -> Dict[str, str]:
        """从infobox数据中提取作者信息（与作者匹配逻辑保持一致）
        
        Args:
            infobox_data: infobox数据列表
            
        Returns:
            Dict[str, str]: 作者信息字典
        """
        authors = {
            "Writer": "",      # 编剧
            "Penciller": "",   # 画师
            "Inker": "",      # 墨线师
            "Colorist": "",   # 上色师
            "Letterer": "",   # 字母师
            "CoverArtist": "", # 封面画师
            "Editor": ""      # 编辑
        }
        
        # 收集所有作者信息
        all_authors = []
        
        # 定义作者类型映射（与作者匹配逻辑保持一致）
        author_type_mapping = {
            "原作": "Writer",      # 原作 → Writer
            "作者": "Penciller",   # 作者 → Penciller（Bangumi中的"作者"实际上是作画者）
            "作画": "Penciller",   # 作画 → Penciller
            "脚本": "Writer",      # 脚本 → Writer
            "监督": "Writer",      # 监督 → Writer
            "导演": "Writer",      # 导演 → Writer
            "原著": "Writer",      # 原著 → Writer
            "插画": "Penciller",   # 插画 → Penciller
            "墨线": "Inker",      # 墨线 → Inker
            "上色": "Colorist",   # 上色 → Colorist
            "字母": "Letterer",   # 字母 → Letterer
            "封面": "CoverArtist", # 封面 → CoverArtist
            "编辑": "Editor"      # 编辑 → Editor
        }
        
        for item in infobox_data:
            key = item.get("key", "")
            value = item.get("value", "")
            
            if key in author_type_mapping:
                target_field = author_type_mapping[key]
                
                # 处理不同类型的值格式
                if isinstance(value, list):
                    # 列表格式：提取所有作者名
                    for v in value:
                        if isinstance(v, dict) and v.get("v"):
                            author_name = v["v"].strip()
                            if author_name:
                                authors[target_field] = self._append_author(authors[target_field], author_name)
                                if author_name not in all_authors:
                                    all_authors.append(author_name)
                        elif isinstance(v, str):
                            author_name = v.strip()
                            if author_name:
                                authors[target_field] = self._append_author(authors[target_field], author_name)
                                if author_name not in all_authors:
                                    all_authors.append(author_name)
                elif isinstance(value, str):
                    # 字符串格式：直接添加
                    author_name = value.strip()
                    if author_name:
                        authors[target_field] = self._append_author(authors[target_field], author_name)
                        if author_name not in all_authors:
                            all_authors.append(author_name)
        
        # 应用作者分配规则
        # 规则1: 如果只有一个作者A，则Writer和Penciller都填A（ComicInfo XML 无 Author 字段）
        if len(all_authors) == 1:
            single_author = all_authors[0]
            authors["Writer"] = single_author
            authors["Penciller"] = single_author
        
        # 规则2: 如果只有Penciller没有Writer，则Writer也填Penciller（两个都填同一个人）
        elif authors["Penciller"] and not authors["Writer"]:
            authors["Writer"] = authors["Penciller"]

        # 兜底: Writer 和 Penciller 单向补齐（覆盖剩余分支，如只有 Writer 无 Penciller）
        if authors["Writer"] and not authors["Penciller"]:
            authors["Penciller"] = authors["Writer"]
        elif authors["Penciller"] and not authors["Writer"]:
            authors["Writer"] = authors["Penciller"]

        return authors
    
    def _extract_year_month(self, date_str: str) -> Dict[str, str]:
        """从日期字符串中提取年份和月份
        
        Args:
            date_str: 日期字符串
            
        Returns:
            Dict[str, str]: 年份和月份字典
        """
        # 惰性导入：xml_generator 模块级 import 本模块，此处不能再反向模块级 import
        from processors.xml_generator import clean_month, clean_year

        year_month = {"Year": "", "Month": ""}

        if date_str:
            # 尝试解析日期格式：YYYY-MM-DD（Year/Month 再经清洗，防「年」等非数字字符）
            parts = date_str.split("-")
            if len(parts) >= 1:
                year_month["Year"] = clean_year(parts[0])
            if len(parts) >= 2:
                year_month["Month"] = clean_month(parts[1])

        return year_month
    
    def _append_author(self, current_authors: str, new_author: str) -> str:
        """追加作者到现有作者列表
        
        Args:
            current_authors: 当前作者列表
            new_author: 新作者
            
        Returns:
            str: 更新后的作者列表
        """
        if not current_authors:
            return new_author
        else:
            return f"{current_authors}, {new_author}"


def create_xml_template_handler() -> XMLTemplateHandler:
    """创建XML模板处理器实例
    
    Returns:
        XMLTemplateHandler: XML模板处理器实例
    """
    return XMLTemplateHandler()