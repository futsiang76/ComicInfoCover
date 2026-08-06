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
