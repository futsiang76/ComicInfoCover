#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台扫描线程 - 漫画目录扫描与数据处理
"""

import os
from typing import Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from gui.gui_dialogs import DialogBridge


class ScanThread(QThread):
    """后台扫描线程"""
    progress_updated = pyqtSignal(int, str)  # (进度, 消息)
    scan_completed = pyqtSignal(list)  # 扫描结果列表
    error_occurred = pyqtSignal(str)  # 错误消息

    def __init__(self, manga_root: str, mode: int, auto_turbo: int, manga_value: Optional[str] = None, use_local_only: bool = False, bangumi_id: Optional[int] = None, parent=None):
        super().__init__()
        self.manga_root = manga_root
        self.mode = mode
        self.auto_turbo = auto_turbo
        self.manga_value = manga_value
        self.use_local_only = use_local_only
        self.bangumi_id = bangumi_id
        self._is_running = True
        # 对话框桥接器（在 __init__ 中创建，确保主线程亲和性）
        self._bridge = DialogBridge(parent)

    def run(self):
        """执行扫描"""
        try:
            # 更新配置
            import config
            config.MODE_SKIP_XMLEXIST = self.mode
            config.AUTO_TURBO_MATCH = self.auto_turbo

            # 导入处理器
            from processors.batch_processor import BatchProcessor

            # 创建 GUI 回调函数（从工作线程调用，桥接到主线程显示对话框）
            bridge = self._bridge

            def gui_callback(action, **params):
                if not self._is_running:
                    return {'action': 'skip', 'value': None} if action == 'search_failure' else None
                return bridge.invoke(action, **params)

            # 创建批量处理器
            processor = BatchProcessor(
                root_path=self.manga_root,
                mode_skip_xml=self.mode,
                auto_turbo=(self.auto_turbo == 1),
                manga_value=self.manga_value,
                use_local_only=self.use_local_only,
                bangumi_id=self.bangumi_id,
                gui_callback=gui_callback
            )

            # 结果收集
            results = []

            # 设置结果回调
            def on_result(result: Dict):
                if not self._is_running:
                    return
                # 添加 folder_name 字段用于显示
                result["folder_name"] = os.path.basename(result["folder_path"])
                results.append(result)
                self.progress_updated.emit(len(results), f"处理: {result['series']}")

            processor.set_result_callback(on_result)

            # 设置进度回调
            def on_progress(progress: int, message: str):
                if not self._is_running:
                    return
                self.progress_updated.emit(progress, message)

            processor.set_progress_callback(on_progress)

            # 执行处理
            processor.process()

            # 发送完成信号
            self.scan_completed.emit(results)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"扫描失败: {str(e)}")

    def stop(self):
        """停止扫描"""
        self._is_running = False
        self._bridge.cancel()


