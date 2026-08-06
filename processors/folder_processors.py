#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理器模块 - 主流程控制器

使用新的模块化组件：
- search_handler: 搜索处理器
- interaction_handler: 交互处理器  
- xml_template_handler: XML模板处理器
- file_handler: 文件处理器
- match_failure_handler: 匹配失败处理器
- folder_recursive_handler: 文件夹递归处理器
- timeout_handler: 超时处理器
"""

import os
import platform
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import AUTHOR_MATCH_THRESHOLD, FUZZ_THRESHOLD, WAITING_TIME
from models.bangumi_fetcher import BangumiFetcher
from processors.folder_recursive_handler import create_folder_recursive_handler
from processors.interaction_handler import create_interaction_handler
from processors.irregular_folder_handler import (
    is_irregular_folder, process_irregular_folder,
    process_irregular_folder_files)
from processors.match_failure_handler import create_match_failure_handler
from processors.search_handler import create_search_handler
from processors.selector_handler import create_selector_handler
from processors.timeout_handler import create_timeout_handler
from processors.xml_template_handler import create_xml_template_handler
from processors.zip_handler import create_file_handler

from .utils import check_all_files_have_xml, process_short_story_folder, process_xml_modify_folder
from .scan_processors import process_comic_folder, process_normal_folder

def batch_process(manga_root: str):
    """批量处理漫画文件夹
    
    Args:
        manga_root: 漫画根目录路径
    """
    # Windows编码适配
    if sys.platform == "win32":
        os.system("chcp 65001 >nul")
        # 完全兼容所有Python版本的编码设置
        try:
            # 设置环境变量来确保UTF-8编码
            os.environ['PYTHONIOENCODING'] = 'utf-8'
            os.environ['PYTHONUTF8'] = '1'
        except Exception:
            # 如果设置失败，忽略错误
            pass
        
        # 简化处理，只依赖环境变量设置
        # 避免修改stdout/stderr的只读属性
        pass

    # 创建处理器实例
    fetcher = BangumiFetcher()
    file_handler = create_file_handler()
    folder_recursive_handler = create_folder_recursive_handler(max_depth=3)
    
    # 统计变量
    total_folders = 0
    auto_processed = 0
    manual_processed = 0
    skipped = 0
    total_files = 0
    success_files = 0

    print("="*80)
    print("📚 开始智能批量处理漫画文件夹")
    print(f"📁 根目录: {manga_root}")
    print(f"⚙️  配置: 作品匹配阈值={FUZZ_THRESHOLD}% | 作者匹配阈值={AUTHOR_MATCH_THRESHOLD}%")
    print("="*80)

    def folder_callback(folder_path: str, folder_info: Dict, depth: int = 0):
        """文件夹处理回调函数
        
        Args:
            folder_path: 文件夹路径
            folder_info: 文件夹信息
            depth: 当前深度
            
        Returns:
            bool: 是否成功处理
        """
        nonlocal auto_processed, manual_processed, skipped, total_files, success_files
        
        try:
            auto_processed, manual_processed, skipped, files, success = process_comic_folder(
                folder_path, folder_info, fetcher, file_handler, 
                auto_processed, manual_processed, skipped, depth, None
            )
            total_files += files
            success_files += success
            return True
        except Exception as e:
            print(f"{'  ' * depth}🔴 处理文件夹失败: {str(e)[:50]}")
            return False

    def recursive_callback(folder_path: str, depth: int = 0):
        """递归处理回调函数
        
        Args:
            folder_path: 文件夹路径
            depth: 当前深度
        """
        print(f"{'  ' * depth}🔍 递归检查子目录: {os.path.basename(folder_path)}")

    # 使用文件夹递归处理器扫描目录
    total_folders, processed_folders, skipped_folders = folder_recursive_handler.scan_directory(
        manga_root, folder_callback, recursive_callback
    )
    
    # 更新统计
    skipped += skipped_folders



