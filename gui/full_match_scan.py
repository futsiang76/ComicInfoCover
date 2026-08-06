#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全匹配模式（mode 0）逐个交互扫描流程 - 基于 BaseScanThread

非无人值守时在后台线程对每个系列文件夹执行：
「扫描匹配 → EditDialog 确认 → 静默保存 → 下一个」，
不批量收集后统一编辑，也不弹「保存完成」结果框。
无人值守（AUTO_TURBO_MATCH=1）仍走 ScanThread 后台批量流程。

本类只保留 bangumi 特有的搜索配置（XML 分流 + 搜索 + 结果构建），
线程化/信号/弹窗桥接/逐系列保存全部由 BaseScanThread 提供。
"""

from typing import Dict, Optional

from .base_scan_thread import BaseScanThread


class FullMatchThread(BaseScanThread):
    """全匹配模式（非无人值守）后台扫描线程

    基于 BaseScanThread，只保留 bangumi 特有的搜索配置：
    「已有 XML 分流（弹窗询问）→ Bangumi 搜索匹配 → 结果构建」。
    逐个系列「扫描匹配 → EditDialog 确认 → 保存 → 下一个」由框架提供。
    """

    source_name = "bangumi"
    source_label = "全匹配"

    def __init__(self, manga_root: str, manga_value: Optional[str], parent=None):
        super().__init__(manga_root, manga_value, parent=parent)
        self._fetcher = None

    def search_and_select(self, folder_path: str, folder_info: Dict):
        """已有 XML 分流 + Bangumi 搜索匹配

        返回 (comic_info_base, selected_result) 或 (RESULT_READY, result)；
        None 表示跳过（含取消整个扫描，置 _is_running=False）。
        """
        from models.bangumi_fetcher import BangumiFetcher
        from processors.scan_processors import process_normal_folder

        # 惰性初始化：仅首个文件夹创建一次
        if self._fetcher is None:
            self._fetcher = BangumiFetcher()

        # 1. 已有 XML 处理（弹窗询问；'cancel' 终止整个扫描）
        handled, xml_out = self.check_existing_xml(folder_path, folder_info)
        if handled:
            return xml_out  # None → 跳过； (RESULT_READY, result) → 修改结果

        # 2. Bangumi 搜索匹配（含多结果选择/无结果处理弹窗）
        scan_result = process_normal_folder(folder_path, folder_info, self._fetcher, 0,
                                            gui_callback=self._gui_callback)
        if scan_result.get("skip_files"):
            self.log_message.emit("⏭️ 跳过此系列")
            return None
        comic_info_base = scan_result.get("comic_info_base") or {}
        return comic_info_base, scan_result.get("selected_result")

    def build_result(self, folder_path: str, folder_info: Dict,
                     comic_info_base: Dict, selected_result: Optional[Dict]) -> Dict:
        """构建 bangumi 扫描结果字典"""
        from processors.result_builder import create_result_dict
        return create_result_dict(folder_path, folder_info, comic_info_base,
                                  selected_result, False, "已修改")
