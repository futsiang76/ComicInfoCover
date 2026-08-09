#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用设置对话框"""

import config
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QSpinBox, QVBoxLayout, QWidget)


class SwitchButton(QCheckBox):
    """左右开关（QCheckBox 自绘滑动圆钮，选中靠右，绿色）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 26)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        # 轨道
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4cd964") if self.isChecked() else QColor("#cccccc"))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        # 滑动圆钮
        d = rect.height() - 4
        x = rect.width() - d - 2 if self.isChecked() else 2
        painter.setBrush(QColor("white"))
        painter.drawEllipse(x, 2, d, d)


class SettingsDialog(QDialog):
    """应用设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("应用设置")
        self.setMinimumWidth(460)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        form_layout = QFormLayout()

        # API Key 配置（密码模式，写入 user_config.json）
        self.bangumi_edit = QLineEdit()
        self.bangumi_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.bangumi_edit.setText(config.BANGUMI_ACCESS_TOKEN)
        form_layout.addRow("Bangumi Access Token:", self.bangumi_edit)

        self.comicvine_edit = QLineEdit()
        self.comicvine_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.comicvine_edit.setText(config.COMICVINE_API_KEY)
        form_layout.addRow("ComicVine API Key:", self.comicvine_edit)

        self.fuzz_spin = QSpinBox()
        self.fuzz_spin.setRange(0, 100)
        self.fuzz_spin.setValue(config.FUZZ_THRESHOLD)
        form_layout.addRow("作品名模糊匹配阈值 (%):", self.fuzz_spin)

        self.author_spin = QSpinBox()
        self.author_spin.setRange(0, 100)
        self.author_spin.setValue(config.AUTHOR_MATCH_THRESHOLD)
        form_layout.addRow("作者名匹配阈值 (%):", self.author_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setValue(config.TIMEOUT)
        form_layout.addRow("请求超时时间 (秒):", self.timeout_spin)

        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(config.MAX_RETRIES)
        form_layout.addRow("请求重试次数:", self.retries_spin)

        self.crop_memory_switch = SwitchButton()
        self.crop_memory_switch.setChecked(config.CROP_MEMORY_ENABLED)
        form_layout.addRow("封面裁剪定位记忆:", self.crop_memory_switch)

        # 保存格式：keep/cbz/zip/cb7（默认保持原格式）
        self.save_format_combo = QComboBox()
        self.save_format_combo.addItem("保持原格式", "keep")
        self.save_format_combo.addItem("CBZ (.cbz)", "cbz")
        self.save_format_combo.addItem("ZIP (.zip)", "zip")
        self.save_format_combo.addItem("CB7 (.cb7)", "cb7")
        index = self.save_format_combo.findData(config.SAVE_FORMAT)
        self.save_format_combo.setCurrentIndex(index if index >= 0 else 0)
        form_layout.addRow("保存格式:", self.save_format_combo)

        self.delete_after_convert_switch = SwitchButton()
        self.delete_after_convert_switch.setChecked(config.DELETE_AFTER_CONVERT)
        form_layout.addRow("写入后删除旧文件:", self.delete_after_convert_switch)

        # 默认漫画目录：QLineEdit + 浏览按钮（留空则启动时提示选择）
        self.default_dir_edit = QLineEdit()
        self.default_dir_edit.setText(config.DEFAULT_MANGA_DIR)
        self.default_dir_edit.setPlaceholderText("留空则启动时提示选择")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_default_dir)
        dir_widget = QWidget()
        dir_layout = QHBoxLayout()
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.addWidget(self.default_dir_edit)
        dir_layout.addWidget(browse_btn)
        dir_widget.setLayout(dir_layout)
        form_layout.addRow("默认漫画目录:", dir_widget)

        self.remember_last_path_switch = SwitchButton()
        self.remember_last_path_switch.setChecked(config.REMEMBER_LAST_PATH)
        form_layout.addRow("记住上次路径:", self.remember_last_path_switch)

        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _browse_default_dir(self):
        """浏览选择默认漫画目录（对话框起始目录优先取当前输入值）"""
        start = self.default_dir_edit.text().strip() or config.DEFAULT_MANGA_DIR or ""
        path = QFileDialog.getExistingDirectory(self, "选择默认漫画目录", start)
        if path:
            self.default_dir_edit.setText(path)

    def _on_accept(self):
        config.BANGUMI_ACCESS_TOKEN = self.bangumi_edit.text().strip()
        config.COMICVINE_API_KEY = self.comicvine_edit.text().strip()
        config.FUZZ_THRESHOLD = self.fuzz_spin.value()
        config.AUTHOR_MATCH_THRESHOLD = self.author_spin.value()
        config.TIMEOUT = self.timeout_spin.value()
        config.MAX_RETRIES = self.retries_spin.value()
        config.CROP_MEMORY_ENABLED = self.crop_memory_switch.isChecked()
        config.SAVE_FORMAT = self.save_format_combo.currentData()
        config.DELETE_AFTER_CONVERT = self.delete_after_convert_switch.isChecked()
        config.DEFAULT_MANGA_DIR = self.default_dir_edit.text().strip()
        config.REMEMBER_LAST_PATH = self.remember_last_path_switch.isChecked()
        config.save_settings({
            "bangumi_access_token": config.BANGUMI_ACCESS_TOKEN,
            "comicvine_api_key": config.COMICVINE_API_KEY,
            "fuzz_threshold": config.FUZZ_THRESHOLD,
            "author_match_threshold": config.AUTHOR_MATCH_THRESHOLD,
            "timeout": config.TIMEOUT,
            "max_retries": config.MAX_RETRIES,
            "crop_memory_enabled": config.CROP_MEMORY_ENABLED,
            "save_format": config.SAVE_FORMAT,
            "delete_after_convert": config.DELETE_AFTER_CONVERT,
            "default_manga_dir": config.DEFAULT_MANGA_DIR,
            "remember_last_path": config.REMEMBER_LAST_PATH,
        })
        self.accept()
