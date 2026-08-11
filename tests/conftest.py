"""pytest-qt 共享 fixture — ComicInfoScratcher GUI 自动化测试"""
import os
import tempfile
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings


@pytest.fixture(scope="session")
def qapp_args():
    """传给 QApplication 的参数"""
    return ["ComicInfoScratcherTest"]


@pytest.fixture
def app(qtbot, monkeypatch):
    """创建 MainWindow 实例，qtbot 接管事件循环，扫描线程不启动"""
    from gui.main_window import MainWindow

    # 隔离 QSettings：不让测试读到真实用户配置（last_manga_path 等）
    # 单元测试不发起真实 IP 检测网络请求（source_detect 默认开启）
    monkeypatch.setattr("gui.source_detect.AUTO_GEO_DETECT", False)
    monkeypatch.setattr(
        "gui.main_window.QSettings",
        lambda org, app_name: type(
            "FakeSettings", (), {"value": lambda self, key, default=None: default,
                                 "setValue": lambda self, key, val: None,
                                 "clear": lambda self: None}
        )(),
    )
    monkeypatch.setattr("gui.scan_thread.ScanThread.start", lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close()


@pytest.fixture
def tmp_manga_dir():
    """临时漫画根目录"""
    with tempfile.TemporaryDirectory(prefix="test_manga_") as tmpdir:
        yield tmpdir
