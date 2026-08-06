#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描标签页 - 漫画目录扫描操作面板
"""

from pathlib import Path

from PyQt6.QtCore import QSettings, QSize
from PyQt6.QtGui import QFont, QMovie
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                             QPushButton, QRadioButton, QTextEdit, QVBoxLayout,
                             QWidget)

from config import AUTO_TURBO_MATCH, MODE_SKIP_XMLEXIST

from .utils import SmoothMovieLabel


MODE_CONSTRAINED_SOURCES = ("manhuagui", "ComicVine")

MODE_DESCRIPTIONS = {
    0: "逐文件夹匹配 Bangumi，匹配失败时弹出选择窗口。速度最慢但结果最准确。",
    1: "跳过已有 XML 的文件夹，只处理没有 XML 的新文件夹，补齐缺失的 XML 信息。",
    2: "只处理已有 XML 的文件夹，修正错误数据。不处理没有 XML 的新文件夹。",
    3: "人工到 Bangumi 查询编号，输入 Bangumi ID 后扫描。适合需要人工确认匹配的系列，可处理多个系列。",
}


def _on_source_changed(mw, text: str) -> None:
    """数据源下拉框变化：记录选中源并联动模式控件显隐"""
    mw.selected_source = text
    if text not in MODE_CONSTRAINED_SOURCES:
        # 切回 Bangumi：仅使用本地信息重置为未勾选（受限源下隐藏，不保留勾选状态）
        mw.local_only_check.setChecked(False)
    apply_source_mode_constraint(mw, text)


def apply_source_mode_constraint(mw, source: str) -> None:
    """数据源联动：manhuagui/ComicVine 固定全匹配模式并隐藏受限控件；Bangumi 恢复

    作为数据源切换与扫描结束解锁的共用入口（scan_controller 恢复时也调用），
    保证受限源下非全匹配模式控件始终不可见/不可用。
    """
    constrained = source in MODE_CONSTRAINED_SOURCES
    if constrained:
        mw._mode_radios[0].setChecked(True)  # 固定全匹配模式
        mw.mode_description_label.setText(MODE_DESCRIPTIONS[0])
    for val, radio in mw._mode_radios.items():
        hidden = constrained and val != 0
        radio.setVisible(not hidden)
        radio.setEnabled(not hidden)
    mw.local_only_check.setVisible(not constrained)
    if constrained:
        # 无人值守与受限模式互斥，切源时强制复位
        mw.auto_turbo_check.setChecked(False)
        mw.auto_turbo_check.hide()
        mw.auto_turbo_desc.hide()
    else:
        # 非受限：无人值守显隐跟随当前模式（对齐 _on_mode_changed）
        show_auto_turbo = mw.mode_group.checkedId() == 0
        mw.auto_turbo_check.setVisible(show_auto_turbo)
        mw.auto_turbo_desc.setVisible(show_auto_turbo)


def build_scan_tab(mw, tab_widget):
    """创建扫描标签页"""
    scan_tab = QWidget()
    layout = QVBoxLayout()
    scan_tab.setLayout(layout)

    # 运行模式组
    mode_group = QGroupBox("运行模式")
    mode_layout = QVBoxLayout()

    mw.mode_group = QButtonGroup()
    mw.mode_group.setExclusive(True)

    radio_layout = QHBoxLayout()
    radio_style = """
        QRadioButton {
            color: #2E7D32;
            font-size: 13px;
            font-weight: bold;
            padding: 6px 14px;
            spacing: 6px;
        }
        QRadioButton::indicator {
            width: 18px;
            height: 18px;
        }
        QRadioButton::indicator:unchecked {
            border: 2px solid #81C784;
            border-radius: 9px;
            background-color: #E8F5E9;
        }
        QRadioButton::indicator:checked {
            border: 2px solid #1B5E20;
            border-radius: 9px;
            background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #66BB6A, stop:0.6 #43A047, stop:1 #2E7D32);
        }
        QRadioButton:hover {
            background-color: #C8E6C9;
            border-radius: 4px;
        }
    """

    mode_options = [
        (0, "全匹配模式"),
        (1, "补漏模式"),
        (2, "修正模式"),
        (3, "手动匹配模式"),
    ]

    mw._mode_radios = {}
    for val, label in mode_options:
        radio = QRadioButton(label)
        radio.setStyleSheet(radio_style)
        mw.mode_group.addButton(radio, val)
        radio_layout.addWidget(radio)
        mw._mode_radios[val] = radio

    default_button = mw.mode_group.button(MODE_SKIP_XMLEXIST)
    if default_button:
        default_button.setChecked(True)

    mode_layout.addLayout(radio_layout)

    # 模式动态描述标签
    mw.mode_description_label = QLabel()
    mw.mode_description_label.setStyleSheet("""
        QLabel {
            color: #2E7D32;
            font-size: 12px;
            margin-left: 4px;
            margin-top: 2px;
        }
    """)
    def _on_mode_changed(btn):
        mode_id = mw.mode_group.id(btn)
        mw.mode_description_label.setText(MODE_DESCRIPTIONS.get(mode_id, ""))
        # 受限源下无人值守始终隐藏；否则仅全匹配模式可见
        if mw.selected_source in MODE_CONSTRAINED_SOURCES:
            mw.auto_turbo_check.setChecked(False)
            mw.auto_turbo_check.hide()
            mw.auto_turbo_desc.hide()
        elif mode_id == 0:
            mw.auto_turbo_check.show()
            mw.auto_turbo_desc.show()
        else:
            mw.auto_turbo_check.setChecked(False)
            mw.auto_turbo_check.hide()
            mw.auto_turbo_desc.hide()
    mw.mode_group.buttonClicked.connect(_on_mode_changed)
    # 初始显隐：非全匹配模式时隐藏无人值守区域
    current_mode_id = mw.mode_group.id(default_button) if default_button else MODE_SKIP_XMLEXIST
    if current_mode_id != 0:
        mw.auto_turbo_check.hide()
        mw.auto_turbo_desc.hide()
    mw.mode_description_label.setText(MODE_DESCRIPTIONS.get(MODE_SKIP_XMLEXIST, ""))
    mode_layout.addWidget(mw.mode_description_label)

    mw.auto_turbo_check = QCheckBox("无人值守模式")
    mw.auto_turbo_check.setStyleSheet("QCheckBox { font-weight: bold; }")
    mw.auto_turbo_check.setChecked(AUTO_TURBO_MATCH == 1)
    mode_layout.addWidget(mw.auto_turbo_check)

    # 无人值守模式描述标签
    mw.auto_turbo_desc = QLabel(
        "唯一匹配自动处理，跳过多结果和无结果的情况。全程无人参与中断，适合大量目录批量扫描。扫描后需要人工查补。"
    )
    mw.auto_turbo_desc.setStyleSheet("""
        QLabel {
            color: #2E7D32;
            font-size: 12px;
            margin-left: 4px;
        }
    """)
    mode_layout.addWidget(mw.auto_turbo_desc)

    mode_group.setLayout(mode_layout)
    layout.addWidget(mode_group)

    # 数据源选择：Bangumi（默认）/ manhuagui / ComicVine，选中后走对应单系列扫描
    source_group = QGroupBox("数据源")
    source_layout = QHBoxLayout()
    source_layout.addWidget(QLabel("选择数据源:"))
    mw.source_combo = QComboBox()
    # 配色对齐「漫画根目录」路径输入框（绿色主题）
    mw.source_combo.setStyleSheet("border: 2px solid #4CAF50; padding: 4px; font-size: 13px; background-color: #f0fff0;")
    mw.source_combo.addItems(["Bangumi（默认）", "manhuagui", "ComicVine"])
    mw.source_combo.setCurrentIndex(0)
    mw.selected_source = "Bangumi（默认）"
    mw.source_combo.currentTextChanged.connect(lambda text: _on_source_changed(mw, text))
    source_layout.addWidget(mw.source_combo)
    source_layout.addStretch()
    source_group.setLayout(source_layout)
    layout.addWidget(source_group)

    # 扫描操作组
    scan_group = QGroupBox("扫描操作")
    scan_layout = QVBoxLayout()

    # 路径选择
    path_layout = QHBoxLayout()
    # 漫画根目录标签 - 加粗14px
    path_label = QLabel("漫画根目录:")
    path_label_font = QFont()
    path_label_font.setBold(True)
    path_label_font.setPointSize(14)
    path_label.setFont(path_label_font)
    path_layout.addWidget(path_label)

    mw.path_edit = QLineEdit()
    # 路径输入框 - 绿色边框和浅绿背景
    mw.path_edit.setStyleSheet("border: 2px solid #4CAF50; padding: 4px; font-size: 13px; background-color: #f0fff0;")
    path_layout.addWidget(mw.path_edit)

    browse_btn = QPushButton("浏览...")
    browse_btn.setStyleSheet("""
        QPushButton {
            background-color: #4CAF50;
            color: white;
            font-size: 13px;
            border-radius: 3px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
    """)
    browse_btn.clicked.connect(mw.browse_path)
    path_layout.addWidget(browse_btn)

    scan_layout.addLayout(path_layout)

    # 选项
    options_layout = QHBoxLayout()
    mw.local_only_check = QCheckBox("仅使用本地信息")
    options_layout.addWidget(mw.local_only_check)
    scan_layout.addLayout(options_layout)

    # 主要操作按钮区域 - 使用更突出的样式
    main_action_layout = QHBoxLayout()
    main_action_layout.addStretch()

    mw.scan_btn = QPushButton("🚀 开始扫描")
    mw.scan_btn.setMinimumHeight(45)
    mw.scan_btn.setMinimumWidth(150)
    mw.scan_btn.setStyleSheet("""
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
        QPushButton:disabled {
            background-color: #cccccc;
            color: #666666;
        }
    """)
    mw.scan_btn.clicked.connect(mw.start_scan)
    main_action_layout.addWidget(mw.scan_btn)

    mw.edit_xml_btn = QPushButton("📝 编辑XML")
    mw.edit_xml_btn.setMinimumHeight(45)
    mw.edit_xml_btn.setMinimumWidth(130)
    mw.edit_xml_btn.setStyleSheet("""
        QPushButton {
            background-color: #FF9800;
            color: white;
            font-size: 14px;
            font-weight: bold;
            border-radius: 5px;
            padding: 10px;
        }
        QPushButton:hover {
            background-color: #e68900;
        }
        QPushButton:pressed {
            background-color: #cc7a00;
        }
    """)
    mw.edit_xml_btn.clicked.connect(mw.on_edit_xml_clicked)
    main_action_layout.addWidget(mw.edit_xml_btn)

    mw.stop_btn = QPushButton("⏹️ 停止扫描")
    mw.stop_btn.setMinimumHeight(45)
    mw.stop_btn.setMinimumWidth(150)
    mw.stop_btn.setEnabled(False)
    mw.stop_btn.setStyleSheet("""
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
        QPushButton:disabled {
            background-color: #cccccc;
            color: #666666;
        }
    """)
    mw.stop_btn.clicked.connect(mw.stop_scan)
    main_action_layout.addWidget(mw.stop_btn)

    main_action_layout.addStretch()
    scan_layout.addLayout(main_action_layout)

    # 进度条
    mw.progress_bar = QProgressBar()
    mw.progress_bar.setMinimumHeight(25)
    mw.progress_bar.setStyleSheet("""
        QProgressBar {
            border: 2px solid grey;
            border-radius: 5px;
            text-align: center;
            height: 25px;
        }
        QProgressBar::chunk {
            background-color: #4CAF50;
            border-radius: 3px;
        }
    """)
    scan_layout.addWidget(mw.progress_bar)

    # 工作小猫加载动画：挂主窗口最上层（顶层浮层，不被进度条容器截断，鼠标穿透）
    mw.loading_cat_movie = QMovie(  # 引用挂 mw 防 GC
        str(Path(__file__).resolve().parent.parent / "assets" / "loading_cat.gif"))
    mw.loading_cat_movie.jumpToFrame(0)  # 解析首帧拿到真实尺寸（frameRect 构造后为空）
    cat_size = mw.loading_cat_movie.frameRect().size()
    if cat_size.isEmpty():  # 兜底：GIF 异常时退回原始像素，避免 0x0 不可见
        cat_size = QSize(282, 282)
    mw.loading_cat_label = SmoothMovieLabel(mw.loading_cat_movie, mw)
    mw.loading_cat_label.setFixedSize(cat_size)
    mw.loading_cat_label.hide()

    scan_group.setLayout(scan_layout)
    layout.addWidget(scan_group)

    # 扫描日志组
    log_group = QGroupBox("扫描日志")
    log_layout = QVBoxLayout()

    mw.log_text = QTextEdit()
    mw.log_text.setReadOnly(True)
    mw.log_text.setMinimumHeight(200)
    mw.log_text.setStyleSheet("""
        QTextEdit {
            background-color: #f5f5f5;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 5px;
            font-family: Consolas, Monaco, monospace;
            font-size: 12px;
        }
    """)
    log_layout.addWidget(mw.log_text)

    log_group.setLayout(log_layout)
    layout.addWidget(log_group)

    # 初始数据源为 Bangumi：应用一次约束以同步无人值守显隐（默认全匹配显示）
    apply_source_mode_constraint(mw, "Bangumi（默认）")

    mw.tab_widget.addTab(scan_tab, "📁 扫描")

