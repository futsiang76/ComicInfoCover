#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量保存 - 将编辑后的元数据写入XML文件
"""

import os

from PyQt6.QtWidgets import QMessageBox


def save_changes(mw, show_result: bool = True):
    modified_results = [r for r in mw.scan_results if r.get("process_status") == "已修改"]

    if not modified_results:
        QMessageBox.information(mw, "提示", "没有需要保存的修改")
        return

    from parsers.file_parser import parse_volume_from_filename
    from processors.xml_generator import XMLGenerator
    from processors.zip_handler import add_file_to_zip, check_zip_xml_files

    xml_generator = XMLGenerator()

    total_files = 0
    success_files = 0
    error_messages = []

    for result in modified_results:
        folder_path = result.get("folder_path", "")
        if not folder_path or not os.path.isdir(folder_path):
            error_messages.append(f"文件夹不存在: {folder_path}")
            continue

        from processors.xml_generator import build_full_comicinfo_dict
        comic_info_base = build_full_comicinfo_dict(result)

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

            total_files += 1

            try:
                # 复制基础数据用于此文件
                file_comic_info = comic_info_base.copy()

                # 如果 file_titles 中有该文件的 Title，使用它
                if filename in file_titles:
                    file_comic_info["Title"] = file_titles[filename]
                else:
                    # 否则用 generate_smart_title 生成
                    from parsers.file_parser import generate_smart_title
                    folder_info = {"series": result.get("series", ""), "complete": result.get("status") == "Completed"}
                    smart_title_result = generate_smart_title(filename, result.get("series", ""), folder_info)
                    file_comic_info["Title"] = smart_title_result[0]

                # 如果 file_details 中有该文件的信息，覆盖
                detail = file_details.get(filename, {})
                is_locked = filename in locked_files
                if detail.get("volume"):
                    file_comic_info["Volume"] = detail["volume"]
                    file_comic_info["Number"] = ""
                else:
                    # 解析卷数信息
                    vol_info = parse_volume_from_filename(filename)
                    if vol_info.get("number") and vol_info["number"].strip():
                        file_comic_info["Volume"] = vol_info["number"]
                        file_comic_info["Number"] = ""
                    else:
                        import re
                        chapter_match = re.search(r'(C\s*\d+|第\s*\d+\s*话)', filename, re.IGNORECASE)
                        if chapter_match:
                            number_match = re.search(r'\d+', chapter_match.group(1))
                            if number_match:
                                file_comic_info["Number"] = number_match.group()
                                file_comic_info["Volume"] = ""
                        else:
                            file_comic_info["Volume"] = ""
                            file_comic_info["Number"] = ""

                # 锁住的文件：用 file_details 中的独立值覆盖系列级数据
                # 未锁住的文件：year/month/summary 跟随系列级数据
                if is_locked:
                    if detail.get("year"):
                        file_comic_info["Year"] = detail["year"]
                    if detail.get("month"):
                        file_comic_info["Month"] = detail["month"]
                    if detail.get("summary"):
                        file_comic_info["Summary"] = detail["summary"]

                # 写入锁定标记到 Notes 字段
                file_comic_info["Notes"] = "ComicScratcherLocked" if is_locked else ""

                # 生成XML
                xml_content = xml_generator.generate_comicinfo_xml(file_comic_info)

                # 先检查ZIP中已有XML是否与新生成的一致
                target_exists, content_matches, _ = check_zip_xml_files(file_path, xml_content)
                if target_exists and content_matches:
                    success_files += 1
                    continue

                # 内容不一致或不存在，写入ZIP文件
                write_result = add_file_to_zip(file_path, xml_content)
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

    # 更新处理状态
    for result in modified_results:
        result["process_status"] = "已保存"

    mw.update_results_table()

    if show_result:
        # 显示结果
        msg = f"保存完成\n\n总文件数: {total_files}\n成功: {success_files}\n失败: {total_files - success_files}"
        if error_messages:
            msg += f"\n\n错误信息:\n" + "\n".join(error_messages[:10])
            if len(error_messages) > 10:
                msg += f"\n...还有 {len(error_messages) - 10} 个错误"

        if total_files - success_files > 0:
            QMessageBox.warning(mw, "保存结果", msg)
        else:
            QMessageBox.information(mw, "保存结果", msg)


