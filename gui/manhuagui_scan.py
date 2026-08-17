#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manhuagui 单系列扫描流程 - 基于 BaseScanThread

用户主动选择 manhuagui 数据源时使用，与全匹配模式同构：
「搜索 → 结果选择 → 详情抓取 → EditDialog 确认 → 写入 XML」。
manhuagui 源只支持单系列，多系列目录已在 scan_controller 中拦截。

本模块只保留 manhuagui 特有的搜索配置（_search_and_select_manhuagui +
结果构建），线程化/信号/弹窗桥接/逐系列保存全部由 BaseScanThread 提供。
"""

from typing import Callable, Dict, List, Optional, Tuple

from .base_scan_thread import BaseScanThread, _ThreadMwProxy
from .gui_dialogs import show_no_result_dialog, show_result_selection_dialog


def _split_result_authors(result: Dict) -> List[str]:
    """从 manhuagui 搜索结果提取作者列表（author 字段，兼容 ×/&/ 等分隔符）"""
    from models.author_utils import _split_authors
    return _split_authors(result.get("author", ""))


def _filter_results_by_author(search_results: List[Dict], folder_info: Dict) -> List[Dict]:
    """逐个比对搜索结果作者与文件夹作者，返回作者匹配项（复用三源公共过滤层）"""
    from models.author_utils import filter_results_by_author
    return filter_results_by_author(
        search_results, folder_info.get("author", ""), _split_result_authors)


def _is_author_keyword(keyword: str, folder_author: str) -> bool:
    """判断关键词是否为作者名（作者是身份不是搜索词，不作为搜索关键词）"""
    author = (folder_author or "").strip().lower()
    return bool(author) and keyword.strip().lower() == author


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


def _build_from_manhuagui_id(mw, value: str, folder_info: Dict, fetcher,
                             template_handler) -> Tuple[Dict, Optional[Dict]]:
    """manhuagui 无结果时按漫画 ID 直接抓详情构建 comic_info_base

    Args:
        mw: 主窗口或线程日志代理（写日志用）
        value: manhuagui 漫画数字 ID 字符串
        folder_info: 文件夹解析信息
        fetcher: ManhuaguiFetcher 实例（工作线程持有，直接抓详情）
        template_handler: XML 模板处理器

    Returns:
        (comic_info_base, selected_result)；ID 无效/未找到时回退本地信息
    """
    try:
        comic_id = int(str(value).strip())
    except (TypeError, ValueError):
        mw.log_text.append("❌ 无效的 manhuagui ID，使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None

    url = f"https://www.manhuagui.com/comic/{comic_id}/"
    detail = fetcher.get_manga_detail(url)
    if not detail:
        mw.log_text.append("❌ 未找到该 manhuagui ID 的作品，使用本地文件夹信息")
        return template_handler.create_local_template(folder_info), None

    comic_info_base = template_handler.create_base_template(folder_info)
    comic_info_base.update(detail)
    title = detail.get("Title") or folder_info["series"]
    mw.log_text.append(f"🎯 获取到: {title}")
    return comic_info_base, {"url": url, "title": detail.get("Title", "")}


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
    folder_author = folder_info.get("author", "")

    # 2. manhuagui 主词搜索（结果已转为选择对话框兼容格式），逐个比对作者
    search_results = route_search(folder_info["series"], folder_info, source="manhuagui")
    matching_results = _filter_results_by_author(search_results, folder_info)

    # 3. 主词无作者匹配 → 用别名补搜（排除作者名：作者是身份不是搜索词）
    if not matching_results:
        for alt in alt_keywords:
            if _is_author_keyword(alt, folder_author):
                continue
            alt_results = route_search(alt, folder_info, source="manhuagui")
            alt_matching = _filter_results_by_author(alt_results, folder_info)
            if alt_matching:
                mw.log_text.append(f"💡 用别名「{alt}」搜到 {len(alt_matching)} 个结果")
                matching_results = alt_matching
                break

    if not matching_results:
        mw.log_text.append("❌ manhuagui 未找到搜索结果")
        if gui_callback is not None:
            action = gui_callback('search_failure', folder_info=folder_info,
                                  allow_id_search=True, id_search_kind="manhuagui")
        else:
            action = show_no_result_dialog(mw, folder_info,
                                           allow_id_search=True,
                                           id_search_kind="manhuagui")
        if action is None:  # 线程停止/对话框被取消 → 跳过
            mw.log_text.append("⏭️ 跳过此系列")
            return None, None
        if action.get("action") == "use_local_info":
            mw.log_text.append("📋 使用本地文件夹信息")
            return template_handler.create_local_template(folder_info), None
        if action.get("action") == "id_search":
            return _build_from_bangumi_id(mw, action.get("value", ""), folder_info, template_handler)
        if action.get("action") == "mhg_id_search":
            return _build_from_manhuagui_id(mw, action.get("value", ""),
                                            folder_info, fetcher, template_handler)
        mw.log_text.append("⏭️ 跳过此系列")
        return None, None

    # 4. 结果选择弹窗（复用 Bangumi 多结果对话框，id 为 manhuagui 漫画ID）
    if gui_callback is not None:
        selected = gui_callback('select_result', search_results=matching_results,
                                folder_info=folder_info, allow_id_search=False)
    else:
        selected = show_result_selection_dialog(mw, matching_results, folder_info,
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


class ManhuaguiScanThread(BaseScanThread):
    """manhuagui 单系列扫描后台线程

    基于 BaseScanThread，只保留 manhuagui 特有的搜索配置：
    「manhuagui 搜索 → 结果选择 → 详情抓取 → 结果构建」。
    逐个系列「搜索 → EditDialog 确认 → 写入 XML」由框架提供。
    """

    source_name = "manhuagui"

    def __init__(self, manga_root: str, manga_value: Optional[str],
                 folders=None, parent=None):
        super().__init__(manga_root, manga_value, folders=folders, parent=parent)
        self._fetcher = None
        self._template_handler = None

    def search_and_select(self, folder_path: str, folder_info: Dict):
        """manhuagui 搜索 → 结果选择 → 详情抓取

        返回 (comic_info_base, selected_result)；comic_info_base 为 None 表示跳过
        """
        from models.manhuagui_fetcher import ManhuaguiFetcher
        from processors.xml_template_handler import create_xml_template_handler

        # 惰性初始化：仅首个文件夹创建一次（fetcher 在 cleanup 中统一关闭）
        if self._fetcher is None:
            self._fetcher = ManhuaguiFetcher()
            self._template_handler = create_xml_template_handler()

        # 1. 已有 XML 处理（弹窗询问；'cancel' 终止整个扫描）
        handled, xml_out = self.check_existing_xml(folder_path, folder_info)
        if handled:
            return xml_out  # None → 跳过； (RESULT_READY, result) → 修改结果

        # 2. manhuagui 搜索 → 结果选择 → 详情抓取
        return _search_and_select_manhuagui(
            _ThreadMwProxy(self), folder_path, folder_info,
            self._fetcher, self._template_handler, gui_callback=self._gui_callback)

    def build_result(self, folder_path: str, folder_info: Dict,
                     comic_info_base: Dict, selected_result: Optional[Dict]) -> Dict:
        """构建 manhuagui 扫描结果字典"""
        from processors.result_builder import create_result_dict
        return create_result_dict(folder_path, folder_info, comic_info_base,
                                  selected_result, skipped=False,
                                  process_status="已修改", source="manhuagui")

    def cleanup(self) -> None:
        """关闭 fetcher 浏览器实例"""
        if self._fetcher is not None:
            self._fetcher.close()
