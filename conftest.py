"""项目根 conftest — pytest 全局配置"""
import os

import pytest


def pytest_configure(config):
    """在测试收集前设置 offscreen 模式"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolate_crop_memory(tmp_path, monkeypatch):
    """隔离裁剪记忆：测试期间 CropDialog 用临时记忆文件，避免污染真实 memory/"""
    from processors.crop_memory import CropMemory

    mem_file = tmp_path / "crop_memory.json"
    monkeypatch.setattr("gui.crop_dialog.CropMemory",
                        lambda: CropMemory(memory_file=str(mem_file)))


@pytest.fixture(autouse=True)
def _isolate_user_config(tmp_path, monkeypatch):
    """隔离用户设置：user_config.json 指向临时文件，config 模块属性每次重置为默认

    避免测试（如 _on_accept 写入）污染项目根的真实 user_config.json。
    """
    import config

    fake_path = str(tmp_path / "user_config.json")
    monkeypatch.setattr(config, "USER_CONFIG_PATH", fake_path)
    config.apply_settings(config.DEFAULT_SETTINGS)
    yield
    config.apply_settings(config.DEFAULT_SETTINGS)
