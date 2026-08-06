#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互处理器模块 - 负责用户交互功能

使用timeout_handler模块统一管理超时逻辑。
支持 GUI 模式（通过 gui_bridge）和控制台模式。
"""

from typing import Any, Dict, List, Optional

from processors.timeout_handler import TimeoutHandler


class InteractionHandler:
    """交互处理器类"""

    def __init__(self, timeout_handler: Optional[TimeoutHandler] = None,
                 gui_bridge: Optional[Any] = None):
        """初始化交互处理器

        Args:
            timeout_handler: 超时处理器实例，None则创建新的
            gui_bridge: GUI 对话框桥接器（DialogBridge实例），为None时使用 console input()
        """
        self.timeout_handler = timeout_handler or TimeoutHandler()
        self.gui_bridge = gui_bridge

    def get_user_input(self, prompt: str, timeout: Optional[int] = None) -> Optional[str]:
        """获取用户输入，支持超时

        Args:
            prompt: 提示信息
            timeout: 超时时间（秒），None表示使用默认配置

        Returns:
            Optional[str]: 用户输入或None（超时）
        """
        if self.gui_bridge:
            return self.gui_bridge.invoke('get_text', title='输入', prompt=prompt)
        return self.timeout_handler.get_user_input(prompt, timeout)

    def get_user_choice(self, prompt: str, valid_choices: List[str],
                       timeout: Optional[int] = None) -> Optional[str]:
        """获取用户选择，支持超时和输入验证

        Args:
            prompt: 提示信息
            valid_choices: 有效选择列表
            timeout: 超时时间（秒），None表示使用默认配置

        Returns:
            Optional[str]: 用户选择或None（超时/无效输入）
        """
        if self.gui_bridge:
            result = self.gui_bridge.invoke('get_text', title='选择', prompt=prompt)
            if result and result.strip() in valid_choices:
                return result.strip()
            return None
        return self.timeout_handler.get_user_choice(prompt, valid_choices, timeout)

    def handle_search_failure(self, folder_info: Dict[str, Any], alt_keywords: List[str],
                             depth: int = 0) -> Dict[str, Any]:
        """处理搜索失败的用户交互

        Args:
            folder_info: 文件夹信息
            alt_keywords: 别名关键词列表
            depth: 当前深度（用于缩进显示）

        Returns:
            Dict[str, Any]: 处理结果，包含选择信息和跳过标志
        """
        if self.gui_bridge:
            choice = self.gui_bridge.invoke('search_failure',
                                            folder_info=folder_info,
                                            alt_keywords=alt_keywords)
            action = choice.get('action', 'skip')
            if action == 'id_search':
                return {"choice": "1", "skip_files": False, "selected_result": None,
                        "_gui_value": choice.get('value')}
            elif action == 'keyword_search':
                return {"choice": "2", "skip_files": False, "selected_result": None,
                        "_gui_value": choice.get('value')}
            elif action == 'use_local_info':
                return {"choice": "local_write", "skip_files": False, "selected_result": None}
            else:
                return {"choice": "4", "skip_files": True, "selected_result": None}

        result = {
            "choice": None,
            "skip_files": False,
            "selected_result": None
        }

        print(f"{'  ' * depth}❌ 所有关键词搜索失败")
        print(f"{'  ' * depth}💡 文件夹信息: 作者={folder_info['author']} | 系列={folder_info['series']}")

        # 提供用户选项
        print()
        print(f"{'  ' * depth}🔧 请选择操作:")
        print(f"{'  ' * depth}   1. 按Bangumi ID直接查找")
        print(f"{'  ' * depth}   2. 手动输入关键词搜索")
        print(f"{'  ' * depth}   3. 按本地解析信息写入")
        print(f"{'  ' * depth}   4. 跳过此系列")

        if alt_keywords:
            print()
            print(f"{'  ' * depth}📋 可用别名关键词: {', '.join(alt_keywords)}")

        choice = self.get_user_choice(f"{'  ' * depth}请输入选择 (1/2/3/4): ", ["1", "2", "3", "4"])

        if choice is None:
            print(f"{'  ' * depth}⏰ 等待超时，自动使用本地文件夹解析结果")
            result["choice"] = "timeout"  # 使用特殊标志表示超时
        else:
            result["choice"] = choice

            # 如果是选择3（按本地解析信息写入），设置特殊标志
            if choice == "3":
                result["choice"] = "local_write"

        return result

    def handle_id_search(self, fetcher, depth: int = 0) -> Optional[Dict[str, Any]]:
        """处理按ID搜索的用户交互

        Args:
            fetcher: Bangumi获取器实例
            depth: 当前深度

        Returns:
            Optional[Dict[str, Any]]: 搜索结果或None
        """
        if self.gui_bridge:
            id_input = self.gui_bridge.invoke('get_text', title='Bangumi ID',
                                              prompt='请输入 Bangumi ID（如 378725）：')
        else:
            id_input = self.get_user_input(f"{'  ' * depth}请输入Bangumi ID（如378725）: ")

        if id_input is None:
            return None

        try:
            subject_id = int(id_input)
            return self.search_by_id(fetcher, subject_id, depth)
        except ValueError:
            print(f"{'  ' * depth}❌ ID格式错误，请输入数字")
            return None
    
    def search_by_id(self, fetcher, subject_id: int, depth: int = 0) -> Optional[Dict[str, Any]]:
        """按Bangumi ID搜索
        
        Args:
            fetcher: Bangumi获取器实例
            subject_id: Bangumi ID
            depth: 当前深度
            
        Returns:
            Optional[Dict[str, Any]]: 搜索结果或None
        """
        print(f"{'  ' * depth}🔍 正在按Bangumi ID查找: {subject_id}")
        detail = fetcher.get_manga_detail(subject_id)
        if detail:
            result = {
                "id": subject_id,
                "name": detail.get("name", ""),
                "name_cn": detail.get("name_cn", ""),
                "rating": detail.get("rating", {})
            }
            print(f"{'  ' * depth}  ✅ ID查找成功: {result.get('name_cn') or result.get('name')}")
            return result
        else:
            print(f"{'  ' * depth}❌ 未找到ID为 {subject_id} 的作品")
            return None
    
    def handle_manual_search(self, fetcher, depth: int = 0) -> Optional[List[Dict[str, Any]]]:
        """处理手动关键词搜索的用户交互

        Args:
            fetcher: Bangumi获取器实例
            depth: 当前深度

        Returns:
            Optional[List[Dict[str, Any]]]: 搜索结果或None
        """
        if self.gui_bridge:
            keyword = self.gui_bridge.invoke('get_text', title='自定义关键词',
                                             prompt='请输入搜索关键词：')
        else:
            keyword = self.get_user_input(f"{'  ' * depth}请输入搜索关键词: ")

        if keyword is None:
            return None

        if keyword:
            print(f"{'  ' * depth}🔍 使用关键词搜索: {keyword}")
            temp_results = fetcher.search_manga(keyword)
            if temp_results:
                print(f"{'  ' * depth}✅ 使用关键词 '{keyword}' 找到 {len(temp_results)} 个结果")
                return temp_results
            else:
                print(f"{'  ' * depth}❌ 关键词 '{keyword}' 未找到结果")
        else:
            print(f"{'  ' * depth}❌ 关键词不能为空")

        return None

    def get_id_input(self, depth: int = 0) -> Optional[str]:
        """获取用户输入的Bangumi ID

        Args:
            depth: 当前深度

        Returns:
            Optional[str]: 用户输入的ID或None（超时）
        """
        if self.gui_bridge:
            return self.gui_bridge.invoke('get_text', title='Bangumi ID',
                                          prompt='请输入 Bangumi ID（如 378725）：')
        return self.get_user_input(f"{'  ' * depth}请输入Bangumi ID（如378725）: ")


def create_interaction_handler(timeout_handler: Optional[TimeoutHandler] = None,
                               gui_bridge: Optional[Any] = None) -> InteractionHandler:
    """创建交互处理器实例

    Args:
        timeout_handler: 超时处理器实例，None则创建新的
        gui_bridge: GUI 对话框桥接器实例

    Returns:
        InteractionHandler: 交互处理器实例
    """
    return InteractionHandler(timeout_handler, gui_bridge)