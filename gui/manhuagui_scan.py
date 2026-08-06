#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manhuagui 单系列扫描流程（后台线程版）

用户主动选择 manhuagui 数据源时使用，与 FullMatchThread 同构：
「搜索 → 结果选择 → 详情抓取 → EditDialog 确认 → 写入 XML」。
manhuagui 源只支持单系列，多系列目录已在 scan_controller 中拦截。

线程化要点：
- 弹窗全部经 DialogBridge 桥接到主线程（search_failure/select_result/edit_result），
  工作线程不直接创建任何 widget。
- 进度/日志/结果经信号回主线程更新进度条、日志和结果表。
- 逐系列确认后立即发 series_saved 写盘（与全匹配模式一致）。
"""

import os
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from .gui_dialogs import DialogBridge, show_no_result_dialog, show_result_selection_dialog


class _ThreadLog:
    """工作线程日志接收器：log_text.append 转发到 log_message 信号

    让 _search_and_select_manhuagui 复用主线程代码时只需写 mw.log_text.append，
    实际输出走信号回主线程，不触碰任何 widget。
    """

    def __init__(self, thread: QThread):
        self._thread = thread

    def append(self, message: str) -> None:
        self._thread.log_message.emit(message)


class _ThreadMwProxy:
    """工作线程内的主窗口最小代理：只提供日志，不做任何 widget 操作"""

    def __init__(self, thread: QThread):
        self.log_text = _ThreadLog(thread)


def _build_from_bangumi_id(mw, value: str, folder_info: Dict, template_handler) -> Tuple[Dict, Optional[Dict]]:
    """manhuagui 无结果时按 Bangumi ID 跨源兜底构建 comic_info_base

    Args:
        mw: 主窗口或线程日志代理（写日志用）
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
                                 template_handler,
                                 gui_callback: Optional[Callable] = None) -> Tuple[Optional[Dict], Optional[Dict]]:
    """manhuagui 搜索 → 结果选择 → 详情抓取

    Args:
        mw: 主窗口（或线程日志代理，仅用 log_text）
        folder_path: 系列文件夹路径（提取搜索别名用）
        folder_info: 文件夹解析信息
        fetcher: ManhuaguiFetcher 实例
        template_handler: XML 模板处理器
        gui_callback: 可选弹窗回调。工作线程传 DialogBridge 包装函数，弹窗经信号
                      路由到主线程；主线程/测试调用不传，直接弹窗。

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
        if gui_callback is not None:
            action = gui_callback('search_failure', folder_info=folder_info, allow_id_search=False)
        else:
            action = show_no_result_dialog(mw, folder_info, allow_id_search=False)
        if action is None:  # 线程停止/对话框被取消 → 跳过
            mw.log_text.append("⏭️ 跳过此系列")
            return None, None
        if action.get("action") == "use_local_info":
            mw.log_text.append("📋 使用本地文件夹信息")
            return template_handler.create_local_template(folder_info), None
        if action.get("action") == "id_search":
            return _build_from_bangumi_id(mw, action.get("value", ""), folder_info, template_handler)
        mw.log_text.append("⏭️ 跳过此系列")
        return None, None

    # 4. 结果选择弹窗（复用 Bangumi 多结果对话框，id 为 manhuagui 漫画ID）
    if gui_callback is not None:
        selected = gui_callback('select_result', search_results=search_results,
                                folder_info=folder_info, allow_id_search=False)
    else:
        selected = show_result_selection_dialog(mw, search_results, folder_info,
                                                allow_id_search=False)
    if selected is None:
        mw.log_text.append("⏭️ 跳过此系列")
        return None, None
    if selected == "use_local_info":
        mw.log_text.append("📋 使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None

    # 5. 抓取详情页构建 ComicInfo 字典
    detail = fetcher.get_manga_detail(selected["url"])
    if not detail:
        mw.log_text.append("⚠️ manhuagui 详情抓取失败，使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None
    comic_info_base = template_handler.create_base_template(folder_info)
    comic_info_base.update(detail)
    title = detail.get("Title") or folder_info["series"]
    mw.log_text.append(f"🎯 获取到: {title}")
    return comic_info_base, selected


class ManhuaguiScanThread(QThread):
    """manhuagui 单系列扫描后台线程

    逐个系列「manhuagui 搜索 → 结果选择 → 详情 → EditDialog 确认 → 写入 XML」，
    仿照 FullMatchThread：弹窗经 DialogBridge 桥接主线程，进度/日志/结果走信号，
    主线程事件循环保持运行（进度条/小猫动画持续刷新、取消按钮可用）。
    逐系列确认后立即发 series_saved 写盘，防中途崩溃丢已确认结果。
    """

    progress_updated = pyqtSignal(int, str)   # (进度值, 状态消息)
    progress_range = pyqtSignal(int, int)     # (min, max)，对应 setRange 语义
    log_message = pyqtSignal(str)
    scan_completed = pyqtSignal(list)          # 收集到的结果列表
    series_saved = pyqtSignal(dict)            # 单系列确认结果（逐系列即时保存）
    error_occurred = pyqtSignal(str)
    series_finished = pyqtSignal(int, int)     # (processed, skipped) 收尾用

    def __init__(self, manga_root: str, manga_value: Optional[str],
                 folders: Optional[List[Tuple[str, Dict]]], parent=None):
        super().__init__()
        self.manga_root = manga_root
        self.manga_value = manga_value
        self.folders = folders or []
        self._is_running = True
        # 对话框桥接器（在 __init__ 中创建，确保主线程亲和性）
        self._bridge = DialogBridge(parent)

    def run(self) -> None:
        """后台逐系列「manhuagui 搜索 → 确认 → 保存」主循环"""
        try:
            from models.manhuagui_fetcher import ManhuaguiFetcher
            from processors.result_builder import create_result_dict
            from processors.xml_template_handler import create_xml_template_handler
            from .scan_controller import _collect_series_folders

            folders = self.folders
            if not folders:
                folders = _collect_series_folders(self.manga_root)
            total = max(1, len(folders))
            self.progress_range.emit(0, total)
            self.progress_updated.emit(0, f"manhuagui 扫描: 共 {total} 个系列")

            proxy = _ThreadMwProxy(self)
            fetcher = ManhuaguiFetcher()
            template_handler = create_xml_template_handler()
            processed = 0
            skipped = 0
            results: List[Dict] = []

            try:
                for idx, (folder_path, folder_info) in enumerate(folders, start=1):
                    if not self._is_running:
                        break
                    folder_name = os.path.basename(folder_path)
                    self.progress_updated.emit(idx - 1, f"\n[{idx}/{total}] 📁 {folder_name}")
                    self.progress_range.emit(0, 0)  # 不定进度 -> Qt 滚动动画

                    comic_info_base, selected_result = _search_and_select_manhuagui(
                        proxy, folder_path, folder_info, fetcher, template_handler,
                        gui_callback=self._gui_callback)
                    if not self._is_running:
                        break
                    if comic_info_base is None:
                        skipped += 1
                        continue
                    comic_info_base["Manga"] = self.manga_value or comic_info_base.get("Manga", "Yes")

                    # 构建结果并弹编辑确认（经 DialogBridge 主线程弹窗）
                    result = create_result_dict(folder_path, folder_info, comic_info_base,
                                                selected_result, skipped=False,
                                                process_status="已修改", source="manhuagui")
                    resp = self._gui_callback('edit_result', result=result)
                    if not self._is_running:
                        break
                    if not (resp and resp.get('accepted')):
                        self.log_message.emit("⏭️ 取消编辑，跳过此系列")
                        skipped += 1
                        continue

                    # 确认后写入 XML：逐系列发回主线程立即保存
                    result.update(resp.get('data') or {})
                    result["process_status"] = "已修改"
                    results.append(result)
                    self.series_saved.emit(result)
                    processed += 1
                    self.progress_range.emit(0, total)  # 恢复定进度
                    self.progress_updated.emit(idx, f"✅ {folder_name} 处理完成")
            finally:
                fetcher.close()

            self.progress_updated.emit(total, "")
            self.progress_range.emit(0, 1)
            self.progress_updated.emit(1, "")
            self.scan_completed.emit(results)
            self.series_finished.emit(processed, skipped)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"扫描失败: {str(e)}")

    def _gui_callback(self, action: str, **params):
        """工作线程弹窗回调：桥接到主线程；停止后不再弹窗"""
        if not self._is_running:
            if action == 'search_failure':
                return {'action': 'skip', 'value': None}
            if action == 'edit_result':
                return {'accepted': False, 'data': None}
            return None
        return self._bridge.invoke(action, **params)

    def stop(self) -> None:
        """停止扫描：置运行标志 + 取消当前等待中的对话框"""
        self._is_running = False
        self._bridge.cancel()
