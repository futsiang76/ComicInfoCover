#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manhuagui 单系列扫描流程（主线程交互）

用户主动选择 manhuagui 数据源时使用，与 _run_manual_match_scan 同构：
「搜索 → 结果选择 → 详情抓取 → EditDialog 确认 → 写入 XML」。
manhuagui 源只支持单系列，多系列目录已在 scan_controller 中拦截。
"""

import os
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import QApplication, QDialog

from .edit_dialog import EditDialog
from .gui_dialogs import show_no_result_dialog, show_result_selection_dialog


def _build_from_bangumi_id(mw, value: str, folder_info: Dict, template_handler) -> Tuple[Dict, Optional[Dict]]:
    """manhuagui 无结果时按 Bangumi ID 跨源兜底构建 comic_info_base

    Args:
        mw: 主窗口（写日志用）
        value: Bangumi ID 字符串
        folder_info: 文件夹解析信息
        template_handler: XML 模板处理器

    Returns:
        (comic_info_base, selected_result)；ID 无效/未找到时回退本地信息
    """
    from models.bangumi_fetcher import BangumiFetcher
    from processors.single_series_processor import build_comic_info_from_id

    try:
        numeric_id = int(str(value).strip())
    except (TypeError, ValueError):
        mw.log_text.append("❌ 无效的 Bangumi ID，使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None

    built = build_comic_info_from_id(BangumiFetcher(), numeric_id, folder_info)
    if not built:
        mw.log_text.append("❌ 未找到该 Bangumi ID 的作品，使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None
    return built


def _search_and_select_manhuagui(mw, folder_path: str, folder_info: Dict, fetcher,
                                 template_handler) -> Tuple[Optional[Dict], Optional[Dict]]:
    """manhuagui 搜索 → 结果选择 → 详情抓取

    Args:
        mw: 主窗口
        folder_path: 系列文件夹路径（提取搜索别名用）
        folder_info: 文件夹解析信息
        fetcher: ManhuaguiFetcher 实例
        template_handler: XML 模板处理器

    Returns:
        (comic_info_base, selected_result)；comic_info_base 为 None 表示跳过此系列
    """
    from processors.search_handler import SearchHandler, search_manga as route_search

    # 1. 提取搜索关键词（主词 + 别名，复用 Bangumi 的方法；仅用 folder_info，fetcher 传 None）
    _, alt_keywords = SearchHandler(None).extract_search_keywords(folder_path, folder_info)

    # 2. manhuagui 主词搜索（结果已转为选择对话框兼容格式）
    search_results = route_search(folder_info["series"], folder_info, source="manhuagui")

    # 3. 主词无结果 → 用别名补搜（与 Bangumi 路径一致）
    if not search_results:
        for alt in alt_keywords:
            search_results = route_search(alt, folder_info, source="manhuagui")
            if search_results:
                mw.log_text.append(f"💡 用别名「{alt}」搜到 {len(search_results)} 个结果")
                break

    if not search_results:
        mw.log_text.append("❌ manhuagui 未找到搜索结果")
        action = show_no_result_dialog(mw, folder_info, allow_id_search=False)
        if action.get("action") == "use_local_info":
            mw.log_text.append("📋 使用本地文件夹信息")
            return template_handler.create_local_template(folder_info), None
        if action.get("action") == "id_search":
            return _build_from_bangumi_id(mw, action.get("value", ""), folder_info, template_handler)
        mw.log_text.append("⏭️ 跳过此系列")
        return None, None

    # 2. 结果选择弹窗（复用 Bangumi 多结果对话框，id 为 manhuagui 漫画ID）
    selected = show_result_selection_dialog(mw, search_results, folder_info,
                                            allow_id_search=False)
    if selected is None:
        mw.log_text.append("⏭️ 跳过此系列")
        return None, None
    if selected == "use_local_info":
        mw.log_text.append("📋 使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None

    # 3. 抓取详情页构建 ComicInfo 字典
    detail = fetcher.get_manga_detail(selected["url"])
    if not detail:
        mw.log_text.append("⚠️ manhuagui 详情抓取失败，使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None
    comic_info_base = template_handler.create_base_template(folder_info)
    comic_info_base.update(detail)
    title = detail.get("Title") or folder_info["series"]
    mw.log_text.append(f"🎯 获取到: {title}")
    return comic_info_base, selected


def _run_manhuagui_single_scan(mw, manga_root: str, manga_value: Optional[str],
                               folders: Optional[List[Tuple[str, Dict]]] = None) -> None:
    """manhuagui 单系列扫描主流程：搜索 → 选择 → 详情 → 编辑确认 → 写入

    Args:
        mw: 主窗口
        manga_root: 漫画根目录
        manga_value: Manga 字段值（"Yes"/"No"）
        folders: 系列文件夹列表（scan_controller 已收集时传入，避免二次收集）
    """
    from models.manhuagui_fetcher import ManhuaguiFetcher
    from processors.result_builder import create_result_dict
    from processors.xml_template_handler import create_xml_template_handler

    mw.log_text.clear()
    mw.log_text.append(f"开始扫描: {manga_root}")
    mw.log_text.append("数据源: manhuagui")
    mw.log_text.append(f"Manga设置: {manga_value}")
    mw.scan_results = []
    mw.update_results_table()

    if folders is None:
        from .scan_controller import _collect_series_folders
        folders = _collect_series_folders(manga_root)
    total = max(1, len(folders))
    mw.progress_bar.setRange(0, total)
    mw.progress_bar.setValue(0)
    mw.scan_btn.setEnabled(False)
    mw.stop_btn.setEnabled(True)

    fetcher = ManhuaguiFetcher()
    template_handler = create_xml_template_handler()
    processed = 0
    skipped = 0

    try:
        for idx, (folder_path, folder_info) in enumerate(folders, start=1):
            mw.progress_bar.setValue(idx - 1)
            mw.progress_bar.setRange(0, 0)   # 不定进度 -> Qt 滚动动画
            QApplication.processEvents()
            folder_name = os.path.basename(folder_path)
            mw.log_text.append(f"\n[{idx}/{total}] 📁 {folder_name}")

            comic_info_base, selected_result = _search_and_select_manhuagui(
                mw, folder_path, folder_info, fetcher, template_handler)
            if comic_info_base is None:
                skipped += 1
                continue
            comic_info_base["Manga"] = manga_value or comic_info_base.get("Manga", "Yes")

            # 构建结果并弹编辑确认（与手动匹配模式一致）
            result = create_result_dict(folder_path, folder_info, comic_info_base,
                                        selected_result, skipped=False, process_status="已修改",
                                        source="manhuagui")
            dialog = EditDialog(result, mw)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                mw.log_text.append("⏭️ 取消编辑，跳过此系列")
                skipped += 1
                continue

            # 确认后写入 XML
            updated = dialog.get_data()
            result.update(updated)
            result["process_status"] = "已修改"
            mw.scan_results.append(result)
            mw.update_results_table()
            mw.save_changes(show_result=False)
            processed += 1
            mw.progress_bar.setRange(0, total)  # 恢复定进度
            mw.progress_bar.setValue(idx)        # 显示当前进度
            QApplication.processEvents()
    finally:
        fetcher.close()
        mw.progress_bar.setRange(0, total)  # 异常路径恢复定进度

    mw.progress_bar.setValue(total)
    QApplication.processEvents()
    mw.progress_bar.setRange(0, 1)
    mw.progress_bar.setValue(1)
    mw.scan_btn.setEnabled(True)
    mw.stop_btn.setEnabled(False)
    mw.log_text.append(f"\nmanhuagui 扫描完成: 共处理 {processed} 个系列，跳过 {skipped} 个")

    # 统一收尾：有结果 → 结果页；无结果 → 留在扫描页
    from .scan_controller import _finish_scan
    _finish_scan(mw, mw.scan_results, 0)
