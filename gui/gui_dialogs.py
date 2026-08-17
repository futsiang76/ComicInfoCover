#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI 交互对话框 - 扫描过程中的用户交互对话框

当 Bangumi 搜索返回多个结果或无结果时，使用这些对话框代替 console input()。
DialogBridge 负责跨线程桥接：后台工作线程通过信号触发主线程显示对话框。
"""

import os
import threading
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from .dialogs import show_xml_exists_dialog


def show_bangumi_id_not_found(parent: QWidget, bangumi_id: str,
                              folder_name: str = "") -> None:
    """查询失败报错弹窗：未找到该 Bangumi ID 的作品，自动跳过此系列

    Args:
        parent: 父窗口
        bangumi_id: 用户输入的 Bangumi ID
        folder_name: 当前系列文件夹名（可选）
    """
    title = "未找到作品"
    text = f"未找到 Bangumi ID {bangumi_id} 的作品，跳过此系列"
    if folder_name:
        text = f"📁 {folder_name}\n\n{text}"
    QMessageBox.warning(parent, title, text)


def _make_button(text: str, color: str, hover_color: str, min_width: int = 130) -> QPushButton:
    """创建统一样式的按钮"""
    btn = QPushButton(text)
    btn.setMinimumHeight(42)
    btn.setMinimumWidth(min_width)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: white;
            font-size: 13px;
            font-weight: bold;
            border-radius: 5px;
            padding: 8px 14px;
        }}
        QPushButton:hover {{ background-color: {hover_color}; }}
    """)
    return btn


def _format_result_display(result: Dict) -> str:
    """格式化结果列表显示文本

    ComicVine 结果（含 resource_type）标注 系列/卷 + 年份/期数辅助辨认；
    bangumi/manhuagui 结果带 platform 时标注平台类型：series=True → （漫画系列）/
    （小说系列），series=False → （漫画）/（小说）；platform 缺失保持原格式。
    """
    sid = result.get('id', '?')
    title_cn = result.get('name_cn') or result.get('name', '未知')
    title_ori = result.get('name', '')
    rtype = result.get('resource_type')
    if rtype:
        extra = (f" {result['start_year']}" if result.get('start_year') else "")
        extra += (f" {result['count_of_issues']}期" if result.get('count_of_issues') else "")
        label = '系列' if rtype == 'series' else '卷'
        return f"[{sid}] 📚 {title_cn}（{label}）{extra}".rstrip()
    # bangumi/manhuagui：platform 存在时标注平台类型（系列条目加「系列」二字）
    platform = result.get('platform')
    if platform:
        platform_label = f"{platform}系列" if result.get('series') is True else platform
        if title_ori and title_ori != title_cn:
            return f"[{sid}] {title_cn}  ({title_ori})（{platform_label}）"
        return f"[{sid}] {title_cn}（{platform_label}）"
    if title_ori and title_ori != title_cn:
        return f"[{sid}] {title_cn}  ({title_ori})"
    return f"[{sid}] {title_cn}"


def show_result_selection_dialog(parent: QWidget, search_results: List[Dict],
                                    folder_info: Dict,
                                    alt_keywords: Optional[List[str]] = None,
                                    allow_id_search: bool = True,
                                    id_search_kind: str = "bangumi"
                                    ):
    """统一的结果选择对话框

    根据 search_results 数量自动切换模式：
    - 空列表 → 无结果模式（标题"未找到结果"，选择按钮隐藏，无列表）
    - 1 项   → 单结果模式（标题"找到 1 个匹配结果"，含列表）
    - N 项   → 多结果模式（标题"N 个匹配结果"，含列表）

    Args:
        parent: 父窗口
        search_results: Bangumi 搜索结果列表，每项含 id/name/name_cn/rating
        folder_info: 文件夹信息 (series, author, volume 等)
        alt_keywords: 备用关键词列表（无结果时显示）
        allow_id_search: 是否显示「按ID查找」按钮（ComicVine 模式传 False 隐藏）
        id_search_kind: ID 查找类型 'bangumi' | 'manhuagui'，决定按钮文字与输入逻辑

    Returns:
        Dict: 用户选择了某个结果 (含 id/name/name_cn/rating 等)
        str 'use_local_info': 用户选择仅使用本地信息
        None: 用户跳过此系列
    """
    has_results = bool(search_results)
    series = folder_info.get('series', '未知')

    dialog = QDialog(parent)
    if has_results:
        dialog.setWindowTitle(f"选择匹配作品 — {series}")
        dialog.setMinimumSize(680, 480)
    else:
        dialog.setWindowTitle(f"未找到结果 — {series}")
        dialog.setMinimumSize(680, 360)

    layout = QVBoxLayout()
    layout.setSpacing(10)

    # 标题
    if has_results:
        title_text = f"📋 找到 <b>{len(search_results)}</b> 个匹配结果，请选择："
        title = QLabel(title_text)
        title.setStyleSheet("font-size: 14px; padding: 8px;")
    else:
        title = QLabel("未找到结果")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #d32f2f; padding: 8px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setWordWrap(True)
    layout.addWidget(title)

    # 文件夹信息
    info_text = f"📁 文件夹: 系列=<b>{folder_info.get('series', '?')}</b>  |  作者=<b>{folder_info.get('author', '?')}</b>"
    if folder_info.get('volume'):
        info_text += f"  |  卷=<b>{folder_info['volume']}</b>"
    info_label = QLabel(info_text)
    info_label.setStyleSheet("font-size: 12px; color: #555; padding: 4px 8px; background: #f0f4f8; border-radius: 4px;")
    info_label.setWordWrap(True)
    layout.addWidget(info_label)

    # 备用关键词（仅无结果时显示）
    if not has_results and alt_keywords:
        kw_text = "📋 可用别名: " + ", ".join(alt_keywords)
        kw_label = QLabel(kw_text)
        kw_label.setStyleSheet("font-size: 11px; color: #666; padding: 4px 8px;")
        kw_label.setWordWrap(True)
        layout.addWidget(kw_label)

    # 结果列表（仅在有结果时显示）
    list_widget = None
    if has_results:
        list_widget = QListWidget()
        list_widget.setStyleSheet("""
            QListWidget { font-size: 13px; border: 1px solid #ccc; border-radius: 4px; }
            QListWidget::item { padding: 8px 6px; border-bottom: 1px solid #eee; }
            QListWidget::item:selected { background-color: #cce5ff; color: #004085; }
            QListWidget::item:hover { background-color: #e8f0fe; }
        """)

        for i, result in enumerate(search_results):
            display = _format_result_display(result)

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, i)
            list_widget.addItem(item)

        if list_widget.count() > 0:
            list_widget.setCurrentRow(0)

        layout.addWidget(list_widget)

        hint = QLabel("💡 点击列表项选中，然后点击「选择此项」")
        hint.setStyleSheet("font-size: 11px; color: #888; padding: 2px 8px;")
        layout.addWidget(hint)
    else:
        layout.addStretch()

    # 按钮区
    btn_layout = QHBoxLayout()
    btn_layout.addStretch()

    select_btn = _make_button("✅ 选择此项", "#2196F3", "#0b7dda")
    id_label = ("🔍 按manhuagui ID查找" if id_search_kind == "manhuagui"
                else "🔍 按Bangumi ID查找")
    id_btn = _make_button(id_label, "#9C27B0", "#7B1FA2")
    if not allow_id_search:
        id_btn.setVisible(False)
    local_btn = _make_button("📋 仅用本地信息", "#FF9800", "#e68900")
    skip_btn = _make_button("⏭️ 跳过此系列", "#9E9E9E", "#757575")

    if not has_results:
        select_btn.setVisible(False)

    btn_layout.addWidget(select_btn)
    btn_layout.addWidget(id_btn)
    btn_layout.addWidget(local_btn)
    btn_layout.addWidget(skip_btn)
    btn_layout.addStretch()
    layout.addLayout(btn_layout)

    # 存储结果
    dialog._result = None

    def on_select():
        if list_widget is not None:
            current = list_widget.currentItem()
            if current:
                idx = current.data(Qt.ItemDataRole.UserRole)
                dialog._result = search_results[idx]
        dialog.accept()

    def on_local():
        dialog._result = 'use_local_info'
        dialog.accept()

    def on_skip():
        dialog._result = None
        dialog.accept()

    def on_id_search():
        from PySide6.QtWidgets import QInputDialog
        if id_search_kind == "manhuagui":
            sid, ok = QInputDialog.getText(
                dialog, "manhuagui ID",
                f"请输入 manhuagui 漫画 ID（如 20635）：\n（当前系列: {folder_info.get('series', '')}）")
            if ok and sid.strip():
                # manhuagui 只输入漫画 ID，详情由工作线程 fetcher 抓取
                dialog._result = {"id": sid.strip()}
                dialog.accept()
            return
        sid, ok = QInputDialog.getText(dialog, "Bangumi ID",
                                       f"请输入 Bangumi ID（如 378725）：\n（当前系列: {folder_info.get('series', '')}）")
        if ok and sid.strip():
            from models.bangumi_fetcher import BangumiFetcher
            fetcher = BangumiFetcher()
            detail = fetcher.get_manga_detail(sid.strip())
            if detail:
                dialog._result = {
                    "id": sid.strip(),
                    "name": detail.get("name", ""),
                    "name_cn": detail.get("name_cn", detail.get("name", "")),
                    "rating": detail.get("rating", {}),
                }
                dialog.accept()
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(dialog, "错误", f"未找到 Bangumi ID {sid.strip()} 的作品")

    select_btn.clicked.connect(on_select)
    id_btn.clicked.connect(on_id_search)
    local_btn.clicked.connect(on_local)
    skip_btn.clicked.connect(on_skip)
    if list_widget is not None:
        list_widget.itemDoubleClicked.connect(on_select)

    dialog.setLayout(layout)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dialog.raise_()
    dialog.activateWindow()
    dialog.exec()

    return dialog._result


def show_multi_result_dialog(parent: QWidget, search_results: List[Dict],
                              folder_info: Dict,
                              alt_keywords: Optional[List[str]] = None,
                              allow_id_search: bool = True,
                              id_search_kind: str = "bangumi"
                              ) -> Optional[Dict]:
    """显示多结果选择对话框（兼容包装，委托给统一函数）

    allow_id_search 透传给统一对话框（ComicVine 传 False 隐藏「按ID查找」）。
    id_search_kind 指定 ID 查找类型（bangumi/manhuagui），决定按钮文字与输入逻辑。
    """
    return show_result_selection_dialog(parent, search_results, folder_info,
                                        alt_keywords, allow_id_search,
                                        id_search_kind)


def show_no_result_dialog(parent: QWidget, folder_info: Dict,
                           alt_keywords: Optional[List[str]] = None,
                           allow_id_search: bool = True,
                           id_search_kind: str = "bangumi"
                           ) -> dict:
    """显示无搜索结果时的选项对话框（兼容包装，委托给统一函数）

    id_search_kind 指定 ID 查找类型（bangumi/manhuagui）：dict 结果转换时
    manhuagui → mhg_id_search（详情由工作线程抓取），bangumi → id_search。
    """
    result = show_result_selection_dialog(parent, [], folder_info, alt_keywords,
                                          allow_id_search, id_search_kind)
    if isinstance(result, dict):
        action = 'mhg_id_search' if id_search_kind == "manhuagui" else 'id_search'
        return {'action': action, 'value': str(result.get('id', ''))}
    elif result == 'use_local_info':
        return {'action': 'use_local_info', 'value': None}
    else:
        return {'action': 'skip', 'value': None}


class DialogBridge(QObject):
    """跨线程对话框桥接器

    后台扫描线程通过此桥接器在主线程上显示 GUI 对话框。
    使用 Qt 信号/槽机制确保对话框在主线程创建和显示。
    使用 threading.Event 阻塞工作线程等待用户响应。

    支持的 action:
        - 'select_result': 多结果选择对话框
        - 'search_failure': 无结果时的选项对话框
        - 'xml_exists': 检测到已有XML文件的处理选择对话框
        - 'edit_xml': 编辑zip文件中的ComicInfo.xml
        - 'single_series_input': 手动匹配模式输入当前系列文件夹的 Bangumi ID
        - 'get_text': 文本输入对话框（ID、关键词等）
        - 'edit_result': 单系列编辑确认对话框（EditDialog，全匹配模式用）
        - 'bangumi_id_not_found': 查询失败报错弹窗（未找到该 ID 的作品）
        - 'warning': 通用警告弹窗（手动匹配无效 ID 输入等）
    """
    _request = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._response: Optional[dict] = None
        self._waiting = False
        self._event = threading.Event()
        self._request.connect(self._handle_request)

    def invoke(self, action: str, **params):
        """从工作线程调用，阻塞直到用户完成对话框操作

        Args:
            action: 对话框类型 ('select_result'|'search_failure'|'get_text')
            **params: 对话框参数

        Returns:
            对话框返回值
        """
        request = {'action': action, 'params': params}
        self._response = None
        self._waiting = True
        self._event.clear()
        self._request.emit(request)
        while self._waiting:
            if self._event.wait(timeout=0.5):
                break
        return self._response

    def cancel(self):
        """取消当前等待的对话框（从主线程调用）"""
        self._waiting = False
        self._event.set()

    @Slot(dict)
    def _handle_request(self, request: dict):
        """在主线程上执行，显示对应的对话框

        Args:
            request: {'action': str, 'params': dict}
        """
        action = request.get('action')
        params = request.get('params', {})
        parent = self.parent()

        try:
            if action == 'select_result':
                self._response = show_multi_result_dialog(parent, **params)
            elif action == 'search_failure':
                self._response = show_no_result_dialog(parent, **params)
            elif action == 'xml_exists':
                self._response = show_xml_exists_dialog(parent, **params)
            elif action == 'edit_xml':
                from .xml_editor import edit_zip_xml
                edit_zip_xml(parent, **params)
                self._response = True
            elif action == 'single_series_input':
                self._response = self._show_single_series_input(parent, **params)
            elif action == 'get_text':
                self._response = self._show_text_dialog(parent, **params)
            elif action == 'edit_result':
                self._response = self._show_edit_dialog(parent, **params)
            elif action == 'bangumi_id_not_found':
                show_bangumi_id_not_found(parent, **params)
                self._response = None
            elif action == 'warning':
                QMessageBox.warning(parent, params.get('title', '警告'),
                                    params.get('message', ''))
                self._response = None
            else:
                self._response = None
        finally:
            self._waiting = False
            self._event.set()

    @staticmethod
    def _show_text_dialog(parent: QWidget, title: str = "输入",
                          prompt: str = "请输入：",
                          default: str = "") -> Optional[str]:
        """显示文本输入对话框"""
        text, ok = QInputDialog.getText(parent, title, prompt, text=default)
        if ok and text.strip():
            return text.strip()
        return None

    @staticmethod
    def _show_single_series_input(parent: QWidget, folder_path: str = "",
                                  folder_info: Optional[Dict] = None) -> Optional[str]:
        """手动匹配模式：弹窗输入当前系列文件夹的 Bangumi ID

        输入 "0" 表示使用本地文件夹信息（不查 Bangumi）。

        Args:
            parent: 父窗口
            folder_path: 当前系列文件夹路径
            folder_info: 文件夹解析信息

        Returns:
            Optional[str]: 用户输入的 Bangumi ID（"0" 表示本地）；取消/留空返回 None
        """
        folder_name = os.path.basename(folder_path) if folder_path else ""
        series = (folder_info or {}).get("series", "")
        if not folder_name and series:
            folder_name = series
        prompt = (f"📁 {folder_name}\n\n"
                  f"请输入该系列的 Bangumi ID（如 378725）：\n"
                  f"提示：输入 0 表示使用本地文件夹信息（不查询 Bangumi）")
        text, ok = QInputDialog.getText(parent, "手动匹配模式", prompt)
        if ok and text.strip():
            return text.strip()
        return None

    @staticmethod
    def _show_edit_dialog(parent: QWidget, result: Optional[Dict] = None) -> Optional[Dict]:
        """单系列编辑确认对话框（EditDialog 包装，主线程执行）

        全匹配模式逐系列「扫描 → 编辑确认 → 保存」流程使用。
        result 为工作线程构建的普通 dict（经信号传值，跨线程安全）。

        Args:
            parent: 父窗口
            result: 扫描构建的待编辑结果字典

        Returns:
            Dict: {'accepted': bool, 'data': Dict}；确认返回编辑后数据，
                  取消/关闭返回 {'accepted': False}
        """
        from .edit_dialog import EditDialog

        dialog = EditDialog(result, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return {'accepted': True, 'data': dialog.get_data()}
        return {'accepted': False, 'data': None}
