#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComicVine 单系列扫描流程 - 基于 BaseScanThread

用户主动选择 ComicVine 数据源时使用，与 manhuagui 单系列扫描同构：
「搜索 → 结果选择 → 详情抓取 → EditDialog 确认 → 写入 XML」。
ComicVine 源只支持单系列，多系列目录已在 scan_controller 中拦截。

本模块只保留 ComicVine 特有的搜索配置（_search_and_select_comicvine +
结果构建），线程化/信号/弹窗桥接/逐系列保存全部由 BaseScanThread 提供。
"""

from typing import Callable, Dict, Optional, Tuple

from .base_scan_thread import BaseScanThread, _ThreadMwProxy
from .gui_dialogs import show_no_result_dialog, show_result_selection_dialog


def _search_and_select_comicvine(mw, folder_path: str, folder_info: Dict, fetcher,
                                 template_handler,
                                 gui_callback: Optional[Callable] = None) -> Tuple[Optional[Dict], Optional[Dict]]:
    """ComicVine 搜索 → 结果选择 → 详情抓取

    Args:
        mw: 主窗口（或线程日志代理，仅用 log_text）
        folder_path: 系列文件夹路径（提取搜索别名用）
        folder_info: 文件夹解析信息
        fetcher: ComicVineFetcher 实例
        template_handler: XML 模板处理器
        gui_callback: 可选弹窗回调。工作线程传 DialogBridge 包装函数，弹窗经信号
                      路由到主线程；主线程/测试调用不传，直接弹窗。

    Returns:
        (comic_info_base, selected_result)；comic_info_base 为 None 表示跳过此系列
    """
    from processors.search_handler import SearchHandler, search_manga as route_search

    # 1. 提取搜索关键词（主词 + 别名，复用 Bangumi 的方法；仅用 folder_info，fetcher 传 None）
    _, alt_keywords = SearchHandler(None).extract_search_keywords(folder_path, folder_info)

    # 2. ComicVine 主词搜索（结果已转为选择对话框兼容格式）
    search_results = route_search(folder_info["series"], folder_info, source="comicvine")

    # 3. 主词无结果 → 用别名补搜（与 Bangumi 路径一致）
    if not search_results:
        for alt in alt_keywords:
            search_results = route_search(alt, folder_info, source="comicvine")
            if search_results:
                mw.log_text.append(f"💡 用别名「{alt}」搜到 {len(search_results)} 个结果")
                break

    if not search_results:
        mw.log_text.append("❌ ComicVine 未找到搜索结果")
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
            from .manhuagui_scan import _build_from_bangumi_id
            return _build_from_bangumi_id(mw, action.get("value", ""), folder_info, template_handler)
        mw.log_text.append("⏭️ 跳过此系列")
        return None, None

    # 4. 结果选择弹窗（复用 Bangumi 多结果对话框，id 为 ComicVine volume ID）
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

    # 5. 抓取详情页构建 ComicInfo 字典（series/volume 走对应详情端点）
    if selected.get("resource_type") == "series":
        detail = fetcher.get_series_detail(selected["id"])
    else:
        detail = fetcher.get_volume_detail(selected["id"])
    if not detail:
        mw.log_text.append("⚠️ ComicVine 详情抓取失败，使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None
    comic_info_base = template_handler.create_base_template(folder_info)
    comic_info_base.update(detail)
    title = detail.get("Title") or folder_info["series"]
    resource_type = selected.get("resource_type", "volume")
    mw.log_text.append(f"🎯 获取到: {title}（{resource_type}）")
    return comic_info_base, selected


class ComicVineScanThread(BaseScanThread):
    """ComicVine 单系列扫描后台线程

    基于 BaseScanThread，只保留 ComicVine 特有的搜索配置：
    「ComicVine 搜索 → 结果选择 → 详情抓取 → 结果构建」。
    逐个系列「搜索 → EditDialog 确认 → 写入 XML」由框架提供。
    """

    source_name = "comicvine"

    def __init__(self, manga_root: str, manga_value: Optional[str],
                 folders=None, parent=None):
        super().__init__(manga_root, manga_value, folders=folders, parent=parent)
        self._fetcher = None
        self._template_handler = None

    def search_and_select(self, folder_path: str, folder_info: Dict):
        """ComicVine 搜索 → 结果选择 → 详情抓取

        返回 (comic_info_base, selected_result)；comic_info_base 为 None 表示跳过
        """
        from models.comicvine_fetcher import ComicVineFetcher
        from processors.xml_template_handler import create_xml_template_handler

        # 惰性初始化：仅首个文件夹创建一次（fetcher 在 cleanup 中统一关闭）
        if self._fetcher is None:
            self._fetcher = ComicVineFetcher()
            self._template_handler = create_xml_template_handler()

        # 1. 已有 XML 处理（弹窗询问；'cancel' 终止整个扫描）
        handled, xml_out = self.check_existing_xml(folder_path, folder_info)
        if handled:
            return xml_out  # None → 跳过； (RESULT_READY, result) → 修改结果

        # 2. ComicVine 搜索 → 结果选择 → 详情抓取
        return _search_and_select_comicvine(
            _ThreadMwProxy(self), folder_path, folder_info,
            self._fetcher, self._template_handler, gui_callback=self._gui_callback)

    def build_result(self, folder_path: str, folder_info: Dict,
                     comic_info_base: Dict, selected_result: Optional[Dict]) -> Dict:
        """构建 ComicVine 扫描结果字典"""
        from processors.result_builder import create_result_dict
        return create_result_dict(folder_path, folder_info, comic_info_base,
                                  selected_result, skipped=False,
                                  process_status="已修改", source="comicvine")

    def cleanup(self) -> None:
        """关闭 fetcher 浏览器实例"""
        if self._fetcher is not None:
            self._fetcher.close()
