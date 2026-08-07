#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果标签页 - 扫描结果展示与批量操作面板
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


def build_results_tab(mw, tab_widget):
    """创建结果标签页"""
    from pathlib import Path

    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QMovie

    from gui.utils import SmoothMovieLabel

    results_tab = QWidget()
    layout = QVBoxLayout()
    results_tab.setLayout(layout)

    # 写盘期间在窗体正中央显示工作小猫（悬浮于主窗口，写盘完成自动隐藏）
    mw.results_cat_movie = QMovie(
        str(Path(__file__).resolve().parent.parent / "assets" / "loading_cat.gif"))
    mw.results_cat_movie.jumpToFrame(0)
    cat_size = mw.results_cat_movie.frameRect().size()
    if cat_size.isEmpty():  # 兜底：GIF 异常时退回原始像素，避免 0x0 不可见
        cat_size = QSize(282, 282)
    if cat_size.height():  # 等比缩小，避免内嵌小猫过大占满结果页顶部
        cat_size = QSize(round(cat_size.width() * 140 / cat_size.height()), 140)
    # 父级为主窗口（悬浮用，不加入布局）；位置由 set_results_saving 居中
    mw.results_cat_label = SmoothMovieLabel(mw.results_cat_movie, mw)
    mw.results_cat_label.setFixedSize(cat_size)
    mw.results_cat_label.hide()

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

