#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选择器处理器模块 - 负责搜索结果的手动选择功能

支持 GUI 模式（通过 gui_bridge）和控制台模式。
"""

import re
from typing import Any, Dict, List, Literal, Optional

from config import SHOW_TOP_N
from models.bangumi_fetcher import BangumiFetcher
from processors.timeout_handler import TimeoutHandler
from processors.choice_handlers import create_choice_handlers


class SelectorHandler:
    """选择器处理器类"""

    def __init__(self, timeout_handler: Optional[TimeoutHandler] = None,
                 gui_bridge: Optional[Any] = None):
        """初始化选择器处理器

        Args:
            timeout_handler: 超时处理器实例，None则创建新的
            gui_bridge: GUI 对话框桥接器（DialogBridge实例），为None时使用 console input()
        """
        self.timeout_handler = timeout_handler or TimeoutHandler()
        self.fetcher = BangumiFetcher()
        self.choice_handlers = create_choice_handlers(self.fetcher)
        self.gui_bridge = gui_bridge

    def manual_select(self, search_results: List[Dict], folder_info: Dict,
                     alt_keywords: Optional[List[str]] = None) -> Optional[Dict] | Literal['use_local_info']:
        """手动选择Bangumi搜索结果

        Args:
            search_results: 搜索结果列表
            folder_info: 文件夹信息
            alt_keywords: 别名关键词列表

        Returns:
            dict: 选中的结果，或"use_local_info"，或None
        """
        if not search_results:
            return None

        # GUI 模式：使用对话框桥接器
        if self.gui_bridge:
            return self.gui_bridge.invoke('select_result',
                                          search_results=search_results,
                                          folder_info=folder_info,
                                          alt_keywords=alt_keywords)

        # 控制台模式
        print(f"\n📋 请选择匹配的作品（共{len(search_results)}个结果）:")
        print(f"💡 文件夹信息: 作者={folder_info['author']} | 系列={folder_info['series']}")
        print("=" * 80)
        
        # 显示搜索结果详情
        for i, result in enumerate(search_results):
            self._display_result_details(i, result, folder_info)
        
        # 显示选择提示
        self._display_selection_prompt(search_results, alt_keywords)
        
        # 获取用户选择
        choice = self._get_user_selection(search_results)
        
        # 处理用户选择
        result = self._process_user_choice(choice, search_results, folder_info, alt_keywords)
        return result  # 可能返回 'use_local_info' 或 Dict 或 None
    
    def _display_result_details(self, index: int, result: Dict, folder_info: Dict):
        """显示单个搜索结果的详细信息
        
        Args:
            index: 结果索引
            result: 搜索结果
            folder_info: 文件夹信息
        """
        # 获取基础信息
        title_cn = result.get("name_cn") or result.get("name", "未知标题")
        title_ori = result.get("name", "")
        score = result.get("rating", {}).get("score", 0)
        subject_id = result.get("id", "未知ID")
        
        # 获取详细信息
        detail = self.fetcher.get_manga_detail(subject_id)
        
        # 提取各种信息（persons 并入，跨端点合并去重）
        persons = self.fetcher.get_manga_persons(subject_id) if detail else []
        authors = self.fetcher.extract_bangumi_authors(detail, persons) if detail else []
        year = self._extract_year(detail)
        tags = self._extract_tags(detail)
        aliases = self._extract_aliases(detail)
        
        # 显示详细信息
        print(f"{index+1}. 🎯 [{subject_id}] {title_cn}")
        if title_ori and title_ori != title_cn:
            print(f"   📖 原名: {title_ori}")
        print(f"   ⭐ 评分: {score}/10 | 📅 年份: {year} | ✍️ 作者: {', '.join(authors) or '未知'}")
        if aliases:
            print(f"   🏷️  别名: {', '.join(aliases[:3])}")  # 最多显示3个别名
        if tags:
            print(f"   🏷️  标签: {', '.join(tags)}")
        
        # 显示匹配状态
        self._display_match_status(folder_info["author"], authors)
        
        print("-" * 80)
    
    def _extract_year(self, detail: Optional[Dict]) -> str:
        """从详细信息中提取年份
        
        Args:
            detail: Bangumi详细信息
            
        Returns:
            str: 年份信息
        """
        if not detail:
            return "未知"
        
        for item in detail.get("infobox", []):
            if item.get("key") in ["发售日", "开始"]:
                date_str = item.get("value", "")
                if isinstance(date_str, str) and date_str:
                    year_match = re.search(r'(\d{4})', date_str)
                    if year_match:
                        return year_match.group(1)
        
        return "未知"
    
    def _extract_tags(self, detail: Optional[Dict]) -> List[str]:
        """从详细信息中提取标签
        
        Args:
            detail: Bangumi详细信息
            
        Returns:
            List[str]: 标签列表
        """
        if not detail:
            return []
        
        bangumi_tags = detail.get("tags", [])
        return [tag["name"] for tag in bangumi_tags if tag.get("count", 0) >= 3][:5]
    
    def _extract_aliases(self, detail: Optional[Dict]) -> List[str]: 
        """从详细信息中提取别名
        
        Args:
            detail: Bangumi详细信息
            
        Returns:
            List[str]: 别名列表
        """
        if not detail:
            return []
        
        aliases = []
        infobox = detail.get("infobox", [])
        for item in infobox:
            if item.get("key") == "别名":
                value = item.get("value", [])
                if isinstance(value, list):
                    for alias in value:
                        if isinstance(alias, dict) and alias.get("v"):
                            aliases.append(alias["v"])
                elif isinstance(value, str) and value.strip():
                    aliases.append(value.strip())
                break
        
        return aliases
    
    def _display_match_status(self, folder_author: str, bangumi_authors: List[str]):
        """显示作者匹配状态
        
        Args:
            folder_author: 文件夹中的作者
            bangumi_authors: Bangumi作者列表
        """
        folder_author_upper = folder_author.upper()
        authors_upper = [author.upper() for author in bangumi_authors]
        
        # 检查是否有任何作者匹配（忽略大小写）
        has_match = False
        for author_upper in authors_upper:
            if any(word in author_upper for word in folder_author_upper.split()) or any(word in folder_author_upper for word in author_upper.split()):
                has_match = True
                break
        
        if has_match or self.fetcher.match_author(folder_author, bangumi_authors):
            print(f"   ✅ 作者匹配成功！")
        else:
            print(f"   ⚠️  作者不匹配: 文件夹[{folder_author}] vs Bangumi[{', '.join(bangumi_authors)}]")
    
    def _display_selection_prompt(self, search_results: List[Dict], alt_keywords: Optional[List[str]]):
        """显示选择提示
        
        Args:
            search_results: 搜索结果列表
            alt_keywords: 别名关键词列表
        """
        # 使用choice_handlers生成选择提示
        result_count = len(search_results) if search_results else 0
        prompt = self.choice_handlers.get_choice_prompt(bool(alt_keywords), result_count)
        print(prompt)
        
        if search_results and len(search_results) > 0:
            sample_id = search_results[0].get('id', '378725')
            print(f"\n💡 提示：Bangumi ID就是方括号里的数字，如[{sample_id}] → 输入id{sample_id}")
    
    def _get_user_selection(self, search_results: List[Dict]) -> Optional[str]:
        """获取用户选择
        
        Args:
            search_results: 搜索结果列表
            
        Returns:
            Optional[str]: 用户选择或None（超时）
        """
        # 添加超时处理
        timeout = self.timeout_handler.get_timeout_value()
        
        if timeout > 0:
            print(f"⏰ 等待时间: {timeout}秒，超时将自动选择第一个结果...")
            choice = self.timeout_handler.get_user_input("请输入您的选择: ")
            if choice is None:
                print("⏰ 等待超时，自动选择第一个结果")
                return "1"  # 自动选择第一个结果
            return choice
        else:
            # 无限等待
            return self.timeout_handler.get_user_input("\n请输入您的选择: ")
    
    def _process_user_choice(self, choice: Optional[str], search_results: List[Dict], 
                           folder_info: Dict, alt_keywords: Optional[List[str]], depth: int = 0) -> Optional[Dict] | Literal['use_local_info']:
        """处理用户选择
        
        Args:
            choice: 用户选择
            search_results: 搜索结果列表
            folder_info: 文件夹信息
            alt_keywords: 别名关键词列表
            depth: 当前深度
            
        Returns:
            Optional[Dict]: 处理结果
        """
        if choice is None:
            # 超时，自动选择第一个结果
            return search_results[0] if search_results else None
        
        # 解析用户选择
        choice_type, choice_param = self.choice_handlers.parse_choice(choice)
        
        # 处理选择项
        result, status = self.choice_handlers.process_choice(choice_type, choice_param, alt_keywords, depth)
        
        if status == 'id_search_success':
            return result
        elif status == 'alias_search_success':
            return result
        elif status == 'use_local_info':
            return 'use_local_info'  # 特殊返回值，指示使用本地信息
        elif status == 'series_skipped':
            return None
        elif status == 'number_selected':
            # 处理数字选择
            try:
                if choice_param is None:
                    print("❌ 选择参数为空")
                    return self.manual_select(search_results, folder_info, alt_keywords)  # 递归重试
                
                choice_idx = int(choice_param) - 1
                if 0 <= choice_idx < len(search_results):
                    selected = search_results[choice_idx]
                    print(f"  ✅ 您选择了: {selected.get('name_cn') or selected.get('name')}")
                    return selected
                else:
                    print(f"❌ 输入无效，请输入1-{len(search_results)}之间的数字")
                    return self.manual_select(search_results, folder_info, alt_keywords)  # 递归重试
            except ValueError:
                print("❌ 输入无效，请输入数字、id+数字、a或q")
                return self.manual_select(search_results, folder_info, alt_keywords)  # 递归重试
        else:
            # 无效选择，递归重试
            print("❌ 输入无效，请输入数字、id+数字、a或q")
            return self.manual_select(search_results, folder_info, alt_keywords)  # 递归重试
    

    
    def auto_select_first(self, search_results: List[Dict]) -> Optional[Dict]:
        """自动选择第一个结果
        
        Args:
            search_results: 搜索结果列表
            
        Returns:
            Optional[Dict]: 第一个结果或None
        """
        if search_results:
            selected = search_results[0]
            print(f"✅ 自动选择: {selected.get('name_cn') or selected.get('name')}")
            return selected
        return None


def create_selector_handler(timeout_handler: Optional[TimeoutHandler] = None,
                            gui_bridge: Optional[Any] = None) -> SelectorHandler:
    """创建选择器处理器实例

    Args:
        timeout_handler: 超时处理器实例，None则创建新的
        gui_bridge: GUI 对话框桥接器实例

    Returns:
        SelectorHandler: 选择器处理器实例
    """
    return SelectorHandler(timeout_handler, gui_bridge)