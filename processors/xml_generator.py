#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML生成器模块 - 负责生成ComicInfo.xml内容
"""

from typing import Any, Dict

from processors.xml_template_handler import XMLTemplateHandler


class XMLGenerator:
    """XML生成器类"""
    
    def __init__(self):
        """初始化生成器"""
        self.template_handler = XMLTemplateHandler()
    
    def generate_comicinfo_xml(self, comic_info: Dict[str, Any]) -> str:
        """生成ComicInfo.xml内容
        
        Args:
            comic_info: ComicInfo字典
            
        Returns:
            str: XML格式的字符串
        """
        xml_content = '''<?xml version="1.0"?>\n<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'''
        
                # 按特定顺序添加字段
        fields_order = [
            "Title", "Series", "Volume", "Number", "Count", "Summary", "Notes",
            "Year", "Month", "Writer", "Penciller", "Inker", "Colorist", "Letterer",
            "CoverArtist", "Editor", "Publisher", "Genre", "Web", "PageCount",
            "LanguageISO", "Format", "BlackAndWhite", "Manga", "AgeRating",
            "Tags", "Status", "Rating"
        ]
        
        for field in fields_order:
            value = comic_info.get(field, "")
            if value:
                xml_content += f'    <{field}>{self._escape_xml(value)}</{field}>\n'
        
        xml_content += '</ComicInfo>'
        return xml_content
    
    def generate_for_short_story(self, folder_info: Dict[str, Any]) -> str:
        """为短篇内容生成XML
        
        Args:
            folder_info: 文件夹信息字典
            
        Returns:
            str: XML内容字符串
        """
        template = self.template_handler.create_base_template(folder_info, is_short_story=True)
        return self.generate_comicinfo_xml(template)
    
    def generate_with_bangumi_data(self, bangumi_data: Dict[str, Any], folder_info: Dict[str, Any]) -> str:
        """使用Bangumi数据生成XML
        
        Args:
            bangumi_data: Bangumi数据字典
            folder_info: 文件夹信息字典
            
        Returns:
            str: XML内容字符串
        """
        template = self.template_handler.create_bangumi_template(bangumi_data, folder_info)
        return self.generate_comicinfo_xml(template)
    
    def generate_with_local_data(self, folder_info: Dict[str, Any]) -> str:
        """使用本地数据生成XML（搜索失败时使用）
        
        Args:
            folder_info: 文件夹信息字典
            
        Returns:
            str: XML内容字符串
        """
        template = self.template_handler.create_local_template(folder_info)
        return self.generate_comicinfo_xml(template)
    
    def generate_for_file(self, base_comic_info: Dict[str, Any], file_name: str, 
                         folder_info: Dict[str, Any]) -> str:
        """为单个文件生成XML
        
        Args:
            base_comic_info: 基础ComicInfo数据
            file_name: 文件名
            folder_info: 文件夹信息
            
        Returns:
            str: XML内容字符串
        """
        import re

        from parsers.file_parser import (generate_smart_title,
                                         parse_volume_from_filename)

        # 复制基础数据
        file_comic_info = base_comic_info.copy()
        
        # 生成智能标题
        smart_title_result = generate_smart_title(file_name, folder_info.get("series", ""), folder_info)
        smart_title = smart_title_result[0]  # 提取标题字符串
        
        # 判断文件类型：先尝试从文件名提取卷数信息
        file_vol_info = parse_volume_from_filename(file_name)
        
        # 如果能成功提取卷数信息，说明是单行本文件
        if file_vol_info['number'] and file_vol_info['number'].strip():
            # 普通卷数文件
            file_comic_info.update({
                "Title": smart_title,  # 使用智能生成的标题
                "Count": base_comic_info.get("Count", ""),  # 已完结填写总卷数，连载中留空
                "Volume": file_vol_info['number'],  # 单本书的卷数
                "Number": file_vol_info['number'],  # 新增：Number 与 Volume 同值
            })
        else:
            # 检查是否为单话文件（C01、C 01、第01话等）
            chapter_match = re.search(r'(C\s*\d+|第\s*\d+\s*话)', file_name, re.IGNORECASE)
            if chapter_match:
                # 单话文件，将序号写入Number字段
                chapter_text = chapter_match.group(1)
                # 提取数字部分
                number_match = re.search(r'\d+', chapter_text)
                if number_match:
                    file_comic_info.update({
                        "Title": smart_title,  # 使用智能生成的标题
                        "Number": number_match.group(),  # 单话编号
                        "Volume": "",  # 单话文件不显示Volume
                        "Status": "Ongoing"  # 单话文件视为已完结
                    })
                else:
                    # 无法提取数字，使用默认逻辑
                    file_comic_info.update({
                        "Title": smart_title,  # 使用智能生成的标题
                        "Volume": "",  # 非单行本内容不显示Volume
                        "Status": "Completed"  # 非单行本内容视为已完结
                    })
            else:
                # 无法识别为单行本或单话的文件（包括画集、设定集、番外等）
                file_comic_info.update({
                    "Title": smart_title,  # 使用智能生成的标题
                    "Volume": "",  # 非单行本内容不显示Volume
                    "Status": "Completed"  # 非单行本内容视为已完结
                })
            # 保留Count字段，如果整个系列已完结，应该显示总卷数
            # 只有当整个系列连载中时，Count字段才会为空
        
        return self.generate_comicinfo_xml(file_comic_info)
    
    def _escape_xml(self, text: str) -> str:
        """转义XML特殊字符
        
        Args:
            text: 需要转义的文本
            
        Returns:
            str: 转义后的文本
        """
        if not text:
            return text
        
        # 替换XML特殊字符
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&apos;'
        }
        
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        
        return text


def build_full_comicinfo_dict(result=None, **overrides) -> Dict[str, Any]:
    """构建完整的 ComicInfo 字典——所有写入路径共用此入口。

    基于 COMICINFO_TEMPLATE 确保所有字段都有默认值（Genre/Format/LanguageISO 等），
    然后通过 result 字典和关键字参数覆盖。

    Args:
        result: 扫描结果字典（可选），包含 series/count/writer/penciller/colorist/
                year/month/status/summary/tags/manga/publisher/bangumi_id 等字段
        **overrides: 单独覆盖的 ComicInfo 字段名（如 Title, Volume, Notes 等）

    Returns:
        Dict[str, Any]: 完整的 ComicInfo 字典（包含 COMICINFO_TEMPLATE 全部字段）
    """
    from config import COMICINFO_TEMPLATE

    info = COMICINFO_TEMPLATE.copy()

    if result:
        _apply_result_fields(info, result)

    if overrides:
        for k, v in overrides.items():
            if k in info:
                info[k] = v

    return info


def _apply_result_fields(info: Dict[str, Any], result: Dict[str, Any]) -> None:
    """将扫描结果字典的通用字段映射到 ComicInfo 字典（原地修改）。"""
    info["Title"] = result.get("series", "")
    info["Series"] = result.get("series", "")
    info["Count"] = str(result.get("count", "")) if result.get("count") else ""
    info["Writer"] = str(result.get("writer", ""))
    info["Penciller"] = str(result.get("penciller", ""))
    info["Colorist"] = str(result.get("colorist", ""))
    info["Year"] = str(result.get("year", "")) if result.get("year") else ""
    info["Month"] = str(result.get("month", "")) if result.get("month") else ""
    info["Status"] = str(result.get("status", ""))
    info["Summary"] = str(result.get("summary", ""))
    info["Tags"] = str(result.get("tags", ""))
    info["Manga"] = str(result.get("manga", "Yes"))
    info["Publisher"] = str(result.get("publisher", ""))
    if result.get("genre"):
        info["Genre"] = str(result.get("genre"))
    # Web 直接用结果 dict 的 web 字段（编辑/回读后可能被用户修改，不再按 source 拼 URL）
    if result.get("web"):
        info["Web"] = str(result.get("web"))


def create_xml_generator() -> XMLGenerator:
    """创建XML生成器实例
    
    Returns:
        XMLGenerator: XML生成器实例
    """
    return XMLGenerator()