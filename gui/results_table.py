#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果表格填充 - 在结果标签页中展示扫描结果的卡片列表
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)


def update_results_table(mw):
    # 清空现有结果
    # 清空 results_layout 中的所有子部件
    while mw.results_layout.count():
        child = mw.results_layout.takeAt(0)
        if child is not None:
            w = child.widget()
            if w:
                w.deleteLater()

    # 为每个结果创建一个卡片
    for row, result in enumerate(mw.scan_results):
        # 创建GroupBox
        group_box = QGroupBox(f"{result['series']} - {result['folder_name']}")
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #333;
                border: 2px solid #4CAF50;
                border-radius: 7px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                background-color: #4CAF50;
                color: white;
                border-radius: 3px;
            }
        """)

        card_layout = QFormLayout()

        # 第一行：基本信息
        card_layout.addRow("文件夹:", QLabel(result["folder_name"]))
        card_layout.addRow("系列名:", QLabel(result["series"]))
        card_layout.addRow("总卷数:", QLabel(str(result.get("count", ""))))

        # 第二行：作者信息
        card_layout.addRow("作者:", QLabel(result.get("writer", "")))
        card_layout.addRow("作画:", QLabel(result.get("penciller", "")))
        card_layout.addRow("上色:", QLabel(result.get("colorist", "")))

        # 第三行：其他信息
        card_layout.addRow("Web:", QLabel(result.get("web", "")))
        year_str = result.get("year", "")
        month_str = result.get("month", "")
        date_display = f"{year_str}-{month_str}" if year_str and month_str else (year_str or "")
        card_layout.addRow("发行时间:", QLabel(date_display))
        card_layout.addRow("状态:", QLabel(result["status"]))

        # 第四行：简介和标签
        summary_text = result.get("summary", "")
        if summary_text:
            summary_label = QLabel(summary_text)
            summary_label.setWordWrap(True)
            summary_label.setMaximumHeight(60)
            card_layout.addRow("简介:", summary_label)

        genre_text = result.get("genre", "")
        if genre_text:
            genre_label = QLabel(genre_text)
            genre_label.setWordWrap(True)
            card_layout.addRow("分类:", genre_label)

        tags_text = result.get("tags", "")
        if tags_text:
            tags_label = QLabel(tags_text)
            tags_label.setWordWrap(True)
            card_layout.addRow("标签:", tags_label)

        # 第五行：Manga设置和操作
        card_layout.addRow("是否Manga:", QLabel(result.get("manga", "")))

        # 操作按钮 - 突出显示
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        edit_btn = QPushButton("✏️ 编辑")
        edit_btn.setMinimumHeight(35)
        edit_btn.setMinimumWidth(100)
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-size: 13px;
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #e68900;
            }
            QPushButton:pressed {
                background-color: #cc7a00;
            }
        """)
        edit_btn.clicked.connect(lambda _, r=row: mw.edit_row(r))
        button_layout.addWidget(edit_btn)

        button_layout.addStretch()
        card_layout.addRow("", button_layout)

        group_box.setLayout(card_layout)
        mw.results_layout.addWidget(group_box)


