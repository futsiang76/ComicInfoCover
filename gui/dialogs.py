#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立对话框 - 可复用的模态对话框
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout)


def _extract_count(stats: dict, key: str) -> int:
    """从 stats 提取数量，兼容 int 计数 / list 列表两种结构"""
    value = stats.get(key, 0)
    return len(value) if isinstance(value, list) else value


def _extract_file_list(stats: dict, count_key: str, list_keys: tuple) -> tuple:
    """从 stats 提取文件列表与总数，兼容 int 计数 / list 列表两种结构

    Args:
        stats: 扫描统计信息
        count_key: 数量字段名（int 计数 / list 列表均适用）
        list_keys: 候选文件列表字段名，按顺序取第一个非空 list

    Returns:
        (文件列表, 总数)：列表用于弹窗展示，总数用于统计区与省略号
    """
    files = []
    for key in list_keys:
        value = stats.get(key)
        if isinstance(value, list) and value:
            files = value
            break
    return files, _extract_count(stats, count_key)


def _format_file_list_html(title: str, file_list: list, total: int,
                           bg_color: str = "#fff3e0") -> str:
    """格式化文件列表区块 HTML

    最多列前 10 个，超过 10 个时在第 10 个后追加省略号行并带总数，
    避免弹窗文件列表过长。

    Args:
        title: 区块标题（如「📁 已有XML的文件：」）
        file_list: 文件名列表
        total: 文件总数（可能大于 len(file_list)）
        bg_color: 区块背景色
    """
    html = f"""
    <div style="background-color: {bg_color}; padding: 10px; border-radius: 5px; margin: 10px;">
        <b>{title}</b><br>
    """
    for file_path in file_list[:10]:
        html += f"• {file_path}<br>"
    if total > 10:
        html += f"• ... 共 {total} 个<br>"
    html += "</div>"
    return html


def _build_xml_stats_html(stats: dict) -> str:
    """构建弹窗统计区 + 两个文件列表区块的 HTML

    兼容两种 stats 结构：
    - int 版（scan_controller）：files_with_xml/files_without_xml 为计数，
      sample_files/no_xml_files 为前 10 示例列表
    - list 版（xml_mode_handler）：files_with_xml/files_without_xml 为完整列表，
      取前 10 展示
    """
    with_xml_files, with_xml_total = _extract_file_list(
        stats, 'files_with_xml', ('sample_files', 'files_with_xml'))
    without_xml_files, without_xml_total = _extract_file_list(
        stats, 'files_without_xml', ('no_xml_files', 'files_without_xml'))
    html = f"""
    <div style="background-color: #e3f2fd; padding: 10px; border-radius: 5px; margin: 10px;">
        <b>📊 检测统计：</b><br>
        • 总文件数：{stats.get('total_files', 0)} 个<br>
        • 已有XML：{with_xml_total} 个 ✅<br>
        • 无XML文件：{without_xml_total} 个 ❌
    </div>
    """
    if with_xml_files:
        html += _format_file_list_html(
            "📁 已有XML的文件：", with_xml_files, with_xml_total)
    if without_xml_files:
        html += _format_file_list_html(
            "📂 没有XML的文件：", without_xml_files, without_xml_total, "#e0f7fa")
    return html


def _normalize_source_name(source) -> str:
    """规范化数据源显示名：去掉「（默认）」后缀，空值兜底 Bangumi"""
    if not source:
        return "Bangumi"
    return source.split("（", 1)[0].strip() or "Bangumi"


def _resolve_source_name(mw) -> str:
    """从 mw 解析当前数据源显示名，取不到时兜底 Bangumi"""
    source = getattr(mw, "selected_source", None)
    if not source:
        source_combo = getattr(mw, "source_combo", None)
        if source_combo is not None:
            current_text = getattr(source_combo, "currentText", None)
            if callable(current_text):
                source = current_text()
    return _normalize_source_name(source)


def _build_xml_options_html(mw) -> str:
    """构建弹窗选项说明 HTML，数据源名随 mw 当前源动态化"""
    source_name = _resolve_source_name(mw)
    return f"""
    <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px;">
        <b>📝 直接修改已有XML</b><br>
        <span style="color: #666;">从XML文件读取元数据到编辑界面，不修改原文件，不进行{source_name}搜索</span>
        <br><br>
        <b>🔄 重新扫描生成XML</b><br>
        <span style="color: #666;">使用全匹配模式，重新从{source_name}获取信息并生成新的XML文件</span>
        <br><br>
        <b>⏭️ 跳过检查，按当前模式继续</b><br>
        <span style="color: #666;">使用当前选择的运行模式继续扫描</span>
    </div>
    """


def show_xml_exists_dialog(mw, stats: dict) -> str:
    """显示XML文件存在对话框，返回用户选择"""
    folder_name = stats.get("folder_name", "") or stats.get("series", "")
    title = f"检测到已有XML文件"
    if folder_name:
        title = f"📂 {folder_name} — {title}"
    dialog = QDialog(mw)
    dialog.setWindowTitle(title)
    dialog.setMinimumSize(600, 400)
    
    layout = QVBoxLayout()
    
    # 系列名（红色，醒目）
    if folder_name:
        series_label = QLabel(f"📂 {folder_name}")
        series_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #D32F2F; padding: 10px 10px 0 10px;")
        series_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(series_label)

    # 提示信息
    info_label = QLabel("⚠️ 检测到目录中已存在ComicInfo.xml文件")
    info_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FF9800; padding: 10px;")
    info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(info_label)
    
    # 统计信息 + 两个文件列表（统计区 → 已有XML文件 → 没有XML文件）
    stats_text = _build_xml_stats_html(stats)
    stats_label = QLabel(stats_text)
    stats_label.setStyleSheet("font-size: 13px; padding: 5px;")
    stats_label.setWordWrap(True)
    layout.addWidget(stats_label)
    
    # 详细说明
    detail_label = QLabel("请选择处理方式：")
    detail_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px;")
    layout.addWidget(detail_label)
    
    # 选项说明（数据源名随当前源动态化）
    options_label = QLabel(_build_xml_options_html(mw))
    options_label.setStyleSheet("font-size: 13px; padding: 5px;")
    options_label.setWordWrap(True)
    layout.addWidget(options_label)
    
    # 按钮区域
    button_layout = QHBoxLayout()
    button_layout.addStretch()
    
    # 直接修改按钮
    modify_btn = QPushButton("📝 直接修改")
    modify_btn.setMinimumHeight(45)
    modify_btn.setMinimumWidth(150)
    modify_btn.setStyleSheet("""
        QPushButton {
            background-color: #2196F3;
            color: white;
            font-size: 14px;
            font-weight: bold;
            border-radius: 5px;
            padding: 10px;
        }
        QPushButton:hover {
            background-color: #0b7dda;
        }
        QPushButton:pressed {
            background-color: #0a5f8f;
        }
    """)
    modify_btn.clicked.connect(lambda: dialog.done(1))  # 返回1表示修改
    button_layout.addWidget(modify_btn)
    
    # 重新扫描按钮
    rescan_btn = QPushButton("🔄 重新扫描")
    rescan_btn.setMinimumHeight(45)
    rescan_btn.setMinimumWidth(150)
    rescan_btn.setStyleSheet("""
        QPushButton {
            background-color: #4CAF50;
            color: white;
            font-size: 14px;
            font-weight: bold;
            border-radius: 5px;
            padding: 10px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
        QPushButton:pressed {
            background-color: #3d8b40;
        }
    """)
    rescan_btn.clicked.connect(lambda: dialog.done(2))  # 返回2表示重新扫描
    button_layout.addWidget(rescan_btn)
    
    # 跳过按钮
    skip_btn = QPushButton("⏭️ 跳过检查")
    skip_btn.setMinimumHeight(45)
    skip_btn.setMinimumWidth(150)
    skip_btn.setStyleSheet("""
        QPushButton {
            background-color: #9E9E9E;
            color: white;
            font-size: 14px;
            font-weight: bold;
            border-radius: 5px;
            padding: 10px;
        }
        QPushButton:hover {
            background-color: #757575;
        }
        QPushButton:pressed {
            background-color: #616161;
        }
    """)
    skip_btn.clicked.connect(lambda: dialog.done(3))  # 返回3表示跳过
    button_layout.addWidget(skip_btn)
    
    # 取消按钮
    cancel_btn = QPushButton("❌ 取消")
    cancel_btn.setMinimumHeight(45)
    cancel_btn.setMinimumWidth(120)
    cancel_btn.setStyleSheet("""
        QPushButton {
            background-color: #f44336;
            color: white;
            font-size: 14px;
            font-weight: bold;
            border-radius: 5px;
            padding: 10px;
        }
        QPushButton:hover {
            background-color: #da190b;
        }
        QPushButton:pressed {
            background-color: #b7140a;
        }
    """)
    cancel_btn.clicked.connect(lambda: dialog.done(0))  # 返回0表示取消
    button_layout.addWidget(cancel_btn)
    
    button_layout.addStretch()
    layout.addLayout(button_layout)
    
    dialog.setLayout(layout)
    
    result = dialog.exec()
    
    # 返回用户选择
    if result == 1:
        return "modify"
    elif result == 2:
        return "rescan"
    elif result == 3:
        return "skip"
    else:
        return "cancel"

