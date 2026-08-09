"""配置/齿轮对话框测试"""
import config

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QDialog

from gui.settings_dialog import SettingsDialog, SwitchButton


def test_gear_button_connected(app):
    """齿轮按钮存在且挂有菜单（点击弹出五项下拉菜单）"""
    gear = app.tab_widget.cornerWidget()
    assert gear is not None
    assert gear.toolTip() == "菜单"
    menu = app._gear_menu
    assert menu is not None
    assert [a.text() for a in menu.actions()] == [
        "应用设置", "法律声明", "使用说明", "版本", "检查更新"]


def test_settings_defaults(qtbot):
    """默认值显示正确"""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.fuzz_spin.value() == config.FUZZ_THRESHOLD
    assert dialog.author_spin.value() == config.AUTHOR_MATCH_THRESHOLD
    assert dialog.timeout_spin.value() == config.TIMEOUT
    assert dialog.retries_spin.value() == config.MAX_RETRIES


def test_settings_modify_and_save(qtbot):
    """修改配置后 _on_accept 写入 config 模块"""
    original_fuzz = config.FUZZ_THRESHOLD
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.fuzz_spin.setValue(99)
    dialog.author_spin.setValue(88)
    dialog._on_accept()

    assert config.FUZZ_THRESHOLD == 99
    assert config.AUTHOR_MATCH_THRESHOLD == 88

    # 还原
    config.FUZZ_THRESHOLD = original_fuzz
    config.AUTHOR_MATCH_THRESHOLD = 70


def test_settings_crop_memory_switch_default(qtbot):
    """封面裁剪定位记忆开关存在且默认勾选（config 默认 True）"""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    assert hasattr(dialog, "crop_memory_switch")
    assert dialog.crop_memory_switch.isChecked() == config.CROP_MEMORY_ENABLED
    assert dialog.crop_memory_switch.isChecked() is True


def test_settings_crop_memory_switch_save(qtbot):
    """关闭开关后 _on_accept 写入 config.CROP_MEMORY_ENABLED"""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.crop_memory_switch.setChecked(False)
    dialog._on_accept()
    assert config.CROP_MEMORY_ENABLED is False

    # 还原
    config.CROP_MEMORY_ENABLED = True


def test_switch_button_size(qtbot):
    """开关固定 48×20，高度减小后自绘圆钮仍居中"""
    switch = SwitchButton()
    qtbot.addWidget(switch)
    switch.show()

    assert switch.width() == 48
    assert switch.height() == 20


def test_settings_inputs_aligned(qtbot):
    """各分组输入控件（Key 框/下拉/SpinBox/开关）左边缘对齐同一竖线"""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    controls = [
        dialog.bangumi_edit,
        dialog.comicvine_edit,
        dialog.fuzz_spin,
        dialog.author_spin,
        dialog.timeout_spin,
        dialog.retries_spin,
        dialog.save_format_combo,
        dialog.delete_after_convert_switch,
        dialog.default_dir_edit,
        dialog.remember_last_path_switch,
        dialog.crop_memory_switch,
    ]
    xs = {w.mapTo(dialog, QPoint(0, 0)).x() for w in controls}
    assert len(xs) == 1
