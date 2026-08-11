﻿#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口 - ComicInfoXmlCreator GUI
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGroupBox,
                             QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                             QMessageBox, QProgressBar, QPushButton, QSpinBox,
                             QSplitter, QStatusBar, QTableWidget,
                             QTableWidgetItem, QTabWidget, QTextEdit,
                             QVBoxLayout, QWidget)

# 导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from processors.batch_processor import BatchProcessor


class ScanThread(QThread):
    """扫描线程"""
    progress_updated = Signal(int, str)
    scan_completed = Signal(list)
    error_occurred = Signal(str)
    
    def __init__(self, root_path: str, mode: int, auto_turbo: bool):
        super().__init__()
        self.root_path = root_path
        self.mode = mode
        self.auto_turbo = auto_turbo
        self._is_running = True
    
    def run(self):
        """执行扫描"""
        try:
            self.progress_updated.emit(0, "开始扫描...")
            
            # 创建批处理器
            processor = BatchProcessor(
                root_path=self.root_path,
                mode_skip_xml=self.mode,
                auto_turbo=self.auto_turbo
            )
            
            # 执行扫描（这里需要修改BatchProcessor以支持GUI模式）
            # 暂时先返回模拟数据
            results = self._get_mock_results()
            
            self.progress_updated.emit(100, "扫描完成")
            self.scan_completed.emit(results)
            
        except Exception as e:
            self.error_occurred.emit(f"扫描失败: {str(e)}")
    
    def _get_mock_results(self) -> List[Dict[str, Any]]:
        """获取模拟数据（用于测试）"""
        return [
            {
                "folder_path": "F:\\Comics\\[作者A] 漫画名1 (V05全)",
                "series": "漫画名1",
                "count": "5",
                "writer": "作者A",
                "penciller": "作者A",
                "colorist": "",
                "bangumi_id": "12345",
                "publisher": "出版社A",
                "status": "Completed",
                "summary": "这是漫画1的简介",
                "tags": "搞笑, 冒险",
                "manga": "Yes",
                "xml_exists": True,
                "file_titles": {
                    "[作者A] 漫画名1 Vol 01.zip": "Vol 01",
                    "[作者A] 漫画名1 Vol 02.zip": "Vol 02",
                    "[作者A] 漫画名1 Vol 03.zip": "Vol 03",
                    "[作者A] 漫画名1 Vol 04.zip": "Vol 04",
                    "[作者A] 漫画名1 Vol 05.zip": "Vol 05",
                }
            },
            {
                "folder_path": "F:\\Comics\\[作者B] 漫画名2 (V03 C13)",
                "series": "漫画名2",
                "count": "",
                "writer": "作者B",
                "penciller": "作者C",
                "colorist": "上色师D",
                "bangumi_id": "67890",
                "publisher": "出版社B",
                "status": "Ongoing",
                "summary": "这是漫画2的简介",
                "tags": "奇幻, 战斗",
                "manga": "Yes",
                "xml_exists": False,
                "file_titles": {
                    "[作者B] 漫画名2 Vol 01.zip": "Vol 01",
                    "[作者B] 漫画名2 Vol 02.zip": "Vol 02",
                    "[作者B] 漫画名2 Vol 03.zip": "Vol 03",
                    "[作者B] 漫画名2 C01.zip": "C 01",
                    "[作者B] 漫画名2 C02.zip": "C 02",
                }
            }
        ]
    
    def stop(self):
        """停止扫描"""
        self._is_running = False