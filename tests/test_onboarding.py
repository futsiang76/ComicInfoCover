#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""首次启动轻引导测试：启动流程（引导先于主窗体）+ 对话框行为 + 配置持久化

conftest._isolate_user_config 已把 user_config.json 指向临时文件并重置
config 模块属性为默认值（first_run_done=False），不会污染真实配置。
"""
import json

import config
import gui_app
from gui.onboarding_dialog import HINT_TEXT, OnboardingDialog


def _patch_dialog(monkeypatch):
    """替换 gui_app.OnboardingDialog 为记录型假类，避免真实模态 exec 阻塞"""
    calls = []

    class FakeDialog:
        def __init__(self):
            calls.append(True)

        def exec(self):
            return 1

    monkeypatch.setattr("gui_app.OnboardingDialog", FakeDialog)
    return calls


def _patch_qsettings(monkeypatch):
    """替换 onboarding_dialog.QSettings 为记录型假类，避免写真实配置"""
    saved = {}

    class FakeSettings:
        def __init__(self, org, app_name):
            pass

        def setValue(self, key, val):
            saved[key] = val

    monkeypatch.setattr("gui.onboarding_dialog.QSettings", FakeSettings)
    return saved


def test_onboarding_shown_when_first_run_not_done(monkeypatch):
    """first_run_done 缺失/False → 先弹轻引导（主窗体创建前）"""
    config.FIRST_RUN_DONE = False
    calls = _patch_dialog(monkeypatch)
    assert gui_app._run_onboarding_if_needed() is True
    assert len(calls) == 1


def test_onboarding_skipped_when_first_run_done(monkeypatch):
    """first_run_done=True → 直接进入主窗体，不弹引导"""
    config.FIRST_RUN_DONE = True
    calls = _patch_dialog(monkeypatch)
    assert gui_app._run_onboarding_if_needed() is False
    assert calls == []


def test_onboarding_prefills_default_dir(qtbot):
    """默认目录已有值 → QLineEdit 预填"""
    config.DEFAULT_MANGA_DIR = "/some/manga/dir"
    dialog = OnboardingDialog()
    qtbot.addWidget(dialog)
    assert dialog.dir_edit.text() == "/some/manga/dir"


def test_onboarding_placeholder_when_no_dir(qtbot):
    """默认目录为空 → placeholder 提示选择"""
    config.DEFAULT_MANGA_DIR = ""
    dialog = OnboardingDialog()
    qtbot.addWidget(dialog)
    assert dialog.dir_edit.text() == ""
    assert dialog.dir_edit.placeholderText() == "请选择你的漫画库目录"


def test_onboarding_hint_text_exact(qtbot):
    """提示文字逐字匹配"""
    dialog = OnboardingDialog()
    qtbot.addWidget(dialog)
    assert dialog.hint_label.text() == HINT_TEXT
    assert HINT_TEXT == "扫描时需联网；大陆镜像已内置；部分源需要科学。"


def test_onboarding_start_use_saves_config(qtbot, monkeypatch):
    """点击开始使用 → 写入 default_manga_dir + first_run_done=true 并关闭"""
    _patch_qsettings(monkeypatch)
    config.DEFAULT_MANGA_DIR = ""
    dialog = OnboardingDialog()
    qtbot.addWidget(dialog)
    dialog.dir_edit.setText("/chosen/dir")
    dialog.start_btn.click()

    assert dialog.result() == 1  # QDialog.Accepted
    assert config.FIRST_RUN_DONE is True
    assert config.DEFAULT_MANGA_DIR == "/chosen/dir"
    with open(config.USER_CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert data["first_run_done"] is True
    assert data["default_manga_dir"] == "/chosen/dir"


def test_onboarding_start_use_overrides_last_path(qtbot, monkeypatch):
    """填了目录 → 同时写 QSettings last_manga_path，覆盖残留旧路径"""
    saved = _patch_qsettings(monkeypatch)
    dialog = OnboardingDialog()
    qtbot.addWidget(dialog)
    dialog.dir_edit.setText("/new/manga")
    dialog.start_btn.click()

    assert saved.get("last_manga_path") == "/new/manga"


def test_onboarding_start_without_dir(qtbot, monkeypatch):
    """不选目录也能开始使用（不写 last_manga_path，不强制阻塞）"""
    saved = _patch_qsettings(monkeypatch)
    config.DEFAULT_MANGA_DIR = ""
    dialog = OnboardingDialog()
    qtbot.addWidget(dialog)
    dialog.start_btn.click()

    assert dialog.result() == 1
    assert config.FIRST_RUN_DONE is True
    assert config.DEFAULT_MANGA_DIR == ""
    assert saved == {}


def test_onboarding_second_run_not_shown_via_config(tmp_path, monkeypatch):
    """模拟重启：完成后再启动，user_config 已含 first_run_done=true 不弹引导"""
    config.USER_CONFIG_PATH = str(tmp_path / "user_config.json")
    config.save_settings({"default_manga_dir": "/manga", "first_run_done": True})

    # 模拟新进程读取配置：模块属性取自已写文件的值
    config.FIRST_RUN_DONE = config.load_settings()["first_run_done"]
    calls = _patch_dialog(monkeypatch)
    assert gui_app._run_onboarding_if_needed() is False
    assert calls == []
