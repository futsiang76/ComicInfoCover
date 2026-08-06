#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""裁剪队列（B2）：点任意「需裁剪」封面开始，确认/跳过推进下一张，取消关闭不推进

收集当前结果页所有 ratio_ok=False 的封面为队列；对话框确定后由 _CropWorker
后台裁剪重打包，完成后自动打开下一张；跳过直接推进下一张；取消结束本次流程。
"""
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QMessageBox

from gui.crop_dialog import CropDialog
from processors.cover_crop import crop_zip_cover
from processors.cover_utils import sort_volume_files


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


def _collect_crop_queue(mw, extra=None) -> list:
    """收集裁剪队列：所有需裁剪封面（ratio_ok=False 且有路径）+ 可选附加目标封面

    Args:
        mw: 主窗口（从 scan_results 收集异常封面）
        extra: (result, filename) —— 目标封面即使比例合格也加入队列（合格封面可点击裁剪）
    """
    queue = []
    for r in mw.scan_results:
        covers = r.get("covers", {}) or {}
        for fname in sort_volume_files(list(covers.keys())):
            info = covers[fname]
            if info and info.get("ratio_ok") is False and info.get("path"):
                queue.append((r, fname, info))
    if extra is not None:
        result, filename = extra
        covers = result.get("covers", {}) or {}
        info = covers.get(filename)
        if info and info.get("path") and not any(
                r is result and f == filename for r, f, _ in queue):
            queue.append((result, filename, info))
    return queue


def _run_crop_queue(mw, queue: list, index: int) -> None:
    """从 index 起逐个弹裁剪对话框：确认/跳过推进下一张，取消关闭但不推进"""
    while index < len(queue):
        result, filename, info = queue[index]
        dialog = CropDialog(info["path"], mw)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            region = dialog.crop_region
            if isinstance(region, tuple):
                mw.crop_running = True
                worker = _CropWorker(info["path"], region, mw)
                worker.done.connect(
                    lambda new_info, m=mw, q=queue, i=index, r=result, f=filename:
                    _on_crop_done(m, r, f, new_info, q, i))
                worker.failed.connect(
                    lambda msg, m=mw, q=queue, i=index, f=filename:
                    _on_crop_failed(m, f, msg, q, i))
                mw._crop_worker = worker  # 持有引用，防止 worker 被 GC
                worker.start()
                return
        if dialog.crop_region == "SKIP_PROCESS":
            index += 1  # 跳过：自动打开下一张需裁剪的图
            continue
        return  # 取消：关闭但不推进


def _open_crop_flow(mw, result, filename):
    """点击封面 → 收集裁剪队列并从该张开始逐个处理

    目标封面即使比例合格也加入队列（合格封面可点击裁剪，从该张开始）。
    """
    if getattr(mw, "crop_running", False):
        return
    queue = _collect_crop_queue(mw, extra=(result, filename))
    if not queue:
        return
    start = next((i for i, (r, f, _) in enumerate(queue)
                  if r is result and f == filename), 0)
    _run_crop_queue(mw, queue, start)


def _open_single_crop_flow(owner, covers, filename, on_done=None):
    """单张封面裁剪入口（标题编辑对话框等非结果页场景复用）

    打开该卷裁剪对话框；确定后后台裁剪重打包，完成后原地更新 covers 并回调 on_done。
    取消 / 跳过 / 已有裁剪在跑时不做任何处理。

    Args:
        owner: 宿主对话框（需可挂 crop_running 标志与后台 worker 引用）
        covers: {文件名: 封面信息} 字典，裁剪完成后更新该卷封面信息
        filename: 目标卷文件名
        on_done: 裁剪完成后的回调（刷新界面缩略图）
    """
    if getattr(owner, "crop_running", False):
        return
    info = covers.get(filename) if covers else None
    if not info or not info.get("path"):
        return
    dialog = CropDialog(info["path"], owner)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    region = dialog.crop_region
    if not isinstance(region, tuple):
        return
    owner.crop_running = True
    worker = _CropWorker(info["path"], region, owner)
    worker.done.connect(
        lambda new_info, c=covers, f=filename, cb=on_done:
        _on_single_crop_done(owner, c, f, new_info, cb))
    worker.failed.connect(
        lambda msg, f=filename: _on_single_crop_failed(owner, f, msg))
    owner._crop_worker = worker
    worker.start()


def _on_single_crop_done(owner, covers, filename, new_info, on_done):
    """单张裁剪完成：更新封面信息并触发回调（如刷新缩略图）"""
    owner.crop_running = False
    if new_info:
        covers[filename] = new_info
    if on_done is not None:
        on_done()


def _on_single_crop_failed(owner, filename, message):
    """单张裁剪失败：恢复可裁剪状态并提示"""
    owner.crop_running = False
    QMessageBox.warning(owner, "裁剪失败", f"{filename} 封面裁剪失败：{message}")


def _on_crop_done(mw, result, filename, new_info, queue=None, next_index=None):
    """裁剪完成：更新封面信息并重渲染；队列流程中继续打开下一张需裁剪的图"""
    mw.crop_running = False
    if new_info:
        result["covers"][filename] = new_info
    mw.update_results_table()
    if queue is not None and next_index is not None and next_index + 1 < len(queue):
        _run_crop_queue(mw, queue, next_index + 1)


def _on_crop_failed(mw, filename, message, queue=None, next_index=None):
    """裁剪失败：恢复可裁剪状态并提示；队列流程中继续下一张"""
    mw.crop_running = False
    QMessageBox.warning(mw, "裁剪失败", f"{filename} 封面裁剪失败：{message}")
    if queue is not None and next_index is not None and next_index + 1 < len(queue):
        _run_crop_queue(mw, queue, next_index + 1)
