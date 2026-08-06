#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全匹配模式（mode 0）逐个交互扫描流程 - 后台线程版

非无人值守时在后台线程对每个系列文件夹执行：
「扫描匹配 → EditDialog 确认 → 静默保存 → 下一个」，
不批量收集后统一编辑，也不弹「保存完成」结果框。
无人值守（AUTO_TURBO_MATCH=1）仍走 ScanThread 后台批量流程。

线程化要点：
- 弹窗全部经 DialogBridge 桥接到主线程（select_result/search_failure/
  xml_exists/edit_result），工作线程不直接创建任何 widget。
- 进度/日志/结果经信号回主线程更新进度条、日志和结果表。
"""

import os
from typing import Callable, Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from .gui_dialogs import DialogBridge


class _FullMatchContext:
    """供 XmlModeHandler 使用的最小处理器上下文

    复用 xml_mode_handler 的「已有 XML 分流」逻辑（模式 0：有 XML 时弹窗询问
    处理方式），避免在 scan_controller 中重复实现。
    """

    mode_skip_xml = 0
    auto_turbo = False

    def __init__(self, gui_callback: Callable, manga_value: Optional[str]):
        self.gui_callback = gui_callback
        self.manga_value = manga_value
        self.skipped = 0
        self.auto_processed = 0
        self._cancelled = False

    def _create_result_dict(self, folder_path: str, folder_info: Dict,
                            comic_info_base, selected_result, skipped: bool,
                            process_status: str) -> Dict:
        from processors.result_builder import create_result_dict
        return create_result_dict(folder_path, folder_info, comic_info_base,
                                  selected_result, skipped, process_status)

    def _create_result_dict_from_xml(self, folder_path: str, folder_info: Dict,
                                     xml_result: Dict) -> Dict:
        from processors.result_builder import create_result_dict_from_xml
        return create_result_dict_from_xml(folder_path, folder_info, xml_result)


class FullMatchThread(QThread):
    """全匹配模式（非无人值守）后台扫描线程

    逐个系列「扫描匹配 → EditDialog 确认 → 保存 → 下一个」，
    仿照 ScanThread 模式：弹窗走 DialogBridge，进度/日志/结果走信号，
    主线程事件循环保持运行（进度条/动画持续刷新、取消按钮可用）。
    """

    progress_updated = pyqtSignal(int, str)   # (进度值, 状态消息)
    progress_range = pyqtSignal(int, int)     # (min, max)，对应 setRange 语义
    log_message = pyqtSignal(str)
    scan_completed = pyqtSignal(list)          # 收集到的结果列表
    series_saved = pyqtSignal(dict)            # 单系列确认结果（逐系列即时保存）
    error_occurred = pyqtSignal(str)
    series_finished = pyqtSignal(int, int)     # (processed, skipped) 收尾用

    def __init__(self, manga_root: str, manga_value: Optional[str], parent=None):
        super().__init__()
        self.manga_root = manga_root
        self.manga_value = manga_value
        self._is_running = True
        # 对话框桥接器（在 __init__ 中创建，确保主线程亲和性）
        self._bridge = DialogBridge(parent)

    def run(self) -> None:
        """后台逐个系列「扫描匹配 → 确认 → 保存」主循环"""
        try:
            import config

            from .scan_controller import _collect_series_folders

            # 逐个交互不触发无人值守逻辑（process_normal_folder 运行时读取该配置）
            config.AUTO_TURBO_MATCH = 0
            config.MODE_SKIP_XMLEXIST = 0

            from models.bangumi_fetcher import BangumiFetcher
            from processors.result_builder import create_result_dict
            from processors.scan_processors import process_normal_folder
            from processors.xml_mode_handler import create_xml_mode_handler

            bridge = self._bridge

            def gui_callback(action: str, **params):
                """工作线程弹窗回调：桥接到主线程；停止后不再弹窗"""
                if not self._is_running:
                    if action == 'search_failure':
                        return {'action': 'skip', 'value': None}
                    return None
                return bridge.invoke(action, **params)

            folders = _collect_series_folders(self.manga_root)
            total = len(folders)
            self.progress_range.emit(0, max(1, total))
            self.progress_updated.emit(0, f"全匹配扫描: 共 {total} 个系列")

            xml_handler = create_xml_mode_handler(_FullMatchContext(gui_callback, self.manga_value))
            xml_ctx = xml_handler.processor
            fetcher = BangumiFetcher()

            processed = 0
            skipped = 0
            results: List[Dict] = []

            for idx, (folder_path, folder_info) in enumerate(folders, start=1):
                if not self._is_running:
                    break
                folder_name = os.path.basename(folder_path)
                self.progress_updated.emit(idx - 1, f"\n[{idx}/{total}] 📁 {folder_name}")
                self.progress_range.emit(0, 0)   # 不定进度 -> Qt 滚动动画

                # 1. 已有 XML 处理（弹窗询问；'cancel' 终止整个扫描）
                xml_status, xml_stats = xml_handler.check_folder_xml(folder_path, folder_info)
                result = xml_handler.handle_existing_xml(folder_path, folder_info, 0, xml_status, xml_stats)
                if not self._is_running:
                    break
                if xml_ctx._cancelled:
                    self.log_message.emit("🛑 用户取消扫描")
                    break
                if result is not None:
                    if result.get("skipped"):
                        self.log_message.emit("⏭️ 跳过此系列（已有XML）")
                        skipped += 1
                        continue
                    # 'modify'：从 XML 读取的只读结果，仍弹编辑确认
                    result["process_status"] = "已修改"
                else:
                    # 2. Bangumi 搜索匹配（含多结果选择/无结果处理弹窗）
                    scan_result = process_normal_folder(folder_path, folder_info, fetcher, 0,
                                                        gui_callback=gui_callback)
                    if not self._is_running:
                        break
                    if scan_result.get("skip_files"):
                        self.log_message.emit("⏭️ 跳过此系列")
                        skipped += 1
                        continue
                    comic_info_base = scan_result.get("comic_info_base") or {}
                    comic_info_base["Manga"] = self.manga_value or comic_info_base.get("Manga", "Yes")
                    result = create_result_dict(folder_path, folder_info, comic_info_base,
                                                scan_result.get("selected_result"),
                                                False, "已修改")

                # 3. EditDialog 确认（单系列无导航；经 DialogBridge 主线程弹窗）
                resp = gui_callback('edit_result', result=result)
                if not self._is_running:
                    break
                if not (resp and resp.get('accepted')):
                    self.log_message.emit("⏭️ 取消编辑，跳过此系列")
                    skipped += 1
                    continue

                # 4. 确认后收集结果：逐系列发回主线程立即保存（防中途崩溃丢已确认结果）
                result.update(resp.get('data') or {})
                result["process_status"] = "已修改"
                results.append(result)
                self.series_saved.emit(result)
                processed += 1
                self.progress_range.emit(0, total)  # 恢复定进度
                self.progress_updated.emit(idx, f"✅ {folder_name} 处理完成")

            self.progress_updated.emit(total, "")
            self.progress_range.emit(0, 1)
            self.progress_updated.emit(1, "")
            self.scan_completed.emit(results)
            self.series_finished.emit(processed, skipped)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"扫描失败: {str(e)}")

    def stop(self) -> None:
        """停止扫描：置运行标志 + 取消当前等待中的对话框"""
        self._is_running = False
        self._bridge.cancel()
