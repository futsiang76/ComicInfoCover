#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
处理器模块 - 包含所有漫画信息处理的处理器组件
"""

# 导入所有处理器模块的创建函数
from .folder_processors import batch_process
from .choice_handlers import create_choice_handlers
from .folder_recursive_handler import create_folder_recursive_handler
from .interaction_handler import create_interaction_handler
from .match_failure_handler import create_match_failure_handler
from .search_handler import create_search_handler
from .selector_handler import create_selector_handler
from .timeout_handler import create_timeout_handler
from .xml_generator import build_full_comicinfo_dict
from .xml_template_handler import create_xml_template_handler
from .zip_handler import create_file_handler

# 导入处理器类（用于直接使用）
from .choice_handlers import ChoiceHandlers
from .folder_recursive_handler import FolderRecursiveHandler
from .interaction_handler import InteractionHandler
from .match_failure_handler import MatchFailureHandler
from .search_handler import SearchHandler
from .selector_handler import SelectorHandler
from .timeout_handler import TimeoutHandler
from .xml_template_handler import XMLTemplateHandler
from .zip_handler import FileHandler

__all__ = [
    # 主处理器函数
    'batch_process',
    
    # 创建函数
    'create_choice_handlers',
    'create_folder_recursive_handler',
    'create_interaction_handler',
    'create_match_failure_handler',
    'create_search_handler',
    'create_selector_handler',
    'create_timeout_handler',
    'create_xml_template_handler',
    'create_file_handler',
    
    # 处理器类
    'ChoiceHandlers',
    'FolderRecursiveHandler',
    'InteractionHandler',
    'MatchFailureHandler',
    'SearchHandler',
    'SelectorHandler',
    'TimeoutHandler',
    'XMLTemplateHandler',
    'FileHandler',
    
    # 工具函数
    'build_full_comicinfo_dict',
]