#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量保存 - 将编辑后的元数据写入XML文件

写盘循环移入 SaveThread（gui/save_thread.py）后台执行：保存期间主线程
事件循环保持空闲，工作小猫动画正常播放，UI 不冻结。
"""

from functools import partial

from PySide6.QtWidgets import QMessageBox

from .save_thread import SaveThread
from .utils import set_results_saving, start_loading_cat, stop_loading_cat


def _scan_running(mw) -> bool:
    """扫描线程是否仍在运行（用于判断小猫动画当前归属方）"""
    thread = getattr(mw, "scan_thread", None)
    return thread is not None and thread.isRunning()


def save_changes(mw, show_result: bool = True):
    # 互斥：已有保存线程在跑时拦截重复触发（用户连点「保存」会启动多个
    # SaveThread 并发写同一批 zip → 互相锁文件 WinError 5 + 多份相同 tmp）。
    # 全匹配模式的逐系列保存已改走 save_single_result（自带等待队列，绝不并发），
    # 不再经过本函数；此处仅服务用户手动保存按钮。
    if not _scan_running(mw) and any(
        t.isRunning() for t in getattr(mw, "_save_threads", [])
    ):
        QMessageBox.information(mw, "提示", "正在保存中，请稍候")
        return

    modified_results = [r for r in mw.scan_results if r.get("process_status") == "已修改"]

    if not modified_results:
        QMessageBox.information(mw, "提示", "没有需要保存的修改")
        return

    _start_save_thread(mw, modified_results, show_result)


def save_single_result(mw, result: dict, show_result: bool = False) -> None:
    """逐系列保存：只写盘当前这一个 result（全匹配模式每个系列确认后调用）

    已有保存线程在跑时结果进入等待队列（FIFO），前一个完成后自动续写——
    任意时刻保存线程数 ≤1，绝不并发写盘；每个已确认系列都保证落盘，
    且不会把前面的系列重复写入（旧实现调 save_changes 会把 scan_results 里
    所有"已修改"结果一起写，导致 A 被后续保存反复重写 + 多线程锁文件）。
    """
    if any(t.isRunning() for t in getattr(mw, "_save_threads", [])):
        pending = list(getattr(mw, "_save_pending", []))
        pending.append((result, show_result))
        mw._save_pending = pending
        return

    _start_save_thread(mw, [result], show_result)


def _start_save_thread(mw, results: list, show_result: bool) -> None:
    """启动一个保存线程（save_changes / save_single_result 共用启动逻辑）"""
    start_loading_cat(mw)  # 保存写入阶段显示工作小猫动画（主线程空闲，动画正常播放）

    thread = SaveThread(results, mw)
    thread.save_finished.connect(partial(_on_save_finished, mw, show_result, results))

    # 保留运行中线程引用，防止 QThread 在运行期间被垃圾回收
    running = [t for t in getattr(mw, "_save_threads", []) if t.isRunning()]
    running.append(thread)
    mw._save_threads = running

    thread.start()

    # 写盘进行中：结果页可交互元素禁用 + 显示工作小猫（不重建卡片，避免写盘期间并发读 zip）
    mw._save_count = getattr(mw, "_save_count", 0) + 1
    set_results_saving(mw, True)


def _start_next_pending_save(mw) -> None:
    """前一保存线程完成后的队列续写：跳过已被其它路径写盘的 result，避免重复写"""
    pending = list(getattr(mw, "_save_pending", []))
    while pending:
        result, show_result = pending.pop(0)
        if result.get("process_status") != "已修改":
            continue  # 已被手动保存等路径写盘 → 跳过，避免重复写
        mw._save_pending = pending
        _start_save_thread(mw, [result], show_result)
        return
    mw._save_pending = []


def _on_save_finished(mw, show_result: bool, modified_results: list, total_files: int,
                      success_files: int, error_messages: list) -> None:
    """保存线程完成（主线程槽）：收尾小猫动画 + 更新状态 + 结果弹窗"""
    mw._save_count = max(0, getattr(mw, "_save_count", 0) - 1)  # 写盘计数-1，update_results_table 据此恢复交互
    # 扫描进行中的逐系列保存由扫描流程负责收尾小猫，此处不重复停止
    if not _scan_running(mw):
        stop_loading_cat(mw)

    # 仅更新本次实际保存的结果（与线程启动时快照一致，避免误改保存期间新编辑的行）
    for result in modified_results:
        result["process_status"] = "已保存"

    mw.update_results_table()

    # 逐系列保存等待队列续写：前一个保存线程完成后启动下一个（任意时刻保存线程数 ≤1）
    _start_next_pending_save(mw)

    if show_result:
        msg = f"保存完成\n\n总文件数: {total_files}\n成功: {success_files}\n失败: {total_files - success_files}"
        if error_messages:
            msg += "\n\n错误信息:\n" + "\n".join(error_messages[:10])
            if len(error_messages) > 10:
                msg += f"\n...还有 {len(error_messages) - 10} 个错误"

        if total_files - success_files > 0:
            QMessageBox.warning(mw, "保存结果", msg)
        else:
            QMessageBox.information(mw, "保存结果", msg)
