#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果标签页 - 扫描结果展示与批量操作面板
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


def build_results_tab(mw, tab_widget):
    """创建结果标签页"""
    results_tab = QWidget()
    layout = QVBoxLayout()
    results_tab.setLayout(layout)

    # 滚动区域
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # 结果容器
    mw.results_container = QWidget()
    mw.results_layout = QVBoxLayout()
    mw.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    mw.results_container.setLayout(mw.results_layout)

    scroll_area.setWidget(mw.results_container)
    layout.addWidget(scroll_area)

    mw.tab_widget.addTab(results_tab, "📊 结果")

