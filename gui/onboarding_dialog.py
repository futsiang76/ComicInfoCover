#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""首次启动轻引导对话框 - 极简配置引导（10秒完成，不挡路）"""

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QVBoxLayout, QWidget)

import config

HINT_TEXT = "Bangumi Token：可选；ComicVine Key：可选备用源"


class OnboardingDialog(QDialog):
    """首次启动轻引导对话框

    只做两件事：
      1. 默认漫画目录选择（可选，QLineEdit + 浏览按钮）
      2. 一行 API Key 可选提示
    底部「开始使用」保存配置（default_manga_dir + first_run_done=true）并关闭。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用 ComicInfo")
        self.setMinimumWidth(460)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建界面：目录选择 + 一行提示 + 开始使用按钮"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # 默认目录选择（唯一建议项，可跳过）
        title = QLabel("选择你的默认漫画目录")
        title.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        self.dir_edit = QLineEdit()
        self.dir_edit.setText(config.DEFAULT_MANGA_DIR)
        self.dir_edit.setPlaceholderText("请选择你的漫画库目录")
        browse_btn = QPushButton("浏览...")
        browse_btn.setStyleSheet(
            "QPushButton { font-size: 13px; background-color: #2196F3; "
            "color: white; border-radius: 5px; padding: 8px 12px; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        browse_btn.clicked.connect(self._browse_dir)
        dir_widget = QWidget()
        dir_layout = QHBoxLayout()
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(browse_btn)
        dir_widget.setLayout(dir_layout)
        layout.addWidget(dir_widget)

        # 一行提示：可选源说明，不展开技术细节
        self.hint_label = QLabel(HINT_TEXT)
        self.hint_label.setStyleSheet("font-size: 11px; color: #757575;")
        layout.addWidget(self.hint_label)

        # 网络提示：数据源需联网；Bangumi 内置大陆镜像，连不上可本地手填
        self.network_hint_label = QLabel("数据源需要网络连接；Bangumi 已内置大陆镜像，无法连接时可改用本地手填")
        self.network_hint_label.setStyleSheet("font-size: 11px; color: #757575;")
        layout.addWidget(self.network_hint_label)

        layout.addSpacing(8)

        # 开始使用：确认色，保存配置并关闭
        self.start_btn = QPushButton("开始使用")
        self.start_btn.setStyleSheet(
            "QPushButton { font-size: 14px; background-color: #4CAF50; "
            "color: white; border-radius: 5px; padding: 8px 24px; }"
            "QPushButton:hover { background-color: #43A047; }"
        )
        self.start_btn.clicked.connect(self._on_start_use)
        layout.addWidget(self.start_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _browse_dir(self) -> None:
        """浏览选择漫画库目录（起始目录优先取当前输入值）"""
        start = self.dir_edit.text().strip() or config.DEFAULT_MANGA_DIR or ""
        path = QFileDialog.getExistingDirectory(self, "选择漫画库目录", start)
        if path:
            self.dir_edit.setText(path)

    def _on_start_use(self) -> None:
        """保存默认目录 + 标记首次引导完成，然后关闭对话框"""
        manga_dir = self.dir_edit.text().strip()
        config.save_settings({
            "default_manga_dir": manga_dir,
            "first_run_done": True,
        })
        # 填了目录则覆盖记住的上次路径残留：主窗体无论开关状态都用新目录
        if manga_dir:
            QSettings("ComicInfoScratcher", "ComicInfoXMLCreator").setValue(
                "last_manga_path", manga_dir)
        self.accept()
