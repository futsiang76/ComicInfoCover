#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果表格填充 - 在结果标签页中展示扫描结果的卡片列表

P2 封面展示：
- 系列卡片左侧显示首卷封面缩略图 + 「共 N 卷」徽章
- 「展开」显示该系列全部卷封面的缩略图网格（网格换行）
- 封面比例异常（非 870x1230±10% 竖版）→ 红色「需裁剪」角标

P3 裁剪交互：
- 「需裁剪」封面缩略图可点击（ClickableLabel）→ 弹裁剪对话框
- 确定后后台裁剪并重打包（__new 排第一位），完成后角标消失、缩略图换新
"""

import os

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QDialog, QFormLayout, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)

from gui.crop_dialog import CropDialog
from processors.cover_crop import crop_zip_cover
from processors.cover_utils import read_cover_bytes, sort_volume_files

# 封面缩略图尺寸（870x1230 竖版比例）
THUMB_WIDTH = 100
THUMB_HEIGHT = 141
# 卷封面网格列数（超宽自动换行）
GRID_COLUMNS = 4

GROUP_BOX_STYLE = """
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
"""

EDIT_BTN_STYLE = """
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
"""

EXPAND_BTN_STYLE = """
    QPushButton {
        background-color: #f0f0f0;
        color: #555;
        font-size: 12px;
        border: 1px solid #ccc;
        border-radius: 4px;
        padding: 4px 12px;
    }
    QPushButton:hover {
        background-color: #e0e0e0;
    }
"""


class ClickableLabel(QLabel):
    """鼠标左键可点击的 QLabel（「需裁剪」封面缩略图用，P3 触发裁剪对话框）"""

    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.unsetCursor()
        super().leaveEvent(event)


class _CropWorker(QThread):
    """后台执行封面裁剪 + ZIP 重打包，避免大图操作阻塞 UI 主线程"""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, zip_path: str, crop_region: tuple, parent=None):
        super().__init__(parent)
        self._zip_path = zip_path
        self._crop_region = crop_region

    def run(self):
        try:
            info = crop_zip_cover(self._zip_path, self._crop_region)
            if info:
                self.done.emit(info)
            else:
                self.failed.emit("未能完成裁剪（图片解析或 ZIP 打包失败）")
        except Exception as e:
            self.failed.emit(str(e))


def _on_crop_done(mw, result, filename, new_info):
    """裁剪完成：更新该卷封面信息并重渲染结果页（角标消失、缩略图换新）"""
    mw.crop_running = False
    if new_info:
        result["covers"][filename] = new_info
    mw.update_results_table()


def _on_crop_failed(mw, filename, message):
    """裁剪失败：恢复可裁剪状态并提示"""
    mw.crop_running = False
    QMessageBox.warning(mw, "裁剪失败", f"{filename} 封面裁剪失败：{message}")


def _open_crop_flow(mw, result, filename):
    """点击「需裁剪」封面 → 弹裁剪对话框；确定后后台执行裁剪与重打包"""
    info = result.get("covers", {}).get(filename)
    if not info or not info.get("path") or getattr(mw, "crop_running", False):
        return
    dialog = CropDialog(info["path"], mw)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return  # 取消/跳过：不改文件
    region = dialog.crop_region
    if not isinstance(region, tuple):
        return
    mw.crop_running = True
    worker = _CropWorker(info["path"], region, mw)
    worker.done.connect(
        lambda new_info, r=result, f=filename: _on_crop_done(mw, r, f, new_info))
    worker.failed.connect(
        lambda msg, f=filename: _on_crop_failed(mw, f, msg))
    mw._crop_worker = worker  # 持有引用，防止 worker 被 GC
    worker.start()


def _placeholder_label() -> QLabel:
    """灰色占位框 + 📕（封面缺失/加载失败时兜底）"""
    label = QLabel("📕")
    label.setFixedSize(THUMB_WIDTH, THUMB_HEIGHT)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        "background-color: #e0e0e0; color: #aaa;"
        "border: 1px solid #ccc; font-size: 30px;"
    )
    return label


def _load_cover_pixmap(info: dict) -> "QPixmap | None":
    """从 zip 读取封面字节并缩放为缩略图；无图/失败返回 None"""
    if not info:
        return None
    data = read_cover_bytes(info.get("path", ""))
    if not data:
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(data):
        return None
    return pixmap.scaled(
        THUMB_WIDTH, THUMB_HEIGHT,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _cover_thumbnail(info: dict, on_click=None) -> QLabel:
    """封面缩略图 QLabel；无图/加载失败 → 占位图，传入 on_click 时转为可点击"""
    if on_click is None:
        label = _placeholder_label()
    else:
        label = ClickableLabel()
        label.setFixedSize(THUMB_WIDTH, THUMB_HEIGHT)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "background-color: #e0e0e0; color: #aaa;"
            "border: 1px solid #ccc; font-size: 30px;"
        )
        label.clicked.connect(on_click)
    pixmap = _load_cover_pixmap(info)
    if pixmap is not None:
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("border: 1px solid #ccc; background-color: #f5f5f5;")
    return label


def _crop_badge() -> QLabel:
    """红色「需裁剪」角标（P2 只做展示标记，裁剪交互在 P3）"""
    badge = QLabel("需裁剪")
    badge.setStyleSheet(
        "background-color: #e53935; color: white; font-size: 10px;"
        "font-weight: bold; border-radius: 3px; padding: 1px 5px;"
    )
    return badge


def _cover_with_badge(info: dict, show_badge: bool, on_click=None) -> QWidget:
    """封面缩略图 + 右上角异常角标（同网格单元格叠加，角标浮于图右上角）"""
    container = QWidget()
    layout = QGridLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(_cover_thumbnail(info, on_click if show_badge else None), 0, 0)
    if show_badge:
        layout.addWidget(
            _crop_badge(), 0, 0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )
    return container


def _volume_card(filename: str, info: dict, on_click=None) -> QWidget:
    """单卷封面卡片：缩略图 + 文件名 + 异常角标（供卷网格使用）"""
    card = QWidget()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(_cover_with_badge(info, info.get("ratio_ok") is False, on_click))
    name_label = QLabel(os.path.basename(filename))
    name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    name_label.setWordWrap(True)
    name_label.setMaximumWidth(THUMB_WIDTH)
    name_label.setStyleSheet("color: #555; font-size: 11px;")
    layout.addWidget(name_label)
    return card


def _build_volume_grid(result: dict, make_handler) -> QWidget:
    """该系列全部卷封面的缩略图网格（固定列数，超出自动换行）"""
    covers = result.get("covers", {}) or {}
    grid = QWidget()
    grid_layout = QGridLayout(grid)
    grid_layout.setContentsMargins(0, 8, 0, 0)
    grid_layout.setSpacing(10)
    for idx, filename in enumerate(sort_volume_files(list(covers.keys()))):
        row, col = divmod(idx, GRID_COLUMNS)
        grid_layout.addWidget(
            _volume_card(filename, covers[filename], make_handler(filename)), row, col)
    return grid


def _toggle_volume_grid(result: dict, holder: QWidget, btn: QPushButton,
                        make_handler) -> None:
    """展开/收起卷封面网格（首次展开才构建，避免隐藏时批量读 zip）"""
    if holder.layout().count() == 0:
        holder.layout().addWidget(_build_volume_grid(result, make_handler))
    visible = not holder.isVisible()
    holder.setVisible(visible)
    btn.setText("收起 ▲" if visible else "展开 ▼")


def update_results_table(mw):
    # 清空现有结果（results_layout 中的所有子部件）
    while mw.results_layout.count():
        child = mw.results_layout.takeAt(0)
        if child is not None:
            w = child.widget()
            if w:
                w.deleteLater()

    def _make_crop_handler(result: dict, filename: str):
        """生成点击「需裁剪」封面 → 裁剪对话框的处理器（闭包绑定 result/filename）"""
        return lambda: _open_crop_flow(mw, result, filename)

    # 为每个结果创建一个卡片
    for row, result in enumerate(mw.scan_results):
        group_box = QGroupBox(f"{result['series']} - {result['folder_name']}")
        group_box.setStyleSheet(GROUP_BOX_STYLE)

        outer_layout = QVBoxLayout()
        header_layout = QHBoxLayout()

        # 左侧：首卷封面缩略图（异常则叠加红色角标，可点击裁剪）
        covers = result.get("covers", {}) or {}
        sorted_names = sort_volume_files(list(covers.keys()))
        first_name = sorted_names[0] if sorted_names else None
        first_info = covers.get(first_name) if first_name else None
        header_layout.addWidget(
            _cover_with_badge(
                first_info,
                bool(first_info) and first_info.get("ratio_ok") is False,
                _make_crop_handler(result, first_name) if first_name else None,
            )
        )

        # 右侧：卷数徽章 + 信息表单 + 操作
        info_layout = QVBoxLayout()

        # 卷数徽章 + 展开/收起按钮
        top_row = QHBoxLayout()
        vol_count = len(result.get("file_details", {}) or {}) or result.get("count", "")
        count_badge = QLabel(f"📚 共 {vol_count} 卷")
        count_badge.setStyleSheet(
            "background-color: #4CAF50; color: white; font-size: 11px;"
            "font-weight: bold; border-radius: 9px; padding: 2px 10px;"
        )
        top_row.addWidget(count_badge)
        top_row.addStretch()

        grid_holder = QWidget()
        grid_layout = QVBoxLayout(grid_holder)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_holder.setVisible(False)

        expand_btn = QPushButton("展开 ▼")
        expand_btn.setStyleSheet(EXPAND_BTN_STYLE)
        expand_btn.clicked.connect(
            lambda _, r=result, g=grid_holder, b=expand_btn:
            _toggle_volume_grid(r, g, b, lambda f: _make_crop_handler(r, f))
        )
        top_row.addWidget(expand_btn)
        info_layout.addLayout(top_row)

        card_layout = QFormLayout()
        card_layout.addRow("文件夹:", QLabel(result["folder_name"]))
        card_layout.addRow("系列名:", QLabel(result["series"]))
        card_layout.addRow("作者:", QLabel(result.get("writer", "")))
        card_layout.addRow("作画:", QLabel(result.get("penciller", "")))
        card_layout.addRow("上色:", QLabel(result.get("colorist", "")))
        card_layout.addRow("Web:", QLabel(result.get("web", "")))
        year_str = result.get("year", "")
        month_str = result.get("month", "")
        date_display = f"{year_str}-{month_str}" if year_str and month_str else (year_str or "")
        card_layout.addRow("发行时间:", QLabel(date_display))
        card_layout.addRow("状态:", QLabel(result["status"]))

        # 简介和标签（有值才显示）
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

        card_layout.addRow("是否Manga:", QLabel(result.get("manga", "")))

        # 操作按钮 - 突出显示
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        edit_btn = QPushButton("✏️ 编辑")
        edit_btn.setMinimumHeight(35)
        edit_btn.setMinimumWidth(100)
        edit_btn.setStyleSheet(EDIT_BTN_STYLE)
        edit_btn.clicked.connect(lambda _, r=row: mw.edit_row(r))
        button_layout.addWidget(edit_btn)
        button_layout.addStretch()
        card_layout.addRow("", button_layout)

        info_layout.addLayout(card_layout)
        header_layout.addLayout(info_layout, 1)
        outer_layout.addLayout(header_layout)
        outer_layout.addWidget(grid_holder)

        group_box.setLayout(outer_layout)
        mw.results_layout.addWidget(group_box)
