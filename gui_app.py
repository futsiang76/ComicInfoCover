#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI入口文件 - 启动PySide6图形界面
"""

import sys

from PySide6.QtWidgets import QApplication

import config
from gui.main_window import MainWindow
from gui.onboarding_dialog import OnboardingDialog


def _run_onboarding_if_needed() -> bool:
    """首次启动未完成时，先弹轻引导（此时无主窗体）

    引导填写的默认目录已写入 config（default_manga_dir）与 QSettings
    （last_manga_path），主窗体创建时天然取到该目录，无需二次同步。

    Returns:
        bool: 是否弹出了轻引导对话框
    """
    if config.FIRST_RUN_DONE:
        return False
    OnboardingDialog().exec()
    return True


def main():
    """主函数"""
    # 创建应用
    app = QApplication(sys.argv)

    # 设置应用属性
    app.setApplicationName("ComicInfo XML Creator")
    app.setOrganizationName("ComicInfoScratcher")

    # Qt 6 默认启用高 DPI 支持，无需额外设置

    # 引导先于主窗体：未完成时先弹引导，填完确认后才创建主窗体
    _run_onboarding_if_needed()

    # 创建主窗口（引导完成后默认目录已就绪）
    window = MainWindow()
    window.show()

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()