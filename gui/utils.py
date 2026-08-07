#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享工具函数
"""

from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import QApplication, QLabel


class SmoothMovieLabel(QLabel):
    """平滑缩放动画帧的 QLabel：QMovie 帧 → QPixmap.scaled(SmoothTransformation) → setPixmap

    Qt 6 在 Windows 高 DPI 下整个 GUI 物理放大；QLabel 直接 setMovie 时 Qt 用
    FastTransformation 重采样导致锯齿。改为每帧按 label 当前物理尺寸（含 DPR）
    手动 SmoothTransformation 缩放后 setPixmap，消除放大锯齿。
    """

    def __init__(self, movie: QMovie, parent=None):
        super().__init__(parent)
        self._movie = movie
        self._movie.setParent(self)  # 生命周期挂 label 防 GC
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)  # 缩放交给 _on_frame 平滑处理
        movie.frameChanged.connect(self._on_frame)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def _on_frame(self, frame: int) -> None:
        pix = self._movie.currentPixmap()
        if pix.isNull():
            return
        target = self.size()  # label 逻辑尺寸；物理尺寸由 DPR 缩放
        if target.isValid() and not target.isEmpty():
            dpr = self.devicePixelRatioF()
            physical = QSize(round(target.width() * dpr), round(target.height() * dpr))
            pix = pix.scaled(physical, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            pix.setDevicePixelRatio(dpr)
        self.setPixmap(pix)

    def start(self) -> None:
        self._movie.start()
        # 启动时立即按当前 label 尺寸平滑渲染当前帧，不等待定时器首帧
        self._on_frame(self._movie.currentFrameNumber())

    def stop(self) -> None:
        self._movie.stop()


def _trim_compare_dicts(old_dict: dict, new_dict: dict) -> bool:
    """递归比较两个字典，对所有字符串值做strip后比较，返回True表示有差异"""
    all_keys = set(old_dict.keys()) | set(new_dict.keys())
    for k in all_keys:
        old_v = old_dict.get(k)
        new_v = new_dict.get(k)
        if isinstance(old_v, dict) and isinstance(new_v, dict):
            if _trim_compare_dicts(old_v, new_v):
                return True
        elif isinstance(old_v, dict) or isinstance(new_v, dict):
            return True
        else:
            if str(old_v).strip() != str(new_v).strip():
                return True
    return False


def start_loading_cat(mw) -> None:
    """显示工作小猫加载动画（幂等）：定位浮层 + 展示 + 启动帧播放

    扫描线程化后主线程事件循环空闲，QMovie 由事件循环自然驱动跳帧；
    processEvents 泵一次确保首帧立即上屏，无需复杂 pump。
    """
    label = getattr(mw, "loading_cat_label", None)
    if label is None:
        return
    # 挂主窗口：左下角对齐下方进度条左下角，悬浮于所有内容之上
    progress = getattr(mw, "progress_bar", None)
    if progress is not None:
        # 进度条相对主窗口的左上角 + 自身高度 → 左下角；label 底部与之平齐
        progress_pos = progress.mapTo(mw, QPoint(0, 0))
        label.move(progress_pos.x(), progress_pos.y() + progress.height() - label.height())
    label.show()
    label.raise_()  # 浮到主窗口内容之上不被遮挡
    label.start()
    QApplication.processEvents()


def stop_loading_cat(mw) -> None:
    """停止工作小猫加载动画（幂等）：停帧 + 隐藏"""
    label = getattr(mw, "loading_cat_label", None)
    if label is None:
        return
    label.stop()
    label.hide()


def save_threads_running(mw) -> bool:
    """是否有写盘线程仍在运行

    计数由 save_handler 维护（save_changes +1、_on_save_finished -1），比直接
    查 mw._save_threads 的 isRunning 更稳：QThread 在 run() 末尾 emit
    save_finished 时尚未置 isRunning=False，主线程槽此时查 isRunning 可能误判
    为仍在写盘，导致结果页交互元素恢复不了。
    """
    return getattr(mw, "_save_count", 0) > 0


def set_results_saving(mw, saving: bool) -> None:
    """写盘期间禁用结果页可交互元素（展开/编辑/封面裁剪）并显示工作小猫；完成后恢复"""
    for widget in getattr(mw, "_interactive_widgets", []):
        if widget is not None:
            widget.setEnabled(not saving)
    label = getattr(mw, "results_cat_label", None)
    if label is not None:
        if saving:
            label.show()
            label.raise_()  # 浮到最上层
            # 窗体正中心（先 adjustSize 确保尺寸正确）
            label.adjustSize()
            mw_w, mw_h = mw.width(), mw.height()
            label.move((mw_w - label.width()) // 2, (mw_h - label.height()) // 2)
            label.start()
            QApplication.processEvents()
        else:
            label.stop()
            label.hide()
