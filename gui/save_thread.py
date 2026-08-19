#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量保存后台线程 - SaveThread

把 save_changes 的写盘循环移入 QThread：保存阶段主线程事件循环保持空闲，
工作小猫动画（QMovie）由事件循环正常驱动播放。写盘逻辑与旧同步版零改动，
仅增加进度信号 emit，GUI 更新一律在 save_handler 的主线程槽里完成。
"""

import os

from PySide6.QtCore import QThread, Signal


class SaveThread(QThread):
    """后台保存线程：逐 zip 生成 XML 并写盘

    run() 内只做文件写入（add_file_to_zip）与 SQLite 缓存更新，不触碰任何
    widget；进度与结果经信号回主线程。信号槽断开后由 Qt 自动回收（或由
    save_handler 挂 mw._save_threads 防 GC）。
    """

    progress_updated = Signal(int, int, str)  # (已处理文件数, 总数, 状态消息)
    save_finished = Signal(int, int, list)    # (total_files, success_files, error_messages)

    def __init__(self, modified_results, parent=None):
        super().__init__(parent)
        self.modified_results = list(modified_results)

    def _count_total_files(self) -> int:
        """统计待保存的漫画文件总数（写盘前预扫描，供进度信号使用）"""
        total = 0
        for result in self.modified_results:
            folder_path = result.get("folder_path", "")
            if not folder_path or not os.path.isdir(folder_path):
                continue
            total += sum(
                1 for fn in os.listdir(folder_path)
                if os.path.isfile(os.path.join(folder_path, fn))
                and fn.lower().endswith(('.zip', '.cbz', '.cbr', '.rar'))
            )
        return total

    def run(self) -> None:
        from processors.xml_generator import XMLGenerator, build_file_comicinfo
        from processors.zip_handler import add_file_to_zip, check_zip_xml_files

        xml_generator = XMLGenerator()

        total_files = self._count_total_files()
        processed = 0
        success_files = 0
        error_messages = []

        for result in self.modified_results:
            folder_path = result.get("folder_path", "")
            if not folder_path or not os.path.isdir(folder_path):
                error_messages.append(f"文件夹不存在: {folder_path}")
                continue

            # 获取该系列的 file_titles、file_details 和 locked_files
            file_titles = result.get("file_titles", {})
            file_details = result.get("file_details", {})
            locked_files = result.get("locked_files", set())

            # 遍历文件夹中的漫画文件
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                if not os.path.isfile(file_path):
                    continue
                if not filename.lower().endswith(('.zip', '.cbz', '.cbr', '.rar')):
                    continue

                processed += 1
                self.progress_updated.emit(processed, total_files, filename)

                try:
                    # per-file 字段统一入口（系列字段 + Title/Volume/Number/锁定字段/Notes）
                    detail = file_details.get(filename, {})
                    is_locked = filename in locked_files
                    file_comic_info = build_file_comicinfo(
                        result, filename,
                        file_titles=file_titles, detail=detail, is_locked=is_locked)

                    # 生成XML
                    xml_content = xml_generator.generate_comicinfo_xml(file_comic_info)

                    # 先检查ZIP中已有XML是否与新生成的一致
                    target_exists, content_matches, other_xml_files = check_zip_xml_files(file_path, xml_content)
                    if target_exists and content_matches:
                        success_files += 1
                        continue

                    # 内容不一致或不存在，写入ZIP文件（复用已 check 结果，避免二次 check 重复打印差异日志）
                    write_result = add_file_to_zip(file_path, xml_content,
                                                   prechecked=(target_exists, content_matches, other_xml_files))
                    if write_result:
                        success_files += 1
                    else:
                        error_messages.append(f"写入失败: {filename}")

                    # 更新 SQLite 锁定状态缓存
                    try:
                        from models.database import LockDatabase
                        db = LockDatabase()
                        db.set_lock_state(
                            filename,
                            os.path.getsize(file_path),
                            result.get("series", ""),
                            is_locked
                        )
                    except Exception:
                        pass

                except Exception as e:
                    error_messages.append(f"处理失败 {filename}: {str(e)[:80]}")

        self.save_finished.emit(processed, success_files, error_messages)
