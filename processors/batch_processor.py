#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理器模块 - 主流程控制器

使用新的模块化组件：
- search_handler: 搜索处理器
- interaction_handler: 交互处理器  
- xml_template_handler: XML模板处理器
- xml_mode_handler: 已有XML文件夹的模式分流（高速/修正优先于GUI弹窗）
- file_handler: 文件处理器
- match_failure_handler: 匹配失败处理器
- folder_recursive_handler: 文件夹递归处理器
- timeout_handler: 超时处理器
"""

import os
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
from processors.single_series_processor import build_comic_info_from_id
from processors.timeout_handler import create_timeout_handler
from processors.xml_template_handler import create_xml_template_handler
from processors.zip_handler import create_file_handler
from processors.xml_mode_handler import create_xml_mode_handler

from .scan_processors import process_normal_folder
from .utils import process_short_story_folder

from .result_builder import create_result_dict, create_result_dict_from_xml

class BatchProcessor:
    """批量处理器类 - 用于GUI模式"""

    def __init__(self, root_path: str, mode_skip_xml: int = 0, auto_turbo: bool = False, manga_value: Optional[str] = None, use_local_only: bool = False, bangumi_id: Optional[int] = None, gui_callback: Optional[Callable] = None):
        """初始化批量处理器
        
        Args:
            root_path: 漫画根目录路径
            mode_skip_xml: XML跳过模式 (0=正常, 1=补漏模式, 2=修正模式, 3=手动匹配模式)
            auto_turbo: 是否启用无人值守模式
            manga_value: Manga字段值（"Yes"或"No"），为None时使用input询问
            use_local_only: 是否仅使用本地信息（不查询Bangumi）
            bangumi_id: 手动匹配模式下的Bangumi ID（GUI 模式下逐文件夹输入，此参数仅控制台使用）
            gui_callback: GUI 交互回调函数，为 None 时使用 console input()
        """
        self.root_path = root_path
        self.mode_skip_xml = mode_skip_xml
        self.auto_turbo = auto_turbo
        self.manga_value = manga_value
        self.use_local_only = use_local_only
        self.bangumi_id = bangumi_id
        self.gui_callback = gui_callback
        self._cancelled = False
        self.progress_callback: Optional[Callable[[int, str], None]] = None
        self.result_callback: Optional[Callable[[Dict], None]] = None
        
        # 统计数据
        self.total_folders = 0
        self.auto_processed = 0
        self.manual_processed = 0
        self.skipped = 0
        self.total_files = 0
        self.success_files = 0
        
        # 处理结果列表
        self.results: List[Dict[str, Any]] = []
        
        # 创建处理器实例
        self.fetcher = BangumiFetcher()
        self.file_handler = create_file_handler()
        self.folder_recursive_handler = create_folder_recursive_handler(max_depth=3)
        self._xml_handler = create_xml_mode_handler(self)

    def _create_result_dict(self, folder_path, folder_info, comic_info_base, selected_result, skipped, process_status):
        return create_result_dict(folder_path, folder_info, comic_info_base, selected_result, skipped, process_status)

    def _create_result_dict_from_xml(self, folder_path, folder_info, xml_result):
        return create_result_dict_from_xml(folder_path, folder_info, xml_result)

    def set_progress_callback(self, callback: Callable[[int, str], None]):
        """设置进度回调函数
        
        Args:
            callback: 回调函数，参数为 (进度百分比, 状态消息)
        """
        self.progress_callback = callback
    
    def set_result_callback(self, callback: Callable[[Dict], None]):
        """设置结果回调函数
        
        Args:
            callback: 回调函数，参数为处理结果字典
        """
        self.result_callback = callback
    
    def process(self) -> List[Dict[str, Any]]:
        """执行批量处理
        
        Returns:
            List[Dict]: 处理结果列表
        """
        # 重置统计
        self.total_folders = 0
        self.auto_processed = 0
        self.manual_processed = 0
        self.skipped = 0
        self.total_files = 0
        self.success_files = 0
        self.results = []
        self._cancelled = False
        
        # 通知开始
        if self.progress_callback:
            self.progress_callback(0, "开始扫描...")
        
        # 使用文件夹递归处理器扫描目录
        self.total_folders, processed_folders, skipped_folders = self.folder_recursive_handler.scan_directory(
            self.root_path, 
            self._folder_callback, 
            self._recursive_callback
        )
        
        # 更新统计
        self.skipped += skipped_folders
        
        # 通知完成
        if self.progress_callback:
            self.progress_callback(100, f"扫描完成 - 共处理 {len(self.results)} 个文件夹")
        
        return self.results
    
    def _folder_callback(self, folder_path: str, folder_info: Dict, depth: int = 0) -> bool:
        """文件夹处理回调函数
        
        Args:
            folder_path: 文件夹路径
            folder_info: 文件夹信息
            depth: 当前深度
            
        Returns:
            bool: 是否成功处理
        """
        try:
            # 通知进度
            if self.progress_callback:
                self.progress_callback(
                    int((self.auto_processed + self.manual_processed + self.skipped) / max(self.total_folders, 1) * 100),
                    f"处理: {os.path.basename(folder_path)}"
                )
            
            # 处理文件夹
            if self._cancelled:
                return False
            result = self._process_comic_folder(folder_path, folder_info, depth)
            
            if result and not result.get("skipped"):
                self.results.append(result)
                if self.result_callback:
                    self.result_callback(result)
            
            return True
        except Exception as e:
            print(f"{'  ' * depth}🔴 处理文件夹失败: {str(e)[:50]}")
            return False
    
    def _recursive_callback(self, folder_path: str, depth: int = 0):
        """递归处理回调函数
        
        Args:
            folder_path: 文件夹路径
            depth: 当前深度
        """
        print(f"{'  ' * depth}🔍 递归检查子目录: {os.path.basename(folder_path)}")
    
    def _process_comic_folder(self, folder_path: str, folder_info: Dict, depth: int = 0) -> Optional[Dict]:
        """处理单个漫画文件夹
        
        Args:
            folder_path: 文件夹路径
            folder_info: 文件夹信息
            depth: 当前深度
            
        Returns:
            Optional[Dict]: 处理结果字典
        """
        total_files = 0
        success_files = 0
        
        # 逐系列XML检查：返回三档状态（all/none/partial）+ 文件列表
        xml_status, xml_stats = self._xml_handler.check_folder_xml(folder_path, folder_info)
        # 模式分流优先于GUI弹窗：高速/修正模式直接决策，不弹「检测到已有XML」对话框
        result = self._xml_handler.handle_existing_xml(folder_path, folder_info, depth, xml_status, xml_stats)
        if self._cancelled:
            return None
        if result is not None:
            return result


        # 手动匹配模式：逐文件夹输入 Bangumi ID（GUI 弹窗；控制台用已传入的 ID）
        bangumi_id = self.bangumi_id
        if self.mode_skip_xml == 3 and self.gui_callback:
            bangumi_id = self.gui_callback('single_series_input',
                                           folder_info=folder_info, folder_path=folder_path)
            if not bangumi_id:
                print(f"{'  ' * depth}⏭️  手动匹配模式：未输入 Bangumi ID，跳过此系列")
                self.skipped += 1
                return self._create_result_dict(folder_path, folder_info, None, None, True,
                                                "已跳过（未输入Bangumi ID）")
            try:
                bangumi_id = int(bangumi_id)
            except (ValueError, TypeError):
                print(f"{'  ' * depth}⏭️  手动匹配模式：Bangumi ID 无效，跳过此系列")
                self.skipped += 1
                return self._create_result_dict(folder_path, folder_info, None, None, True,
                                                "已跳过（Bangumi ID无效）")

        # 手动匹配模式：0 → 本地信息；非0 → 按 ID 查询（复用共享构建函数）
        if self.mode_skip_xml == 3:
            if bangumi_id == 0:
                print(f"{'  ' * depth}📋 手动匹配模式：使用本地文件夹信息")
                template_handler = create_xml_template_handler()
                comic_info_base = template_handler.create_local_template(folder_info)
                result = {
                    "comic_info_base": comic_info_base,
                    "selected_result": None,
                    "skip_files": False
                }
                self.auto_processed += 1
            elif bangumi_id:
                print(f"{'  ' * depth}🎯 手动匹配模式：使用 Bangumi ID {bangumi_id} 直接获取信息")
                built = build_comic_info_from_id(self.fetcher, bangumi_id, folder_info)
                if built:
                    comic_info_base, selected_result = built
                    result = {
                        "comic_info_base": comic_info_base,
                        "selected_result": selected_result,
                        "skip_files": False
                    }
                    self.auto_processed += 1
                else:
                    print(f"{'  ' * depth}❌ 无法获取 Bangumi ID {bangumi_id} 的详情")
                    return self._create_result_dict(folder_path, folder_info, None, None, True,
                                                    "获取Bangumi详情失败")
            else:
                print(f"{'  ' * depth}❌ 手动匹配模式未指定 Bangumi ID")
                return self._create_result_dict(folder_path, folder_info, None, None, True,
                                                "未指定 Bangumi ID")
        # 检测是否是不规范文件夹
        elif is_irregular_folder(folder_info):
            # 不规范文件夹，每个文件独立处理
            result = process_irregular_folder(folder_path, self.fetcher, depth)
            self.auto_processed += 1
        # 短篇文件夹特殊处理
        elif folder_info.get('vol_type') == '短篇':
            result = process_short_story_folder(folder_path, folder_info, depth)
            self.auto_processed += 1
        # 仅使用本地信息模式
        elif self.use_local_only:
            # 直接使用本地信息，不查询Bangumi
            template_handler = create_xml_template_handler()
            comic_info_base = template_handler.create_local_template(folder_info)
            result = {
                "comic_info_base": comic_info_base,
                "selected_result": None,
                "skip_files": False
            }
            self.auto_processed += 1
        else:
            # 正常流程
            result = process_normal_folder(folder_path, folder_info, self.fetcher, depth,
                                           gui_callback=self.gui_callback)
            
            # 更新统计
            if result.get("selected_result"):
                if result["selected_result"] == "manual":
                    self.manual_processed += 1
                else:
                    self.auto_processed += 1
        
        # 处理文件
        if result.get("skip_files"):
            # 如果是XML只读模式，不更新文件，但仍要创建结果字典
            if result.get("xml_readonly"):
                print(f"{'  ' * depth}📖 XML只读模式：仅读取元数据，不更新文件")
                return self._create_result_dict_from_xml(folder_path, folder_info, result)
            else:
                self.skipped += 1
                print(f"{'  ' * depth}⏭️  跳过此系列")
                return self._create_result_dict(folder_path, folder_info, None, None, True, "已跳过")
        else:
                        # 检查是否是不规范文件夹特殊处理
            if result.get("selected_result") == "irregular":
                # 不规范文件夹，每个文件独立处理
                total_files, success_files = process_irregular_folder_files(
                    folder_path, self.fetcher, depth, self.manga_value
                )
            else:
                # 正常处理
                comic_info_base = result["comic_info_base"]
                skip_files = result.get("skip_files", False)
                
                total_files, success_files = self.file_handler.process_comic_files(
                    folder_path, comic_info_base, folder_info, skip_files, self.manga_value
                )
            
            self.total_files += total_files
            self.success_files += success_files
            
            # 创建结果字典
            selected_result = result.get("selected_result")
            comic_info_base = result.get("comic_info_base")

            return self._create_result_dict(
                folder_path, folder_info, comic_info_base, selected_result, False, "处理成功"
            )

    def get_statistics(self) -> Dict:
        """获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        return {
            "total_folders": self.total_folders,
            "auto_processed": self.auto_processed,
            "manual_processed": self.manual_processed,
            "skipped": self.skipped,
            "total_files": self.total_files,
            "success_files": self.success_files,
            "success_rate": (self.success_files / self.total_files * 100) if self.total_files > 0 else 0
        }
