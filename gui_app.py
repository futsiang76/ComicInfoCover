#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI入口文件 - 启动PyQt6图形界面
"""

import sys

from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main():
    """主函数"""
    # 创建应用
    app = QApplication(sys.argv)

    # 设置应用属性
    app.setApplicationName("ComicInfo XML Creator")
    app.setOrganizationName("ComicInfoScratcher")

    # Qt 6 默认启用高 DPI 支持，无需额外设置

    # 创建主窗口
    window = MainWindow()
    window.show()

    # 首次启动轻引导：主窗口显示后弹出（未完成时）
    window.maybe_show_onboarding()

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()