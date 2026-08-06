#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选择项处理器模块 - 统一处理各种选择项功能

处理的选择项包括：
- ID查询：按Bangumi ID直接查找
- 别名查询：使用别名重新搜索
- 跳过系列：跳过当前系列
- 本地写入：按本地解析信息写入
"""

from typing import Dict, List, Optional, Tuple
from models.bangumi_fetcher import BangumiFetcher


class ChoiceHandlers:
    """选择项处理器类"""
    
    def __init__(self, fetcher: BangumiFetcher):
        """初始化选择项处理器
        
        Args:
            fetcher: Bangumi获取器实例
        """
        self.fetcher = fetcher
    
    def handle_id_search(self, id_input: str, depth: int = 0) -> Tuple[Optional[Dict], bool]:
        """处理ID查询选择项
        
        Args:
            id_input: 用户输入的ID字符串
            depth: 当前深度（用于缩进显示）
            
        Returns:
            Tuple[Optional[Dict], bool]: (搜索结果, 是否成功)
        """
        try:
            subject_id = int(id_input)
            print(f"{'  ' * depth}🔍 正在按Bangumi ID查找: {subject_id}")
            
            # 直接获取该ID的详情
            detail = self.fetcher.get_manga_detail(subject_id)
            if detail:
                # 创建简化的结果格式
                result = {
                    "id": subject_id,
                    "name": detail.get("name", ""),
                    "name_cn": detail.get("name_cn", ""),
                    "rating": detail.get("rating", {})
                }
                print(f"{'  ' * depth}  ✅ ID查找成功: {result.get('name_cn') or result.get('name')}")
                return result, True
            else:
                print(f"{'  ' * depth}❌ 未找到ID为 {subject_id} 的作品")
                return None, False
        except ValueError:
            print(f"{'  ' * depth}❌ ID格式错误，请输入数字")
            return None, False
    
    def handle_alias_search(self, alt_keywords: Optional[List[str]], depth: int = 0) -> Tuple[Optional[List[Dict]], bool]:
        """处理别名查询选择项
        
        Args:
            alt_keywords: 别名关键词列表
            depth: 当前深度（用于缩进显示）
            
        Returns:
            Tuple[Optional[List[Dict]], bool]: (搜索结果列表, 是否成功)
        """
        if not alt_keywords:
            print(f"{'  ' * depth}❌ 没有可用的别名关键词")
            return None, False
        
        print(f"{'  ' * depth}🔄 尝试使用别名重新搜索...")
        
        search_results = []
        for alt_keyword in alt_keywords:
            print(f"{'  ' * depth}🔍 使用别名搜索: {alt_keyword}")
            temp_results = self.fetcher.search_manga(alt_keyword)
            if temp_results:
                search_results = temp_results
                print(f"{'  ' * depth}✅ 使用别名 '{alt_keyword}' 找到 {len(search_results)} 个结果")
                return search_results, True
            else:
                print(f"{'  ' * depth}❌ 别名 '{alt_keyword}' 未找到结果")
        
        print(f"{'  ' * depth}❌ 所有别名搜索都失败")
        return None, False
    
    def handle_skip_series(self, depth: int = 0) -> Tuple[None, bool]:
        """处理跳过系列选择项
        
        Args:
            depth: 当前深度（用于缩进显示）
            
        Returns:
            Tuple[None, bool]: (None, 跳过成功)
        """
        print(f"{'  ' * depth}⏭️  跳过此系列")
        return None, True
    
    def handle_local_write(self, folder_info: Dict, depth: int = 0) -> Tuple[Dict, bool]:
        """处理按本地解析信息写入选择项
        
        Args:
            folder_info: 文件夹信息
            depth: 当前深度（用于缩进显示）
            
        Returns:
            Tuple[Dict, bool]: (本地数据模板, 是否成功)
        """
        print(f"{'  ' * depth}📝 按本地解析信息写入")
        
        # 创建本地数据模板
        local_data = {
            "title": folder_info.get("series", ""),
            "authors": [folder_info.get("author", "")] if folder_info.get("author") else [],
            "volumes": folder_info.get("total_volumes", 0),
            "is_completed": folder_info.get("is_completed", False),
            "is_oneshot": folder_info.get("is_oneshot", False),
            "is_local": True  # 标记为本地数据
        }
        
        print(f"{'  ' * depth}📊 本地信息: 系列名={local_data['title']}, 作者={local_data['authors']}, 卷数={local_data['volumes']}")
        
        return local_data, True
    
    def validate_id_input(self, id_input: str) -> Tuple[bool, Optional[int]]:
        """验证ID输入格式
        
        Args:
            id_input: 用户输入的ID字符串
            
        Returns:
            Tuple[bool, Optional[int]]: (是否有效, 解析后的ID)
        """
        if not id_input.strip():
            return False, None
        
        try:
            subject_id = int(id_input)
            return True, subject_id
        except ValueError:
            return False, None
    
    def validate_choice(self, choice: str, valid_choices: List[str]) -> bool:
        """验证用户选择是否有效
        
        Args:
            choice: 用户选择
            valid_choices: 有效选择列表
            
        Returns:
            bool: 选择是否有效
        """
        return choice in valid_choices
    
    def get_choice_prompt(self, has_aliases: bool = False, result_count: int = 0) -> str:
        """获取选择提示信息
        
        Args:
            has_aliases: 是否有可用的别名
            result_count: 搜索结果的数量
            
        Returns:
            str: 选择提示信息
        """
        prompt = "\n💡 选择提示:"
        if result_count > 0:
            prompt += f"\n   • 输入数字 1-{result_count} 选择对应作品"
        else:
            prompt += "\n   • 输入数字选择对应作品（暂无结果）"
        prompt += "\n   • 输入 'id' + 数字（如：id378725）直接按Bangumi ID查找"
        
        if has_aliases:
            prompt += "\n   • 输入 'a' 使用别名重新搜索"
        
        prompt += "\n   • 输入 'l' 使用本地信息写入XML"
        prompt += "\n   • 输入 'q' 跳过此系列"
        
        return prompt
    
    def parse_choice(self, choice: str) -> Tuple[str, Optional[str]]:
        """解析用户选择
        
        Args:
            choice: 用户输入的选择
            
        Returns:
            Tuple[str, Optional[str]]: (选择类型, 参数)
        """
        choice = choice.strip().lower()
        
        if choice.startswith('id') and len(choice) > 2:
            return 'id', choice[2:].strip()
        elif choice == 'a':
            return 'alias', None
        elif choice == 'l':
            return 'local', None
        elif choice == 'q':
            return 'skip', None
        elif choice.isdigit():
            return 'number', choice
        else:
            return 'invalid', None
    
    def process_choice(self, choice_type: str, choice_param: Optional[str], 
                      alt_keywords: Optional[List[str]], depth: int = 0) -> Tuple[Optional[Dict], str]:
        """处理用户选择
        
        Args:
            choice_type: 选择类型
            choice_param: 选择参数
            alt_keywords: 别名关键词列表
            depth: 当前深度
            
        Returns:
            Tuple[Optional[Dict], str]: (处理结果, 状态)
        """
        if choice_type == 'id':
            if choice_param:
                result, success = self.handle_id_search(choice_param, depth)
                return result, 'id_search_success' if success else 'id_search_failed'
            else:
                return None, 'id_param_missing'
        
        elif choice_type == 'alias':
            results, success = self.handle_alias_search(alt_keywords, depth)
            if success and results:
                # 返回第一个结果
                return results[0], 'alias_search_success'
            else:
                return None, 'alias_search_failed'
        
        elif choice_type == 'local':
            print(f"{'  ' * depth}📝 使用本地信息写入XML")
            return None, 'use_local_info'
        
        elif choice_type == 'skip':
            self.handle_skip_series(depth)
            return None, 'series_skipped'
        
        elif choice_type == 'number':
            # 数字选择由调用方处理
            return None, 'number_selected'
        
        else:
            return None, 'invalid_choice'


def create_choice_handlers(fetcher: BangumiFetcher) -> ChoiceHandlers:
    """创建选择项处理器实例
    
    Args:
        fetcher: Bangumi获取器实例
        
    Returns:
        ChoiceHandlers: 选择项处理器实例
    """
    return ChoiceHandlers(fetcher)