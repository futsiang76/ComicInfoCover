#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面裁剪对话框（P3，PyQt6）— 移植 007 ui/crop_selector.py 的交互语义

- 显示原图 + 锁定竖版 870x1230 比例的裁剪框（拖拽移动 + 右下角手柄等比缩放，不能拉成横版）
- 初始裁剪框居中（007 智能推荐区域 → P4 记忆系统再引入）
- 按钮对齐 007：确定(裁剪)/取消/跳过
- 画布随窗口 resize：图片等比缩放，裁剪框坐标在 原图坐标 ↔ 显示坐标 之间换算（B1）

结果语义（对齐 007 crop_selector）：
    确定 → crop_region = (x, y, w, h) 原图坐标，对话框返回 Accepted
    取消 → crop_region = None，返回 Rejected
    跳过 → crop_region = "SKIP_PROCESS"，返回 Rejected
"""
import os

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from processors.cover_utils import (STANDARD_HEIGHT, STANDARD_WIDTH,
                                    get_zip_first_image, read_zip_entry)

HANDLE_SIZE = 14          # 右下角缩放手柄边长
MIN_CROP_HEIGHT = 40      # 裁剪框最小高度（显示坐标）

BTN_STYLE = """
    QPushButton { font-size: 13px; padding: 6px 18px; border-radius: 5px; }
"""
OK_STYLE = """
    QPushButton { background-color: #e53935; color: white; font-weight: bold; }
    QPushButton:hover { background-color: #c62828; }
"""
PLAIN_STYLE = """
    QPushButton { background-color: #f0f0f0; color: #555; border: 1px solid #ccc; }
    QPushButton:hover { background-color: #e0e0e0; }
"""


class _CropCanvas(QWidget):
    """裁剪画布：渲染缩放后的原图 + 遮罩 + 锁定比例的裁剪框 + 缩放手柄

    画布尺寸由对话框布局驱动（去掉固定尺寸，可随窗口 resize）。
    图片按画布尺寸等比缩放显示；裁剪框以「原图坐标」为基准，resize 时按新缩放
    换算显示坐标，保证窗口拖大后图片与裁剪框同步放大（B1）。
    """

    CROP_RATIO = STANDARD_WIDTH / STANDARD_HEIGHT  # 870/1230 ≈ 0.707

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._error = None
        self._disp_rect = QRectF()   # 图片在画布上的显示区域
        self._scale = 1.0            # 显示坐标 → 原图坐标的缩放
        self._orig_crop = QRectF()   # 裁剪框（原图坐标，resize 时保持稳定）
        self._crop = QRectF()        # 裁剪框（显示坐标，由 _orig_crop 换算）
        self._dragging = False
        self._resizing = False
        self._drag_anchor = QPointF()
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)

    # ---------- 图片装载 ----------

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """设置原图并初始化居中裁剪框"""
        self._pixmap = pixmap
        self._error = None
        self._layout_image()
        self._orig_crop = self._initial_crop()
        self._crop = self._to_display(self._orig_crop)
        self.update()

    def set_error(self, message: str) -> None:
        """图片加载失败时显示错误提示"""
        self._error = message
        self.update()

    def resizeEvent(self, event) -> None:
        """画布尺寸变化：重排图片显示区，并按新缩放重算裁剪框显示坐标"""
        self._layout_image()
        if self._pixmap is not None:
            self._crop = self._to_display(self._orig_crop)
        self.update()

    def _layout_image(self) -> None:
        """按当前画布尺寸等比缩放原图，居中放置（不放大超过原图）"""
        if self._pixmap is None:
            return
        img_w, img_h = self._pixmap.width(), self._pixmap.height()
        scale = min(self.width() / img_w, self.height() / img_h, 1.0)
        disp_w, disp_h = img_w * scale, img_h * scale
        self._disp_rect = QRectF((self.width() - disp_w) / 2,
                                 (self.height() - disp_h) / 2,
                                 disp_w, disp_h)
        self._scale = scale

    def _initial_crop(self) -> QRectF:
        """初始裁剪框（原图坐标）：满足 870x1230 比例的最大内接框，居中"""
        img_w, img_h = self._pixmap.width(), self._pixmap.height()
        if img_w / img_h >= self.CROP_RATIO:
            h = img_h
            w = img_h * self.CROP_RATIO
            x = (img_w - w) / 2
            y = 0.0
        else:
            w = img_w
            h = img_w / self.CROP_RATIO
            x = 0.0
            y = (img_h - h) / 2
        return QRectF(x, y, w, h)

    def _to_display(self, orig: QRectF) -> QRectF:
        """原图坐标裁剪框 → 显示坐标（基于当前显示区与缩放）"""
        s = self._scale
        return QRectF(self._disp_rect.x() + orig.x() * s,
                      self._disp_rect.y() + orig.y() * s,
                      orig.width() * s, orig.height() * s)

    def _from_display(self, disp: QRectF) -> QRectF:
        """显示坐标裁剪框 → 原图坐标"""
        s = self._scale
        return QRectF((disp.x() - self._disp_rect.x()) / s,
                      (disp.y() - self._disp_rect.y()) / s,
                      disp.width() / s, disp.height() / s)

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f0f0f0"))
        if self._error:
            painter.setPen(QColor("#555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._error)
            return
        if self._pixmap is None:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self._disp_rect.toRect(), self._pixmap)
        # 裁剪框外半透明遮罩（OddEven 填充规则 → 裁剪框内留空）
        mask = QPainterPath()
        mask.addRect(self._disp_rect)
        mask.addRect(self._crop)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 110))
        painter.drawPath(mask)
        # 裁剪框边框
        painter.setPen(QPen(QColor("#e53935"), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._crop)
        # 右下角缩放手柄
        painter.setPen(QPen(QColor("#e53935"), 1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRect(self._handle_rect())

    def _handle_rect(self) -> QRectF:
        return QRectF(self._crop.right() - HANDLE_SIZE,
                      self._crop.bottom() - HANDLE_SIZE,
                      HANDLE_SIZE, HANDLE_SIZE)

    # ---------- 鼠标交互 ----------

    def mousePressEvent(self, event) -> None:
        if self._pixmap is None:
            return
        pos = event.position()
        if self._handle_rect().contains(pos):
            self._resizing = True
        elif self._crop.contains(pos):
            self._dragging = True
            self._drag_anchor = QPointF(pos.x() - self._crop.x(),
                                        pos.y() - self._crop.y())

    def mouseMoveEvent(self, event) -> None:
        if self._pixmap is None or not (self._dragging or self._resizing):
            return
        pos = event.position()
        if self._dragging:
            self._crop.moveTo(pos.x() - self._drag_anchor.x(),
                              pos.y() - self._drag_anchor.y())
            self._clamp_move()
        else:
            self._resize_to(pos)
        self._orig_crop = self._from_display(self._crop)  # 每次交互同步原图坐标
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        self._resizing = False

    def _clamp_move(self) -> None:
        """裁剪框移动不超出图片显示区域"""
        x = max(self._disp_rect.x(),
                min(self._crop.x(), self._disp_rect.right() - self._crop.width()))
        y = max(self._disp_rect.y(),
                min(self._crop.y(), self._disp_rect.bottom() - self._crop.height()))
        self._crop.moveTo(x, y)

    def _resize_to(self, pos: QPointF) -> None:
        """右下角手柄缩放：左上角固定，右下角跟随鼠标，始终锁定比例"""
        x1, y1 = self._crop.x(), self._crop.y()
        max_h = self._disp_rect.bottom() - y1
        h = max(MIN_CROP_HEIGHT, min(pos.y() - y1, max_h))
        w = h * self.CROP_RATIO
        max_w = self._disp_rect.right() - x1
        if w > max_w:  # 宽度到边界时退回等比高度
            w = max_w
            h = w / self.CROP_RATIO
        self._crop.setRect(x1, y1, w, h)

    # ---------- 输出 ----------

    def crop_region(self) -> tuple:
        """返回原图坐标裁剪区域 (x, y, width, height)"""
        x = int(round(self._orig_crop.x()))
        y = int(round(self._orig_crop.y()))
        w = max(1, int(round(self._orig_crop.width())))
        h = max(1, int(round(self._orig_crop.height())))
        return (x, y, w, h)


class CropDialog(QDialog):
    """封面裁剪对话框（PyQt6，锁定 870x1230 比例）"""

    def __init__(self, zip_path: str, parent=None):
        super().__init__(parent)
        self.zip_path = zip_path
        self.cover_name = None
        self.crop_region = None  # 确定时设置 (x, y, w, h) 原图坐标
        self.setWindowTitle("裁剪封面")
        self.resize(1000, 780)
        self._init_ui()
        self._load_cover()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        tip = QLabel(f"裁剪框锁定竖版 {STANDARD_WIDTH}x{STANDARD_HEIGHT} 比例：拖拽移动，右下角手柄等比缩放")
        tip.setStyleSheet("color: #555; font-size: 12px; padding: 2px 4px;")
        layout.addWidget(tip)

        self.canvas = _CropCanvas()
        layout.addWidget(self.canvas)

        self.path_label = QLabel(os.path.basename(self.zip_path))
        self.path_label.setStyleSheet("color: #999; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(self.path_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定 (Enter)")
        ok_btn.setObjectName("crop_ok")
        ok_btn.setStyleSheet(BTN_STYLE + OK_STYLE)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("取消 (Esc)")
        cancel_btn.setObjectName("crop_cancel")
        cancel_btn.setStyleSheet(BTN_STYLE + PLAIN_STYLE)
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)

        skip_btn = QPushButton("跳过")
        skip_btn.setObjectName("crop_skip")
        skip_btn.setStyleSheet(BTN_STYLE + PLAIN_STYLE)
        skip_btn.clicked.connect(self._on_skip)
        btn_layout.addWidget(skip_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.ok_btn = ok_btn

    def _load_cover(self) -> None:
        """读取 zip 首图并交给画布渲染"""
        cover_name = get_zip_first_image(self.zip_path)
        self.cover_name = cover_name
        if not cover_name:
            self.ok_btn.setEnabled(False)
            self.canvas.set_error("ZIP 内未找到封面图片")
            return
        data = read_zip_entry(self.zip_path, cover_name)
        pixmap = QPixmap()
        if not data or not pixmap.loadFromData(data):
            self.ok_btn.setEnabled(False)
            self.canvas.set_error("封面图片加载失败")
            return
        self.canvas.set_pixmap(pixmap)

    def _on_ok(self) -> None:
        region = self.canvas.crop_region()
        if region[2] <= 0 or region[3] <= 0:
            return
        self.crop_region = region
        self.accept()

    def _on_cancel(self) -> None:
        """取消：不裁剪不改文件"""
        self.crop_region = None
        self.reject()

    def _on_skip(self) -> None:
        """跳过：本次不处理该卷封面"""
        self.crop_region = "SKIP_PROCESS"
        self.reject()
