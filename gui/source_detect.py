#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动时 IP 检测模块 - 后台检测出口 IP 是否大陆，完成后切默认 Bangumi 数据源

检测完成前保持「Bangumi（官方）」默认；大陆 → 切「Bangumi（大陆镜像）」，
非大陆/检测失败 → 保持官方。检测在后台 QThread 执行，不阻塞主线程。
"""

from typing import Optional

from PySide6.QtCore import QThread, Signal

from config import SOURCE_BANGUMI_MIRROR_TEXT
from utils.geo_detect import detect_country_cn

# 测试可关闭自动检测（单元测试不发起真实网络请求）
AUTO_GEO_DETECT = True


class _GeoDetectWorker(QThread):
    """后台 IP 检测线程：完成发 detected(result) 信号（True/False/None）"""

    detected = Signal(object)

    def run(self) -> None:
        result = detect_country_cn()
        self.detected.emit(result)


def start_geo_detect(mw) -> None:
    """后台启动 IP 检测：完成前保持官方默认，检测完成按结果切默认源

    结果通过主线程信号槽应用（QThread → 主线程自动排队），不阻塞 UI。
    """
    worker = _GeoDetectWorker()
    mw._geo_detect_worker = worker
    worker.detected.connect(lambda result: _on_geo_detected(mw, result))
    worker.finished.connect(lambda: _release_worker(mw, worker))
    worker.start()


def _release_worker(mw, worker) -> None:
    """检测线程结束：清理引用，避免悬挂的 QThread 对象"""
    if getattr(mw, "_geo_detect_worker", None) is worker:
        mw._geo_detect_worker = None


def _on_geo_detected(mw, result: Optional[bool]) -> None:
    """IP 检测完成：大陆 → 默认镜像；非大陆/失败 → 保持官方

    用户已手动切过数据源则不覆盖（尊重用户选择）。
    """
    if result is not True:
        return
    if getattr(mw, "_source_user_touched", False):
        return
    index = mw.source_combo.findText(SOURCE_BANGUMI_MIRROR_TEXT)
    if index >= 0:
        mw.source_combo.setCurrentIndex(index)
