#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""赞助支持对话框 - 展示收款码（单码/多码）+ 文案 + 可选外部赞助链接"""

import os
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

import config

DEFAULT_SPONSOR_TEXT = (
    "开发不易，欢迎支持开发者买猫条 🐱\n"
    "ComicInfo 是完全免费的开源工具，如果你觉得它帮你省了时间，"
    "可以扫码请开发者喝杯咖啡："
)

QR_MAX_SIZE = 200  # 收款码显示最大边长（多码并排时缩小）


class SponsorDialog(QDialog):
    """赞助支持对话框

    展示发布者配置的收款码（sponsor_qr_codes 多码并排，或 sponsor_qr_path 单码）
    与文案（config.SPONSOR_TEXT）。未配置收款码时给出提示，不崩溃。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("赞助支持")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建界面：文案 + 收款码区（单/多码） + 可选外链按钮"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # 赞助文案（自定义优先，留空用默认）
        text = config.SPONSOR_TEXT.strip() or DEFAULT_SPONSOR_TEXT
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet("font-size: 13px; color: #333333;")
        layout.addWidget(text_label)

        # 收款码区：多码并排（每个带名称标签）或单码
        qr_items = self._collect_qr_items()
        if qr_items:
            qr_area = QHBoxLayout()
            qr_area.setSpacing(16)
            qr_area.addStretch(1)
            per_max = QR_MAX_SIZE if len(qr_items) <= 1 else 150
            for name, path in qr_items:
                qr_area.addWidget(self._build_qr_widget(name, path, per_max))
            qr_area.addStretch(1)
            layout.addLayout(qr_area)
        else:
            hint = QLabel("（暂未配置收款码，请联系开发者）")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet("font-size: 12px; color: #999999;")
            layout.addWidget(hint)

        # 底部按钮：可选外链 + 关闭
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        if config.SPONSOR_URL.strip():
            link_btn = QPushButton("打开赞助页")
            link_btn.setStyleSheet(
                "QPushButton { font-size: 13px; background-color: #2196F3; "
                "color: white; border-radius: 5px; padding: 6px 16px; }"
                "QPushButton:hover { background-color: #1976D2; }")
            link_btn.clicked.connect(self._open_sponsor_url)
            btn_layout.addWidget(link_btn)
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "QPushButton { font-size: 13px; padding: 6px 16px; "
            "border-radius: 5px; }")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _build_qr_widget(self, name: str, path: str, max_size: int) -> QWidget:
        """构建单个收款码组件（标签 + 图片）"""
        widget = QWidget()
        vbox = QVBoxLayout()
        vbox.setSpacing(4)
        vbox.setContentsMargins(0, 0, 0, 0)
        if name:
            name_label = QLabel(name)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setStyleSheet("font-size: 12px; color: #666666;")
            vbox.addWidget(name_label)
        if path and os.path.exists(path):
            qr_label = QLabel()
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    max_size, max_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                qr_label.setPixmap(pixmap)
                qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                vbox.addWidget(qr_label)
        widget.setLayout(vbox)
        return widget

    def _collect_qr_items(self) -> List[Tuple[str, str]]:
        """收集收款码 [(名称, 绝对路径), ...]：优先多码列表，其次单码"""
        items: List[Tuple[str, str]] = []
        codes = config.SPONSOR_QR_CODES
        if isinstance(codes, list) and codes:
            for entry in codes:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "")).strip()
                raw = str(entry.get("path", "")).strip()
                if raw:
                    items.append((name, self._resolve_qr_path(raw)))
            if items:
                return items
        raw = config.SPONSOR_QR_PATH.strip()
        if raw:
            items.append(("", self._resolve_qr_path(raw)))
        return items

    def _resolve_qr_path(self, raw: str) -> str:
        """解析收款码图片绝对路径（支持相对项目根路径）"""
        if not raw:
            return ""
        if os.path.isabs(raw):
            return raw
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, raw)

    def _open_sponsor_url(self) -> None:
        """打开外部赞助链接（系统浏览器）"""
        import webbrowser
        url = config.SPONSOR_URL.strip()
        if url:
            webbrowser.open(url)
