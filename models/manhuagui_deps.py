#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manhuagui 抓取依赖检查与自动安装（playwright + chromium）

首次使用 manhuagui 源时调用 ensure_manhuagui_deps：
- 已装        → 返回 True
- 未装        → 弹窗确认 → 后台线程安装（pip install playwright → playwright install chromium）
- 安装成功    → True
- 用户取消/失败 → 弹窗报错并返回 False（不影响 Bangumi 源）
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QProgressDialog

# 安装子进程超时（秒），chromium 首次下载较慢
_INSTALL_TIMEOUT = 1800


# ----------------------------------------------------------------------
# 依赖检查
# ----------------------------------------------------------------------
def _playwright_importable() -> bool:
    """检查 playwright 包是否可导入"""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _chromium_cache_dir() -> Path:
    """playwright 浏览器缓存目录（跨平台）"""
    if sys.platform.startswith("win"):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "ms-playwright"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ms-playwright"


def _chromium_installed() -> bool:
    """检查 chromium 浏览器是否已安装（缓存目录下存在 chromium-* 目录）"""
    cache_dir = _chromium_cache_dir()
    if not cache_dir.exists():
        return False
    return any(p.name.startswith("chromium") for p in cache_dir.iterdir())


def _deps_ready() -> bool:
    """检查 playwright 包 + chromium 浏览器是否就绪"""
    return _playwright_importable() and _chromium_installed()


# ----------------------------------------------------------------------
# 安装步骤
# ----------------------------------------------------------------------
def _run_cmd(args: List[str]) -> None:
    """执行子进程命令，失败抛 RuntimeError 携带错误摘要"""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=_INSTALL_TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("安装超时，请手动执行安装命令") from e
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RuntimeError(f"命令 {' '.join(args)} 失败: {detail}")


def _pip_install_playwright() -> None:
    """安装 playwright 包；PEP 668 环境（externally-managed）降级 --break-system-packages"""
    try:
        _run_cmd([sys.executable, "-m", "pip", "install", "playwright"])
    except RuntimeError as e:
        if "externally-managed" in str(e):
            _run_cmd([sys.executable, "-m", "pip", "install",
                      "--break-system-packages", "playwright"])
        else:
            raise


def _install_chromium() -> None:
    """下载安装 chromium 浏览器"""
    _run_cmd([sys.executable, "-m", "playwright", "install", "chromium"])


def _install_sync() -> bool:
    """无 GUI 父窗口时的同步安装（打印进度），返回是否成功"""
    try:
        _pip_install_playwright()
        print("正在下载 chromium 浏览器（约150MB，耗时较长）...")
        _install_chromium()
        return True
    except Exception as e:
        print(f"🔴 manhuagui 依赖安装失败: {e}")
        return False


class _DepsInstallThread(QThread):
    """后台安装线程：pip install playwright → playwright install chromium"""

    progress_updated = pyqtSignal(str)   # 进度提示（更新进度弹窗文案）
    install_finished = pyqtSignal(bool, str)  # (是否成功, 消息)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ok = False
        self.message = ""

    def run(self) -> None:
        try:
            self.progress_updated.emit("正在安装 playwright 包...")
            _pip_install_playwright()
            self.progress_updated.emit("正在下载 chromium 浏览器（约150MB，耗时较长）...")
            _install_chromium()
            self.ok = True
            self.message = "manhuagui 依赖安装完成，可正常使用 manhuagui 数据源"
        except Exception as e:
            self.message = str(e)
        self.install_finished.emit(self.ok, self.message)


def ensure_manhuagui_deps(parent: Optional[QProgressDialog] = None) -> bool:
    """检查并安装 manhuagui 抓取所需依赖（playwright + chromium）

    已装 → 直接返回 True
    未装 → 弹窗确认 → 后台线程安装（进度弹窗反馈）
          → 成功 True / 用户取消或失败弹窗报错返回 False（不影响 Bangumi 源）

    Args:
        parent: 父窗口（GUI 弹窗用）；为 None 时直接同步安装、不弹窗

    Returns:
        bool: 依赖就绪返回 True，否则返回 False
    """
    if _deps_ready():
        return True

    if parent is None:
        return _install_sync()

    reply = QMessageBox.question(
        parent,
        "安装 manhuagui 依赖",
        "manhuagui 数据源需要 playwright 及 chromium 浏览器"
        "（首次安装需下载约150MB）。\n\n是否现在自动安装？",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return False

    # 不确定进度弹窗（后台线程安装时提供视觉反馈）
    dialog = QProgressDialog("正在准备安装...", "", 0, 0, parent)
    dialog.setWindowTitle("安装 manhuagui 依赖")
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setCancelButton(None)
    dialog.setMinimumDuration(0)
    dialog.setValue(0)

    thread = _DepsInstallThread(parent)
    thread.progress_updated.connect(dialog.setLabelText)

    def _on_finished(ok: bool, message: str) -> None:
        dialog.close()
        if not ok:
            QMessageBox.critical(
                parent,
                "安装失败",
                f"manhuagui 依赖安装失败（不影响 Bangumi 源）：\n{message}\n\n"
                "可手动执行：pip install playwright && playwright install chromium",
            )

    thread.install_finished.connect(_on_finished)
    thread.start()
    dialog.exec()
    thread.wait()
    return thread.ok
