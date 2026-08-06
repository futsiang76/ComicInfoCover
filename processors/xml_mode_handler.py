#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML模式处理器 - 已有XML文件夹的分流逻辑

封装 高速(1)/修正(2) 模式的快速分流，以及 全匹配(0)/单系列(3) 模式
下的 GUI 弹窗询问。模式判断优先于弹窗，保证 GUI 下高速/修正模式
不会被「检测到已有XML」对话框短路。
"""

import os
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from processors.utils import process_xml_modify_folder


class XmlModeHandler:
    """已有XML文件夹的模式分流处理

    持有 BatchProcessor 实例以访问其状态（mode_skip_xml/gui_callback/
    skipped/auto_processed 等），减轻 batch_processor.py 的体积。
    """

    def __init__(self, processor: Any):
        """初始化

        Args:
            processor: BatchProcessor 实例
        """
        self.processor = processor

    def check_folder_xml(self, folder_path: str, folder_info: Dict) -> Tuple[str, Dict]:
        """检查单个文件夹的XML覆盖情况，返回三档状态

        Args:
            folder_path: 文件夹路径
            folder_info: 文件夹信息

        Returns:
            tuple: (xml_status, 统计信息dict)
                xml_status: 'all'（全部卷有XML）| 'none'（全部卷无XML）| 'partial'（部分卷有XML）
                统计信息中 files_with_xml / files_without_xml 为文件名列表
        """
        stats = {
            "total_files": 0,
            "files_with_xml": [],
            "files_without_xml": [],
            "sample_files": [],
            "xml_status": "none",
            "folder_name": os.path.basename(folder_path),
            "series": folder_info.get("series", "")
        }

        try:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith((".zip", ".cbz", ".cbr", ".rar")):
                    continue
                file_path = os.path.join(folder_path, filename)
                if not os.path.isfile(file_path):
                    continue

                stats["total_files"] += 1
                try:
                    with zipfile.ZipFile(file_path, "r") as zf:
                        if "ComicInfo.xml" in zf.namelist():
                            stats["files_with_xml"].append(filename)
                            if len(stats["sample_files"]) < 5:
                                stats["sample_files"].append(filename)
                        else:
                            stats["files_without_xml"].append(filename)
                except Exception:
                    stats["files_without_xml"].append(filename)
        except Exception as e:
            print(f"⚠️  检查文件夹XML状态失败: {str(e)[:50]}")

        # 三档分流：无归档文件视为 none；有缺XML卷视为 partial；否则 all
        if stats["files_without_xml"]:
            stats["xml_status"] = "partial" if stats["files_with_xml"] else "none"
        else:
            stats["xml_status"] = "all" if stats["files_with_xml"] else "none"
        return stats["xml_status"], stats

    def handle_existing_xml(self, folder_path: str, folder_info: Dict, depth: int,
                            xml_status: str, xml_stats: Dict) -> Optional[Dict]:
        """按模式分流处理已有XML的文件夹

        模式判断优先于 GUI 弹窗：
        - mode 1（补漏）：三档分流——全部有XML跳过 / 部分有XML补漏写入缺失卷 / 全部无XML正常扫描
        - mode 2（修正）：有XML → 读XML构建结果；无XML → 直接跳过，不弹窗
        - mode 3（手动匹配）：不询问XML处理方式，直接继续扫描（逐文件夹输入ID）
        - mode 0：有XML才走 GUI 弹窗流程（无人值守跳过弹窗继续扫描）

        Args:
            folder_path: 文件夹路径
            folder_info: 文件夹信息
            depth: 当前深度
            xml_status: 'all' / 'none' / 'partial'
            xml_stats: XML统计信息

        Returns:
            Optional[Dict]: 已确定的结果字典；None 表示继续正常扫描流程
        """
        p = self.processor
        mode = p.mode_skip_xml

        # 补漏模式（mode 1）：三档分流
        if mode == 1:
            if xml_status == 'all':
                print(f"{'  ' * depth}⏭️ 补漏模式：全部卷已包含XML，跳过整个文件夹")
                p.skipped += 1
                return p._create_result_dict(folder_path, folder_info, None, None, True, "已跳过（已有XML）")
            if xml_status == 'partial':
                return self.process_xml_backfill(folder_path, folder_info, depth, xml_stats)
            # 'none' → 全部卷无XML，返回 None 继续正常扫描
            return None

        # 修正模式：有XML读XML构建结果，无XML直接跳过（均不弹窗）
        if mode == 2:
            if xml_status != 'none':
                return self.process_xml_modify(folder_path, folder_info, depth)
            print(f"{'  ' * depth}⏭️ 修正模式：文件夹下没有文件包含XML，跳过整个文件夹")
            p.skipped += 1
            return p._create_result_dict(folder_path, folder_info, None, None, True, "已跳过（无XML）")

        # 手动匹配模式（mode 3）：用户已明确要逐文件夹输入 Bangumi ID 处理，
        # 无论有无 XML 都不询问处理方式，直接继续扫描流程
        if mode == 3:
            return None

        # 以下仅 mode 0 且有XML时触发 GUI 弹窗
        if xml_status == 'none':
            return None

        if p.gui_callback and not p.auto_turbo:
            choice = p.gui_callback('xml_exists', stats=xml_stats)
            if choice == 'cancel':
                p._cancelled = True
                return None
            elif choice == 'modify':
                print(f"{'  ' * depth}📖 用户选择修改模式：从XML读取元数据")
                return self.process_xml_modify(folder_path, folder_info, depth)
            elif choice == 'skip':
                print(f"{'  ' * depth}⏭️ 用户跳过此系列（已有XML）")
                p.skipped += 1
                return p._create_result_dict(folder_path, folder_info, None, None, True, "已跳过（已有XML）")
            # choice == 'rescan': 重新扫描，继续正常流程
        elif p.gui_callback and p.auto_turbo:
            # 无人值守模式：不弹窗，直接继续扫描（覆盖XML）
            pass
        # 控制台模式（gui_callback=None）：mode 0/3 有XML时直接继续正常扫描（覆盖XML）
        return None

    def process_xml_backfill(self, folder_path: str, folder_info: Dict, depth: int,
                             xml_stats: Dict) -> Optional[Dict]:
        """补漏流程：部分卷有XML → 读基础信息 → 为缺失卷补写XML

        读取第一个有XML卷的 comic_info_base（复用 process_xml_modify_folder），
        对缺XML的卷逐个按文件名解析 Volume 生成 XML 写入，结果进结果页并标
        记「已补漏」。

        Args:
            folder_path: 文件夹路径
            folder_info: 文件夹信息
            depth: 当前深度
            xml_stats: check_folder_xml 返回的统计信息

        Returns:
            Optional[Dict]: 补漏结果字典；读取基础信息失败时返回失败跳过结果
        """
        p = self.processor
        print(f"{'  ' * depth}🔧 补漏模式：部分卷已有XML，为缺失卷补写XML")

        # 1. 读取第一个有XML卷的系列基础信息
        xml_result = process_xml_modify_folder(folder_path, folder_info, depth)
        comic_info_base = xml_result.get("comic_info_base") if xml_result else None
        if not comic_info_base:
            print(f"{'  ' * depth}❌ 补漏失败：无法读取已有XML基础信息")
            p.skipped += 1
            return p._create_result_dict(folder_path, folder_info, None, None, True, "补漏失败")

        # 2. 为缺失XML的卷逐个补写（Volume 从文件名解析，其余字段继承基础信息）
        from processors.xml_generator import XMLGenerator
        from processors.zip_operations import add_file_to_zip

        xml_generator = XMLGenerator()
        manga_value = comic_info_base.get("Manga") or p.manga_value or "Yes"
        total_files = 0
        success_files = 0

        for filename in xml_stats.get("files_without_xml", []):
            file_path = os.path.join(folder_path, filename)
            if not os.path.isfile(file_path):
                continue
            total_files += 1
            try:
                file_comic_info = comic_info_base.copy()
                file_comic_info["Manga"] = manga_value
                xml_content = xml_generator.generate_for_file(file_comic_info, filename, folder_info)
                write_result = add_file_to_zip(file_path, xml_content)
                # True=已写入；None=内容一致（视为成功）；False=写入失败
                if write_result is not False:
                    success_files += 1
            except Exception as e:
                print(f"{'  ' * depth}❌ 补写失败 {filename}: {str(e)[:50]}")

        p.total_files += total_files
        p.success_files += success_files
        p.auto_processed += 1

        print(f"{'  ' * depth}✅ 补漏完成：{success_files}/{total_files} 个缺失卷已补写XML")

        # 3. 构建结果（comic_info_base + file_titles/file_details）进结果页
        return p._create_result_dict(
            folder_path, folder_info, comic_info_base,
            xml_result.get("selected_result"), False, "已补漏"
        )

    def process_xml_modify(self, folder_path: str, folder_info: Dict, depth: int) -> Optional[Dict]:
        """修正流程：读取已有XML构建完整结果（skip_files=True、xml_readonly=True）

        Args:
            folder_path: 文件夹路径
            folder_info: 文件夹信息
            depth: 当前深度

        Returns:
            Optional[Dict]: 结果字典；XML读取失败时返回失败跳过结果
        """
        p = self.processor
        print(f"{'  ' * depth}📖 修正模式：从XML文件读取元数据（不更新文件）")

        xml_result = process_xml_modify_folder(folder_path, folder_info, depth)
        if xml_result and xml_result.get("comic_info_base"):
            xml_result["skip_files"] = True
            xml_result["xml_readonly"] = True
            p.auto_processed += 1
            result = p._create_result_dict_from_xml(folder_path, folder_info, xml_result)
            result["_from_modify"] = True  # 标记：GUI 收到后自动打开编辑弹窗
            result["process_status"] = "已修改XML"
            return result
        print(f"{'  ' * depth}❌ 无法从XML读取元数据")
        p.skipped += 1
        return p._create_result_dict(folder_path, folder_info, None, None, True, "XML读取失败")


def create_xml_mode_handler(processor: Any) -> XmlModeHandler:
    """创建XML模式处理器

    Args:
        processor: BatchProcessor 实例

    Returns:
        XmlModeHandler: XML模式处理器实例
    """
    return XmlModeHandler(processor)
