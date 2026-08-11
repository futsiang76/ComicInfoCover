#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 模块 - PySide6 图形界面
──────────────────
模块文件结构：
  main_window.py        主窗口（244行）骨架，所有方法委托到下级模块
  scan_tab.py           扫描面板 UI
  results_tab.py        结果面板 UI
  scan_thread.py        后台扫描线程
  scan_controller.py    扫描流程控制（启动/停止/进度/完成）
  dialogs.py            独立对话框
  results_table.py      结果表格填充
  edit_controller.py    编辑辅助（选择/双击编辑）
  save_handler.py       批量保存逻辑
  xml_editor.py         XML 编辑/对比
  edit_dialog.py        单条目元数据编辑对话框
  title_edit_dialog.py  各卷Title/详细信息编辑对话框
  utils.py              共享工具函数
"""

from .main_window import MainWindow
from .scan_thread import ScanThread
from .edit_dialog import EditDialog
from .title_edit_dialog import TitleEditDialog
from .scan_controller import start_scan, stop_scan
from .dialogs import show_xml_exists_dialog
from .edit_controller import edit_row, on_results_double_clicked, edit_selected
from .save_handler import save_changes
from .xml_editor import open_xml_editor, on_edit_xml_clicked

__all__ = ['MainWindow', 'ScanThread', 'EditDialog', 'TitleEditDialog']
