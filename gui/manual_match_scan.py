#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动匹配模式（mode 3）后台扫描线程 - ManualMatchThread

逐文件夹「输入 Bangumi ID（0=本地）→ 查询 → 编辑确认 → 保存」，
基于 BaseScanThread：弹窗经 DialogBridge 桥接主线程，进度/日志/结果走信号，
主线程事件循环保持运行（进度条/小猫动画持续刷新、取消按钮可用）。
"""

import os
from typing import Dict, Optional

from .base_scan_thread import BaseScanThread


class ManualMatchThread(BaseScanThread):
    """手动匹配模式后台扫描线程

    基于 BaseScanThread，只保留手动匹配特有的搜索配置：
    「输入 Bangumi ID → 查询/本地构建」。
    逐个系列「输入 → EditDialog 确认 → 保存」由框架提供。
    """

    source_name = "manual"

    def __init__(self, manga_root: str, manga_value: Optional[str],
                 folders=None, parent=None):
        super().__init__(manga_root, manga_value, folders=folders, parent=parent)
        self._fetcher = None
        self._template_handler = None

    def search_and_select(self, folder_path: str, folder_info: Dict):
        """输入 Bangumi ID → 查询/本地构建

        返回 (comic_info_base, selected_result)；None 表示跳过此系列
        """
        from models.bangumi_fetcher import BangumiFetcher
        from processors.single_series_processor import build_comic_info_from_id
        from processors.xml_template_handler import create_xml_template_handler

        # 惰性初始化：仅首个文件夹创建一次
        if self._fetcher is None:
            self._fetcher = BangumiFetcher()
            self._template_handler = create_xml_template_handler()

        # 1. 输入 Bangumi ID（0=使用本地文件夹信息）
        bangumi_id = self._gui_callback('single_series_input',
                                        folder_path=folder_path, folder_info=folder_info)
        if not bangumi_id:
            self.log_message.emit("⏭️ 未输入，跳过此系列")
            return None

        # 2. 查询并构建 comic_info_base
        if bangumi_id == "0":
            self.log_message.emit("📋 使用本地文件夹信息")
            return self._template_handler.create_local_template(folder_info), None

        try:
            numeric_id = int(bangumi_id)
        except ValueError:
            self._gui_callback('warning', title="无效输入",
                               message=f"Bangumi ID 必须是数字: {bangumi_id}，跳过此系列")
            self.log_message.emit("❌ 无效的 Bangumi ID，跳过")
            return None

        built = build_comic_info_from_id(self._fetcher, numeric_id, folder_info)
        if not built:
            # 查询失败：报错后自动跳过，进入下一个文件夹
            folder_name = os.path.basename(folder_path)
            self._gui_callback('bangumi_id_not_found', bangumi_id=bangumi_id,
                               folder_name=folder_name)
            self.log_message.emit("❌ 未找到该 ID 的作品，跳过此系列")
            return None
        comic_info_base, selected_result = built
        title_cn = selected_result.get("name_cn") or selected_result.get("name", "")
        self.log_message.emit(f"🎯 获取到: {title_cn}")
        return comic_info_base, selected_result

    def build_result(self, folder_path: str, folder_info: Dict,
                     comic_info_base: Dict, selected_result: Optional[Dict]) -> Dict:
        """构建手动匹配扫描结果字典"""
        from processors.result_builder import create_result_dict
        return create_result_dict(folder_path, folder_info, comic_info_base,
                                  selected_result, skipped=False, process_status="已修改")
