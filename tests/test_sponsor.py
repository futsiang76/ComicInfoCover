#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""赞助通道测试 - 配置解析 / 入口显示 / 收款码路径解析"""

import os

import pytest

import config


def test_sponsor_defaults_disabled():
    """默认 sponsor_enabled=False（不显示赞助入口）"""
    settings = config.load_settings()
    assert settings["sponsor_enabled"] is False
    assert settings["sponsor_qr_path"] == ""
    assert settings["sponsor_text"] == ""
    assert settings["sponsor_url"] == ""


def test_sponsor_attr_map_registered():
    """SETTINGS_ATTR_MAP 包含全部 sponsor 字段"""
    for key in ("sponsor_enabled", "sponsor_qr_path",
                "sponsor_text", "sponsor_url"):
        assert key in config.SETTINGS_ATTR_MAP
        assert hasattr(config, config.SETTINGS_ATTR_MAP[key])


# 项目根（gui/sponsor_dialog.py 的父目录的父目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_sponsor_dialog_resolve_abs_path():
    """绝对路径原样返回"""
    from gui.sponsor_dialog import SponsorDialog
    dialog = SponsorDialog.__new__(SponsorDialog)
    assert SponsorDialog._resolve_qr_path(dialog, "C:/qr.png") == "C:/qr.png"


def test_sponsor_dialog_resolve_relative_path():
    """相对路径解析到项目根"""
    from gui.sponsor_dialog import SponsorDialog
    dialog = SponsorDialog.__new__(SponsorDialog)
    result = SponsorDialog._resolve_qr_path(dialog, "assets/sponsor_qr.png")
    assert result == os.path.join(PROJECT_ROOT, "assets/sponsor_qr.png")
    assert os.path.isabs(result)


def test_sponsor_dialog_empty_path():
    """空路径返回空串（不崩溃）"""
    from gui.sponsor_dialog import SponsorDialog
    dialog = SponsorDialog.__new__(SponsorDialog)
    assert SponsorDialog._resolve_qr_path(dialog, "") == ""


@pytest.fixture
def qapp():
    """离屏 QApplication（gui 测试用）"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_sponsor_dialog_builds_without_qr(qapp):
    """未配置收款码时对话框可构建（显示占位提示）"""
    from gui.sponsor_dialog import SponsorDialog
    old = config.SPONSOR_QR_PATH
    try:
        config.SPONSOR_QR_PATH = ""
        dlg = SponsorDialog()
        assert dlg.windowTitle() == "赞助支持"
        dlg.close()
    finally:
        config.SPONSOR_QR_PATH = old


def test_sponsor_dialog_builds_with_qr(qapp, tmp_path):
    """配置收款码图片时对话框显示图片"""
    from gui.sponsor_dialog import SponsorDialog
    # 生成一个最小 PNG（1x1 像素）
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    qr_file = tmp_path / "qr.png"
    qr_file.write_bytes(png)
    old = config.SPONSOR_QR_PATH
    try:
        config.SPONSOR_QR_PATH = str(qr_file)
        dlg = SponsorDialog()
        assert dlg.windowTitle() == "赞助支持"
        dlg.close()
    finally:
        config.SPONSOR_QR_PATH = old


def test_sponsor_dialog_collects_multiple_qr(qapp, tmp_path):
    """多收款码配置时 collect_qr_items 返回全部（名称+路径）"""
    from gui.sponsor_dialog import SponsorDialog
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    f1 = tmp_path / "a.png"
    f2 = tmp_path / "b.png"
    f1.write_bytes(png)
    f2.write_bytes(png)
    old = config.SPONSOR_QR_CODES
    try:
        config.SPONSOR_QR_CODES = [
            {"name": "支付宝", "path": str(f1)},
            {"name": "微信", "path": str(f2)},
        ]
        dlg = SponsorDialog()
        items = dlg._collect_qr_items()
        assert len(items) == 2
        assert items[0] == ("支付宝", str(f1))
        assert items[1] == ("微信", str(f2))
        dlg.close()
    finally:
        config.SPONSOR_QR_CODES = old


def test_sponsor_default_text_mentions_cat():
    """默认文案含买猫条话术"""
    from gui.sponsor_dialog import DEFAULT_SPONSOR_TEXT
    assert "买猫条" in DEFAULT_SPONSOR_TEXT


def test_sponsor_thank_mode_text_mentions_leo():
    """感谢模式文案提到 ComicInfoCover 和小猫 Leo"""
    from gui.sponsor_dialog import DEFAULT_THANK_TEXT
    assert "ComicInfoCover" in DEFAULT_THANK_TEXT
    assert "Leo" in DEFAULT_THANK_TEXT


def test_sponsor_thank_mode_builds(qapp):
    """感谢模式对话框可构建（标题=感谢使用）"""
    from gui.sponsor_dialog import SponsorDialog
    dlg = SponsorDialog(thank_mode=True)
    assert dlg.windowTitle() == "感谢使用"
    dlg.close()
