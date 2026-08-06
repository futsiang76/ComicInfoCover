"""项目根 conftest — pytest 全局配置"""
import os


def pytest_configure(config):
    """在测试收集前设置 offscreen 模式"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
