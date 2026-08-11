#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一后台扫描线程框架 - BaseScanThread

所有扫描源/模式共有的骨架：线程化 + 7 个公共信号 + DialogBridge 弹窗桥接
+ 逐系列保存 + 小猫等待（接线在 scan_controller）。子类只实现源/模式特有
的"配置"（source_name / search_and_select / build_result），禁止复制粘贴
线程代码。全匹配/manhuagui/comicvine/手动匹配/批量统一走此框架。
"""

import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from .gui_dialogs import DialogBridge


# 哨兵：search_and_select 返回 (RESULT_READY, result_dict) 表示结果已构建完毕
# （「已有 XML 修改」路径使用，跳过 build_result 直接进入编辑确认）
RESULT_READY = object()


class _XmlScanContext:
    """供 XmlModeHandler 使用的最小处理器上下文（所有扫描源共用）

    复用 xml_mode_handler 的「已有 XML 分流」逻辑（模式 0：有 XML 时弹窗询问
    处理方式），避免在 scan_controller 及各源线程中重复实现。
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


class _ThreadLog:
    """工作线程日志接收器：log_text.append 转发到 log_message 信号

    让复用主线程的搜索函数只需写 mw.log_text.append，
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


class BaseScanThread(QThread):
    """统一后台扫描线程框架：线程化 + 信号 + 弹窗桥接 + 逐系列保存

    子类需实现（源/模式特有的"配置"）：
      - source_name: str    数据源/模式标识（"bangumi"/"manhuagui"/"comicvine"/
                             "manual"/"batch"）
      - search_and_select(folder_path, folder_info)
          -> (comic_info_base, selected_result) 或 (RESULT_READY, result_dict)
          -> 返回 None 表示跳过此系列。
          弹窗一律走 self._gui_callback / DialogBridge，不得直接创建 widget。
      - build_result(folder_path, folder_info, comic_info_base, selected_result)
          -> result dict，在编辑确认前构建最终结果。

    run() 为公共主循环：逐个系列「搜索选择 → 编辑确认 → 逐系列保存」，
    收尾发 scan_completed / series_finished，异常发 error_occurred。
    """

    progress_updated = Signal(int, str)   # (进度值, 状态消息)
    progress_range = Signal(int, int)     # (min, max)，对应 setRange 语义
    log_message = Signal(str)
    scan_completed = Signal(list)          # 收集到的结果列表
    series_saved = Signal(dict)            # 单系列确认结果（逐系列即时保存）
    error_occurred = Signal(str)
    series_finished = Signal(int, int)     # (processed, skipped) 收尾用

    source_name = "base"                       # 数据源/模式标识
    source_label = "扫描"                       # 开始日志用的显示名（可覆盖）

    def __init__(self, manga_root: str, manga_value: Optional[str],
                 folders: Optional[List[Tuple[str, Dict]]] = None, parent=None):
        super().__init__()
        self.manga_root = manga_root
        self.manga_value = manga_value
        self.folders = list(folders or [])
        self._is_running = True
        self._total = 1
        # 已有 XML 分流处理器（惰性初始化，所有源共用）
        self._xml_handler = None
        self._xml_ctx = None
        # 对话框桥接器（在 __init__ 中创建，确保主线程亲和性）
        self._bridge = DialogBridge(parent)

    def run(self) -> None:
        """后台逐系列「搜索选择 → 编辑确认 → 逐系列保存」主循环（子类无需重写）"""
        try:
            import config

            from .scan_controller import _collect_series_folders

            # 逐系列交互流程不触发无人值守/XML 模式短路（与既有单系列语义一致）
            config.AUTO_TURBO_MATCH = 0
            config.MODE_SKIP_XMLEXIST = 0

            folders = self.folders or _collect_series_folders(self.manga_root)
            self._total = max(1, len(folders))
            self.progress_range.emit(0, self._total)
            self.progress_updated.emit(0, f"{self.source_label}扫描: 共 {self._total} 个系列")

            results: List[Dict] = []
            processed = 0
            skipped = 0

            for idx, (folder_path, folder_info) in enumerate(folders, start=1):
                if not self._is_running:
                    break
                folder_name = os.path.basename(folder_path)
                self.progress_updated.emit(idx - 1, f"\n[{idx}/{self._total}] 📁 {folder_name}")
                self.progress_range.emit(0, 0)   # 不定进度 -> Qt 滚动动画

                out = self.search_and_select(folder_path, folder_info)
                if not self._is_running:
                    break
                if out is None:
                    skipped += 1
                    continue
                if out[0] is RESULT_READY:
                    result = out[1]              # 结果已构建（如 XML 修改路径）
                else:
                    comic_info_base, selected_result = out
                    comic_info_base["Manga"] = self.manga_value or comic_info_base.get("Manga", "Yes")
                    result = self.build_result(folder_path, folder_info,
                                               comic_info_base, selected_result)

                # 编辑确认（经 DialogBridge 主线程弹窗）
                resp = self._gui_callback('edit_result', result=result)
                if not self._is_running:
                    break
                if not (resp and resp.get('accepted')):
                    self.log_message.emit("⏭️  取消编辑，跳过此系列")
                    skipped += 1
                    continue

                # 确认后逐系列发回主线程立即保存（防中途崩溃丢已确认结果）
                result.update(resp.get('data') or {})
                result["process_status"] = "已修改"
                results.append(result)
                self.series_saved.emit(result)
                processed += 1
                self.progress_range.emit(0, self._total)  # 恢复定进度
                self.progress_updated.emit(idx, f"✅ {folder_name} 处理完成")

            self.progress_updated.emit(self._total, "")
            self.progress_range.emit(0, 1)
            self.progress_updated.emit(1, "")
            self.scan_completed.emit(results)
            self.series_finished.emit(processed, skipped)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"扫描失败: {str(e)}")
        finally:
            self.cleanup()

    # ---- 子类配置接口 ----

    def search_and_select(self, folder_path: str, folder_info: Dict):
        """源/模式特有的搜索与选择

        Returns:
            (comic_info_base, selected_result) 正常结果；
            (RESULT_READY, result_dict) 结果已构建；
            None 表示跳过此系列。
        """
        raise NotImplementedError

    def build_result(self, folder_path: str, folder_info: Dict,
                     comic_info_base: Dict, selected_result: Optional[Dict]) -> Dict:
        """源/模式特有的结果构建"""
        raise NotImplementedError

    def cleanup(self) -> None:
        """扫描结束资源释放（子类按需覆盖，如关闭 fetcher 浏览器实例）"""
        pass

    def _gui_callback(self, action: str, **params):
        """工作线程弹窗回调：桥接到主线程；停止后不再弹窗"""
        if not self._is_running:
            if action == 'search_failure':
                return {'action': 'skip', 'value': None}
            if action == 'edit_result':
                return {'accepted': False, 'data': None}
            return None
        return self._bridge.invoke(action, **params)

    def _init_xml_handler(self) -> None:
        """惰性初始化已有 XML 分流处理器（仅首个文件夹创建一次）"""
        if self._xml_handler is None:
            from processors.xml_mode_handler import create_xml_mode_handler
            self._xml_handler = create_xml_mode_handler(
                _XmlScanContext(self._gui_callback, self.manga_value))
            self._xml_ctx = self._xml_handler.processor

    def check_existing_xml(self, folder_path: str, folder_info: Dict) -> Tuple[bool, Optional[Any]]:
        """已有 XML 分流（所有源统一入口）

        有 XML 时弹窗询问处理方式（mode 0 语义）：'modify' 返回只读结果直接进入
        编辑确认，'skip' 跳过该系列，'cancel' 终止整个扫描（置 _is_running=False）。

        Returns:
            (True, (RESULT_READY, result_dict))：XML 修改结果，直接进入编辑确认；
            (True, None)：跳过此系列（'skip'/'cancel'，日志已输出）；
            (False, None)：无 XML 或选择重扫，继续正常搜索流程。
        """
        self._init_xml_handler()
        xml_status, xml_stats = self._xml_handler.check_folder_xml(folder_path, folder_info)
        result = self._xml_handler.handle_existing_xml(folder_path, folder_info, 0,
                                                       xml_status, xml_stats)
        if self._xml_ctx._cancelled:
            self.log_message.emit("🛑 用户取消扫描")
            self._is_running = False
            return True, None
        if result is not None:
            if result.get("skipped"):
                self.log_message.emit("⏭️  跳过此系列（已有XML）")
                return True, None
            # 'modify'：从 XML 读取的只读结果，仍弹编辑确认
            result["process_status"] = "已修改"
            return True, (RESULT_READY, result)
        return False, None

    def stop(self) -> None:
        """停止扫描：置运行标志 + 取消当前等待中的对话框"""
        self._is_running = False
        self._bridge.cancel()
