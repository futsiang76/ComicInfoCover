#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用设置对话框"""

import config
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                             QSpinBox, QVBoxLayout)


class SettingsDialog(QDialog):
    """应用设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("应用设置")
        self.setMinimumWidth(360)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        form_layout = QFormLayout()

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

        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        config.FUZZ_THRESHOLD = self.fuzz_spin.value()
        config.AUTHOR_MATCH_THRESHOLD = self.author_spin.value()
        config.TIMEOUT = self.timeout_spin.value()
        config.MAX_RETRIES = self.retries_spin.value()
        self.accept()
