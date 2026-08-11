#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口模块 - PySide6 GUI主窗口
"""

import os
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, Qt, QSettings, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QFileDialog,
                             QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QMainWindow, QMenu, QMessageBox, QProgressBar,
                             QPushButton, QRadioButton, QTableWidget,
                             QTableWidgetItem, QTabWidget, QTextEdit,
                             QVBoxLayout, QWidget)

import markdown

import config
from config import AUTO_TURBO_MATCH, MODE_SKIP_XMLEXIST


def _trim_compare_dicts(old_dict: dict, new_dict: dict) -> bool:
    """递归比较两个字典，对所有字符串值做strip后比较，返回True表示有差异"""
    all_keys = set(old_dict.keys()) | set(new_dict.keys())
    for k in all_keys:
        old_v = old_dict.get(k)
        new_v = new_dict.get(k)
        if isinstance(old_v, dict) and isinstance(new_v, dict):
            if _trim_compare_dicts(old_v, new_v):
                return True
        elif isinstance(old_v, dict) or isinstance(new_v, dict):
            return True
        else:
            if str(old_v).strip() != str(new_v).strip():
                return True
    return False

from .scan_thread import ScanThread
from .edit_dialog import EditDialog
from .title_edit_dialog import TitleEditDialog
from .scan_tab import build_scan_tab
from .results_tab import build_results_tab
from .scan_controller import (start_scan, check_xml_before_scan, stop_scan,
                              on_progress_updated, on_scan_completed, on_error_occurred)
from .dialogs import show_xml_exists_dialog
from .results_table import update_results_table
from .save_handler import save_changes
from .xml_editor import open_xml_editor, on_edit_xml_clicked
from .edit_controller import (edit_row, on_results_double_clicked,
                              edit_selected)


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.scan_results = []
        self.scan_thread = None
        self.locked_files = set()
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("ComicInfo XML Creator")
        self.setMinimumSize(1200, 800)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # 创建标签页
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # 创建标签页（扫描、结果，配置已改为右上角齿轮）
        self.create_scan_tab()
        self.create_results_tab()

        # 齿轮菜单按钮：恢复原 QPushButton ⚙ 扁平透明观感（可下拉），点击手动弹出菜单
        gear_btn = QPushButton("\u2699")
        gear_btn.setFixedSize(26, 22)
        gear_btn.setToolTip("菜单")
        gear_btn.setFlat(True)
        gear_btn.setFont(QFont("Segoe UI Symbol", 16))
        gear_btn.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0 6px 0 0; margin: 0; } QPushButton:hover { background: #e0e0e0; border-radius: 4px; }")
        gear_menu = QMenu(gear_btn)
        gear_menu.addAction("应用设置", self._open_settings)
        gear_menu.addAction("法律声明", lambda: self._show_doc_dialog("法律声明", "法律声明.md"))
        gear_menu.addAction("使用说明", lambda: self._show_doc_dialog("使用说明", "使用说明.md"))
        gear_menu.addAction("版本", self._show_about_dialog)
        gear_menu.addAction("检查更新", self._check_update_placeholder)
        if config.SPONSOR_ENABLED:
            gear_menu.addAction("赞助支持", self._show_sponsor_dialog)
        self._gear_menu = gear_menu
        self._gear_btn = gear_btn
        gear_btn.clicked.connect(lambda: self._popup_gear_menu(gear_btn, gear_menu))
        self.tab_widget.setCornerWidget(gear_btn)
        
        # 启动路径：记住上次路径=开 → 上次路径 > 默认目录；关 → 仅默认目录；均无 → 提示选择
        settings = QSettings("ComicInfoScratcher", "ComicInfoXMLCreator")
        initial_path = self._initial_manga_path(settings)
        if initial_path:
            self.path_edit.setText(initial_path)
        else:
            self.path_edit.setPlaceholderText("请选择漫画库目录")

    def _open_settings(self):
        """打开应用设置对话框"""
        from gui.settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

    def _show_sponsor_dialog(self):
        """打开赞助支持对话框"""
        from gui.sponsor_dialog import SponsorDialog
        SponsorDialog(self).exec()

    def _gear_menu_popup_pos(self, btn, menu) -> QPoint:
        """计算菜单弹出全局坐标：默认对齐按钮右缘向下弹出，超出窗口右缘则整体左移

        Returns:
            QPoint: 菜单左上角全局坐标（保证菜单右缘 ≤ 窗口右缘）
        """
        menu_width = menu.sizeHint().width()
        btn_global = btn.mapToGlobal(btn.rect().topLeft())
        window_right = self.mapToGlobal(self.rect().topRight()).x()
        x = btn_global.x() + btn.width() - menu_width
        if x + menu_width > window_right:
            x = window_right - menu_width
        x = max(x, 0)  # 窗口极窄时防止负坐标
        y = btn_global.y() + btn.height()
        return QPoint(x, y)

    def _popup_gear_menu(self, btn, menu):
        """齿轮按钮点击：手动指定菜单弹出位置（菜单右缘不超出主窗口右边界）"""
        menu.exec(self._gear_menu_popup_pos(btn, menu))

    _MD_CSS = """
    body { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; font-size: 13px; line-height: 1.6; color: #222; }
    h1 { font-size: 20px; font-weight: bold; margin: 12px 0 8px; }
    h2 { font-size: 17px; font-weight: bold; margin: 10px 0 6px; }
    h3 { font-size: 15px; font-weight: bold; margin: 8px 0 4px; }
    p { margin: 6px 0; }
    strong { font-weight: bold; }
    ul, ol { margin: 6px 0; padding-left: 24px; }
    blockquote { border-left: 3px solid #ccc; margin: 6px 0; padding-left: 12px; color: #555; }
    a { color: #1a73e8; }
    """

    def _render_markdown(self, content: str) -> str:
        """markdown 文本 → 带基础样式的 HTML（标题大字号、正文常规、strong 加粗）"""
        body = markdown.markdown(content, extensions=["extra"])
        return f"<html><head><style>{self._MD_CSS}</style></head><body>{body}</body></html>"

    def _doc_path(self, filename: str) -> str:
        """返回 docs/ 目录下文档的绝对路径（项目根 docs/）"""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, "docs", filename)

    def _show_doc_dialog(self, title: str, filename: str):
        """模态对话框显示 docs/ 下 markdown 文档（只读 + 滚动）；文件缺失时优雅提示"""
        doc_path = self._doc_path(filename)
        if not os.path.isfile(doc_path):
            QMessageBox.information(self, title, f"文档文件不存在：{doc_path}")
            return
        try:
            with open(doc_path, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            QMessageBox.warning(self, title, f"读取文档失败：{e}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(640, 520)
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        # markdown → HTML 渲染：标题大字号加粗、正文常规，文档观感而非源码
        text_edit.setHtml(self._render_markdown(content))
        layout.addWidget(text_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _show_about_dialog(self):
        """版本/about 对话框：应用名 + 版本 + 版权行 + GitHub 链接"""
        about_text = (
            f"<h3>{config.APP_NAME} {config.APP_VERSION}</h3>"
            "<p>本地漫画库 ComicInfo.xml 批量整理工具</p>"
            "<p>© 2026 futsiang76. All rights reserved.</p>"
            '<p><a href="https://github.com/futsiang76/ComicInfoCover">'
            "GitHub: futsiang76/ComicInfoCover</a></p>"
        )
        box = QMessageBox(self)
        box.setWindowTitle("版本")
        box.setIcon(QMessageBox.Icon.Information)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(about_text)
        label = box.findChild(QLabel)
        if label is not None:
            label.setOpenExternalLinks(True)
        box.exec()

    def _check_update_placeholder(self):
        """检查更新占位：功能尚未上线，点击提示"""
        QMessageBox.information(self, "检查更新",
                                "检查更新功能即将上线，敬请期待。")

    def _initial_manga_path(self, settings) -> str:
        """计算启动时的漫画根目录（为空则界面提示选择，不落任何写死路径）

        Args:
            settings: QSettings 实例（组织/应用名已定）

        Returns:
            str: 启动路径；无可用路径时返回空字符串
        """
        if config.REMEMBER_LAST_PATH:
            last_path = settings.value("last_manga_path", "")
            if last_path:
                return str(last_path).strip()
        return (config.DEFAULT_MANGA_DIR or "").strip()

    def create_scan_tab(self):
        """创建扫描标签页"""
        build_scan_tab(self, self.tab_widget)

    def create_results_tab(self):
        """创建结果标签页"""
        build_results_tab(self, self.tab_widget)

    def browse_path(self):
        """浏览路径：保存到 QSettings；默认目录未配置时首次引导写入 config"""
        current_path = self.path_edit.text().strip() or config.DEFAULT_MANGA_DIR or ""
        path = QFileDialog.getExistingDirectory(self, "选择漫画根目录", current_path)
        if path:
            self.path_edit.setText(path)
            # 保存路径到 QSettings（记住上次路径依赖）
            settings = QSettings("ComicInfoScratcher", "ComicInfoXMLCreator")
            settings.setValue("last_manga_path", path)
            # 首次引导：默认目录为空时同步写入 config，无记忆也能回到该目录
            if not config.DEFAULT_MANGA_DIR:
                config.save_settings({"default_manga_dir": path})


    def start_scan(self):
        start_scan(self)

    def check_xml_before_scan(self, manga_root: str) -> tuple:
        return check_xml_before_scan(self, manga_root)

    def show_xml_exists_dialog(self, stats: dict) -> str:
        return show_xml_exists_dialog(self, stats)

    def stop_scan(self):
        stop_scan(self)

    def on_progress_updated(self, progress: int, message: str):
        on_progress_updated(self, progress, message)

    def on_scan_completed(self, results: List[Dict]):
        on_scan_completed(self, results)

    def on_error_occurred(self, error: str):
        on_error_occurred(self, error)

    def update_results_table(self):
        update_results_table(self)

    def edit_row(self, row: int):
        edit_row(self, row)

    def open_xml_editor(self, xml_path: str):
        open_xml_editor(self, xml_path)

    def on_edit_xml_clicked(self):
        on_edit_xml_clicked(self)

    def on_results_double_clicked(self, row: int, column: int):
        on_results_double_clicked(self, row, column)

    def edit_selected(self):
        edit_selected(self)

    def save_changes(self, show_result: bool = True):
        save_changes(self, show_result)


    def cancel_to_scan(self):
        """取消并返回扫描页"""
        self.tab_widget.setCurrentIndex(0)
