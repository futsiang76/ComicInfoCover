#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享工具函数
"""

from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import QApplication


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
    movie = getattr(mw, "loading_cat_movie", None)
    if label is None or movie is None:
        return
    # 挂主窗口：直接定位窗体左上角，悬浮于所有内容之上
    label.move(8, 8)
    label.show()
    label.raise_()  # 浮到主窗口内容之上不被遮挡
    if movie.state() != QMovie.MovieState.Running:
        movie.start()
    QApplication.processEvents()


def stop_loading_cat(mw) -> None:
    """停止工作小猫加载动画（幂等）：停帧 + 隐藏"""
    movie = getattr(mw, "loading_cat_movie", None)
    label = getattr(mw, "loading_cat_label", None)
    if movie is not None and movie.state() == QMovie.MovieState.Running:
        movie.stop()
    if label is not None:
        label.hide()
