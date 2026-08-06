#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描控制逻辑 - 扫描启动/停止/进度/完成回调
"""

import os
from functools import partial
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import QMessageBox

from .scan_thread import ScanThread
from .edit_dialog import EditDialog
from .gui_dialogs import DialogBridge, show_bangumi_id_not_found
from .utils import start_loading_cat, stop_loading_cat


def start_scan(mw):
    """开始扫描"""
    manga_root = mw.path_edit.text().strip()
    if not manga_root:
        QMessageBox.warning(mw, "警告", "请先选择漫画根目录")
        return

    if not os.path.isdir(manga_root):
        QMessageBox.warning(mw, "警告", "指定的目录不存在")
        return

    # 数据源路由：manhuagui / ComicVine 走「多系列拦截 → 单系列扫描」
    source = getattr(mw, "selected_source", "Bangumi（默认）")
    if source == "manhuagui":
        _start_manhuagui_scan(mw, manga_root)
        return
    if source == "ComicVine":
        _start_comicvine_scan(mw, manga_root)
        return

    # 弹出对话框询问是否为Manga
    manga_value = _ask_manga_setting(mw)
    if manga_value is None:
        # 用户点击取消
        return

    # 获取配置
    mode = mw.mode_group.checkedId()
    auto_turbo = 1 if mw.auto_turbo_check.isChecked() else 0
    use_local_only = mw.local_only_check.isChecked()

    # 手动匹配模式：Bangumi ID 在扫描过程中逐文件夹输入，此处无需提前获取
    bangumi_id = None

    # 清空日志
    mw.log_text.clear()
    mw.log_text.append(f"开始扫描: {manga_root}")
    mw.log_text.append(f"模式: {mw.mode_group.checkedButton().text()}")
    mw.log_text.append(f"无人值守: {'开启' if auto_turbo else '关闭'}")
    mw.log_text.append(f"仅使用本地信息: {'是' if use_local_only else '否'}")
    mw.log_text.append(f"Manga设置: {manga_value}")

    # 清空结果
    mw.scan_results = []
    mw.update_results_table()

    # 手动匹配模式：逐个系列文件夹「输入→查询→确认」，在主线程循环（不走 ScanThread 批量流程）
    if mode == 3:
        _run_manual_match_scan(mw, manga_root, manga_value)
        return

    # 全匹配模式（非无人值守）：逐个系列「扫描→确认→保存」，后台线程执行
    # （弹窗经 DialogBridge 桥接主线程，进度/日志/结果经信号更新，主线程不阻塞）
    if mode == 0 and auto_turbo != 1:
        from .full_match_scan import FullMatchThread

        thread = FullMatchThread(manga_root, manga_value, parent=mw)
        mw.scan_thread = thread
        thread.progress_updated.connect(partial(_on_full_match_progress, mw))
        thread.progress_range.connect(partial(_on_full_match_progress_range, mw))
        thread.log_message.connect(partial(_on_full_match_log, mw))
        thread.scan_completed.connect(partial(_on_full_match_completed, mw))
        thread.series_saved.connect(partial(_on_full_match_series_saved, mw))
        thread.series_finished.connect(partial(_on_full_match_series_finished, mw))
        thread.error_occurred.connect(partial(on_error_occurred, mw))

        mw.scan_btn.setEnabled(False)
        mw.stop_btn.setEnabled(True)
        mw.progress_bar.setRange(0, 0)  # 不确定进度（后台线程开始时由信号校正）

        start_loading_cat(mw)  # 全匹配扫描等待期显示工作小猫动画

        thread.start()
        return

    # 创建并启动扫描线程
    mw.scan_thread = ScanThread(manga_root, mode, auto_turbo, manga_value, use_local_only, bangumi_id, parent=mw)
    mw.scan_thread.progress_updated.connect(mw.on_progress_updated)
    mw.scan_thread.scan_completed.connect(mw.on_scan_completed)
    mw.scan_thread.error_occurred.connect(mw.on_error_occurred)

    mw.scan_btn.setEnabled(False)
    mw.stop_btn.setEnabled(True)
    mw.progress_bar.setRange(0, 0)  # 不确定进度

    mw.scan_thread.start()


def _ask_manga_setting(mw) -> Optional[str]:
    """弹出 Manga 设置对话框，返回 'Yes'/'No'/None（取消）"""
    manga_dialog = QMessageBox(mw)
    manga_dialog.setWindowTitle("Manga设置")
    manga_dialog.setText("请选择是否为Manga（漫画）")
    manga_dialog.setInformativeText("此设置将应用于所有扫描到的文件")
    yes_btn = manga_dialog.addButton("是 (Yes)", QMessageBox.ButtonRole.YesRole)
    no_btn = manga_dialog.addButton("否 (No)", QMessageBox.ButtonRole.NoRole)
    manga_dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    manga_dialog.exec()

    if manga_dialog.clickedButton() == yes_btn:
        return "Yes"
    if manga_dialog.clickedButton() == no_btn:
        return "No"
    return None


def _start_manhuagui_scan(mw, manga_root: str) -> None:
    """manhuagui 源扫描入口：依赖检查 → 多系列拦截 → 单系列扫描

    manhuagui 源只支持单系列目录：多系列在扫描前拦截弹窗，不开始扫。
    依赖未装成功（用户取消/安装失败）直接返回，不影响 Bangumi 源。
    """
    from models.manhuagui_deps import ensure_manhuagui_deps

    # 1. 依赖检查
    if not ensure_manhuagui_deps(mw):
        return

    # 2. 多系列拦截
    folders = _collect_series_folders(manga_root)
    if len(folders) > 1:
        QMessageBox.warning(
            mw, "数据源限制",
            "manhuagui 源只支持单系列扫描，请拆分成单系列目录或用 Bangumi 源",
        )
        return

    # 3. Manga 设置（与 Bangumi 流程一致）
    manga_value = _ask_manga_setting(mw)
    if manga_value is None:
        return

    # 3.5 清空日志/结果（主线程操作，对应原 _run_manhuagui_single_scan 的初始化）
    mw.log_text.clear()
    mw.log_text.append(f"开始扫描: {manga_root}")
    mw.log_text.append("数据源: manhuagui")
    mw.log_text.append(f"Manga设置: {manga_value}")
    mw.scan_results = []
    mw.update_results_table()

    # 4. 单系列扫描流程（搜索走 manhuagui，后台线程执行，对齐全匹配 FullMatchThread）
    from .manhuagui_scan import ManhuaguiScanThread

    thread = ManhuaguiScanThread(manga_root, manga_value, folders, parent=mw)
    mw.scan_thread = thread
    thread.progress_updated.connect(partial(_on_full_match_progress, mw))
    thread.progress_range.connect(partial(_on_full_match_progress_range, mw))
    thread.log_message.connect(partial(_on_full_match_log, mw))
    thread.scan_completed.connect(partial(_on_full_match_completed, mw))
    thread.series_saved.connect(partial(_on_full_match_series_saved, mw))
    thread.series_finished.connect(partial(_on_manhuagui_series_finished, mw))
    thread.error_occurred.connect(partial(on_error_occurred, mw))

    mw.scan_btn.setEnabled(False)
    mw.stop_btn.setEnabled(True)
    mw.progress_bar.setRange(0, 0)  # 不确定进度（后台线程开始时由信号校正）

    start_loading_cat(mw)  # manhuagui 扫描等待期显示工作小猫动画

    thread.start()


def _start_comicvine_scan(mw, manga_root: str) -> None:
    """ComicVine 源扫描入口：多系列拦截 → Manga 设置 → 单系列扫描

    ComicVine 源只支持单系列目录：多系列在扫描前拦截弹窗，不开始扫。
    requests 直连无额外依赖，无需依赖检查（与 manhuagui 分支不同）。
    """
    # 1. 多系列拦截
    folders = _collect_series_folders(manga_root)
    if len(folders) > 1:
        QMessageBox.warning(
            mw, "数据源限制",
            "ComicVine 源只支持单系列扫描，请拆分成单系列目录或用 Bangumi 源",
        )
        return

    # 2. Manga 设置（与 Bangumi 流程一致）
    manga_value = _ask_manga_setting(mw)
    if manga_value is None:
        return

    # 3. 单系列扫描流程（搜索走 ComicVine）
    from .comicvine_scan import _run_comicvine_single_scan
    _run_comicvine_single_scan(mw, manga_root, manga_value, folders)


def _collect_series_folders(manga_root: str) -> List[Tuple[str, Dict]]:
    """收集目标目录下的系列文件夹列表（直接包含漫画文件的目录）

    高一层目录已收集为系列时，其子目录不再重复收集（与递归扫描语义一致）。

    Args:
        manga_root: 漫画根目录

    Returns:
        List[Tuple[str, Dict]]: [(folder_path, folder_info), ...]
    """
    from parsers.file_parser import parse_folder_from_filename
    from parsers.folder_parser import parse_folder_name

    comic_ext = ('.zip', '.cbz', '.cbr', '.rar')
    folders = []
    collected = []
    for root, dirs, files in os.walk(manga_root):
        # 父级已是系列文件夹时跳过其后代，避免重复处理
        if any(root.startswith(parent + os.sep) for parent in collected):
            continue
        if not any(f.lower().endswith(comic_ext) for f in files):
            continue
        folder_info = parse_folder_name(os.path.basename(root), root)
        if not folder_info:
            folder_info = parse_folder_from_filename(root)
        if folder_info:
            collected.append(root)
            folders.append((root, folder_info))
    return folders


def _run_manual_match_scan(mw, manga_root: str, manga_value: Optional[str]) -> None:
    """手动匹配模式主流程：在主线程逐个系列文件夹「输入→查询→确认」

    每个文件夹：
      1. 弹窗输入 Bangumi ID（0=使用本地文件夹信息）
      2. 查询 Bangumi 详情并构建 comic_info_base（本地则直接构建）
      3. 构建结果并立即弹 EditDialog 确认
      4. 确认后写入 XML，进入下一个文件夹
    """
    from PyQt6.QtWidgets import QDialog

    from models.bangumi_fetcher import BangumiFetcher
    from processors.result_builder import create_result_dict
    from processors.single_series_processor import build_comic_info_from_id
    from processors.xml_template_handler import create_xml_template_handler

    mw.scan_btn.setEnabled(False)
    mw.stop_btn.setEnabled(True)

    folders = _collect_series_folders(manga_root)
    total = len(folders)
    mw.progress_bar.setRange(0, max(1, total))
    mw.progress_bar.setValue(0)

    fetcher = BangumiFetcher()
    template_handler = create_xml_template_handler()
    processed = 0
    skipped = 0

    for idx, (folder_path, folder_info) in enumerate(folders, start=1):
        mw.progress_bar.setValue(idx - 1)
        folder_name = os.path.basename(folder_path)
        mw.log_text.append(f"\n[{idx}/{total}] 📁 {folder_name}")

        # 1. 输入 Bangumi ID
        bangumi_id = DialogBridge._show_single_series_input(mw, folder_path, folder_info)
        if not bangumi_id:
            mw.log_text.append("⏭️ 未输入，跳过此系列")
            skipped += 1
            continue

        # 2. 查询并构建 comic_info_base
        if bangumi_id == "0":
            # 3.2 输入 0：按本地文件夹信息构建，不查 Bangumi
            comic_info_base = template_handler.create_local_template(folder_info)
            selected_result = None
            mw.log_text.append("📋 使用本地文件夹信息")
        else:
            try:
                numeric_id = int(bangumi_id)
            except ValueError:
                QMessageBox.warning(mw, "无效输入", f"Bangumi ID 必须是数字: {bangumi_id}，跳过此系列")
                mw.log_text.append("❌ 无效的 Bangumi ID，跳过")
                skipped += 1
                continue
            built = build_comic_info_from_id(fetcher, numeric_id, folder_info)
            if not built:
                # 3.3 查询失败：报错后自动跳过，进入下一个文件夹
                show_bangumi_id_not_found(mw, bangumi_id, folder_name)
                mw.log_text.append("❌ 未找到该 ID 的作品，跳过此系列")
                skipped += 1
                continue
            comic_info_base, selected_result = built
            title_cn = selected_result.get("name_cn") or selected_result.get("name", "")
            mw.log_text.append(f"🎯 获取到: {title_cn}")
        comic_info_base["Manga"] = manga_value or comic_info_base.get("Manga", "Yes")

        # 3. 构建结果并立即弹编辑确认
        result = create_result_dict(folder_path, folder_info, comic_info_base,
                                    selected_result, skipped=False, process_status="已修改")
        dialog = EditDialog(result, mw)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            mw.log_text.append("⏭️ 取消编辑，跳过此系列")
            skipped += 1
            continue

        # 4. 确认后写入 XML
        updated = dialog.get_data()
        result.update(updated)
        result["process_status"] = "已修改"
        mw.scan_results.append(result)
        mw.update_results_table()
        mw.save_changes(show_result=False)
        processed += 1

    mw.progress_bar.setValue(total)
    mw.progress_bar.setRange(0, 1)
    mw.progress_bar.setValue(1)
    mw.scan_btn.setEnabled(True)
    mw.stop_btn.setEnabled(False)
    mw.log_text.append(f"\n手动匹配完成: 共处理 {processed} 个系列，跳过 {skipped} 个")

    # 统一收尾：有结果 → 结果页；无结果 → 留在扫描页
    _finish_scan(mw, mw.scan_results, 3)


def check_xml_before_scan(mw, manga_root: str) -> tuple:
    """扫描前检查目录中是否已有XML文件，返回 (是否有XML, 统计信息)"""
    try:
        from processors.zip_handler import check_zip_xml_files
        
        stats = {
            "total_files": 0,
            "files_with_xml": 0,
            "files_without_xml": 0,
            "sample_files": []  # 存储一些有XML的文件示例
        }
        
        for root, dirs, files in os.walk(manga_root):
            for file in files:
                if file.lower().endswith(('.zip', '.cbz', '.cbr', '.rar')):
                    stats["total_files"] += 1
                    file_path = os.path.join(root, file)
                    try:
                        # 检查ZIP文件中是否包含ComicInfo.xml
                        has_xml, _, _ = check_zip_xml_files(file_path, "")
                        if has_xml:
                            stats["files_with_xml"] += 1
                            # 保存前5个有XML的文件作为示例
                            if len(stats["sample_files"]) < 5:
                                relative_path = os.path.relpath(file_path, manga_root)
                                stats["sample_files"].append(relative_path)
                        else:
                            stats["files_without_xml"] += 1
                    except Exception:
                        stats["files_without_xml"] += 1
                        continue
        
        has_xml = stats["files_with_xml"] > 0
        return has_xml, stats
    except Exception as e:
        print(f"检查XML文件时出错: {e}")
        return False, {}


def stop_scan(mw):
    """停止扫描"""
    if mw.scan_thread and mw.scan_thread.isRunning():
        mw.scan_thread.stop()
        mw.log_text.append("\n正在停止扫描...")
        mw.stop_btn.setEnabled(False)


def on_progress_updated(mw, progress: int, message: str):
    """进度更新"""
    mw.log_text.append(message)
    # 自动滚动到底部（确保滚动条非 None）
    vbar = mw.log_text.verticalScrollBar()
    if vbar is not None:
        vbar.setValue(vbar.maximum())


def _finish_scan(mw, results: List[Dict], mode: int) -> None:
    """扫描/编辑收尾：路由到结果页或扫描页（未来 008 封面流程的挂载点）

    有结果 → 切到结果页；无结果 → 留在扫描页。
    扩展点：未来 008 合并封面改图后，在此调用 _maybe_start_cover_flow(mw, results, mode)
    判断是否进入封面处理流程（结果页封面缩略图 → 用户选择是否改图）。
    """
    if not results:
        mw.tab_widget.setCurrentIndex(0)  # 无结果 → 扫描页
        return
    mw.tab_widget.setCurrentIndex(1)      # 有结果 → 结果页
    # 未来扩展点：_maybe_start_cover_flow(mw, results, mode)


def _on_full_match_progress(mw, progress: int, message: str) -> None:
    """全匹配模式进度信号：更新进度条值 + 日志滚动（主线程槽）"""
    mw.progress_bar.setValue(progress)
    if message:
        mw.log_text.append(message)
        vbar = mw.log_text.verticalScrollBar()
        if vbar is not None:
            vbar.setValue(vbar.maximum())


def _on_full_match_progress_range(mw, minimum: int, maximum: int) -> None:
    """全匹配模式进度条范围信号：setRange 语义（主线程槽）"""
    mw.progress_bar.setRange(minimum, maximum)


def _on_full_match_log(mw, message: str) -> None:
    """全匹配模式日志信号：追加日志并滚动到底部（主线程槽）"""
    mw.log_text.append(message)
    vbar = mw.log_text.verticalScrollBar()
    if vbar is not None:
        vbar.setValue(vbar.maximum())


def _on_full_match_series_finished(mw, processed: int, skipped: int) -> None:
    """全匹配模式收尾信号：追加统计消息（主线程槽）"""
    mw.log_text.append(f"\n全匹配完成: 共处理 {processed} 个系列，跳过 {skipped} 个")
    vbar = mw.log_text.verticalScrollBar()
    if vbar is not None:
        vbar.setValue(vbar.maximum())


def _on_manhuagui_series_finished(mw, processed: int, skipped: int) -> None:
    """manhuagui 单系列扫描收尾信号：追加统计消息（主线程槽）"""
    mw.log_text.append(f"\nmanhuagui 扫描完成: 共处理 {processed} 个系列，跳过 {skipped} 个")
    vbar = mw.log_text.verticalScrollBar()
    if vbar is not None:
        vbar.setValue(vbar.maximum())


def _on_full_match_series_saved(mw, result: Dict) -> None:
    """全匹配模式逐系列保存信号：结果入库 → 刷新结果表 → 立即静默写盘（主线程槽）

    每个系列确认后即时保存，保证扫描中途崩溃/强制停止时已确认结果不丢失。
    """
    mw.scan_results.append(result)
    mw.update_results_table()
    mw.save_changes(show_result=False)


def _on_full_match_completed(mw, results: List[Dict]) -> None:
    """全匹配模式完成信号：统一收尾（主线程槽）

    结果已由 series_saved 逐系列保存并写盘，此处仅兜底刷新结果表，
    不重复 save_changes。results 参数保留以兼容既有调用方。
    """
    stop_loading_cat(mw)
    mw.update_results_table()
    mw.scan_btn.setEnabled(True)
    mw.stop_btn.setEnabled(False)
    mw.progress_bar.setRange(0, 1)
    mw.progress_bar.setValue(1)
    _finish_scan(mw, mw.scan_results, 0)


def on_scan_completed(mw, results: List[Dict]):
    """扫描完成"""
    from PyQt6.QtWidgets import QDialog

    mw.scan_results = results
    mw.progress_bar.setRange(0, 1)
    mw.progress_bar.setValue(1)

    mw.log_text.append(f"\n扫描完成! 共找到 {len(results)} 个文件夹")
    mw.log_text.append("=" * 80)

    mw.scan_btn.setEnabled(True)
    mw.stop_btn.setEnabled(False)
    mw.update_results_table()

    # ── 有扫描结果 → 打开编辑元数据（多系列导航） ──
    from config import AUTO_TURBO_MATCH, MODE_SKIP_XMLEXIST
    # 修正模式结果（_from_modify）必须进入编辑流程，即使无人值守也不自动保存
    is_modify_results = any(r.get("_from_modify") for r in results)
    if AUTO_TURBO_MATCH == 1 and not is_modify_results:
        # 无人值守模式：不弹编辑窗，直接保存
        mw.log_text.append(f"🚀 无人值守模式：自动保存 {len(results)} 个结果")
        if results:
            for r in results:
                r["process_status"] = "已修改"
            mw.save_changes()
    elif len(results) == 1:
        # 单个结果 → 弹编辑元数据（无导航；修正模式标记结果逐项编辑）
        result = results[0]
        dialog = EditDialog(result, mw, auto_advance=is_modify_results)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_data = dialog.get_data()
            mw.scan_results[0].update(updated_data)
            mw.scan_results[0]["process_status"] = "已修改"
            mw.update_results_table()
            mw.save_changes()
        else:
            mw.scan_results = []
            mw.update_results_table()

    elif len(results) > 1:
        # 多个结果 → 弹编辑元数据（带 ◀▶ 导航；修正模式自动逐个跳转）
        first_result = results[0]
        dialog = EditDialog(first_result, mw, results_list=mw.scan_results,
                            current_index=0, auto_advance=is_modify_results)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 对话框关闭时把其余结果也标记为已修改，确保多系列全部写入
            for r in mw.scan_results:
                r["process_status"] = "已修改"
            mw.update_results_table()
            mw.save_changes()
        else:
            mw.scan_results = []
            mw.update_results_table()

    # 统一收尾：有结果 → 结果页；无结果/取消编辑 → 留在扫描页
    _finish_scan(mw, mw.scan_results, MODE_SKIP_XMLEXIST)


def on_error_occurred(mw, error: str):
    """发生错误"""
    stop_loading_cat(mw)
    mw.log_text.append(f"\n❌ {error}")
    mw.progress_bar.setRange(0, 1)
    mw.progress_bar.setValue(0)

    mw.scan_btn.setEnabled(True)
    mw.stop_btn.setEnabled(False)

    QMessageBox.critical(mw, "错误", error)
