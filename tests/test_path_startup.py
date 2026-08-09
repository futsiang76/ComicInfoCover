"""默认漫画目录 + 记住上次路径 — 启动取值逻辑测试

覆盖：记住上次路径开/关的取值顺序、默认目录为空时的界面提示、
设置对话框中两个新控件的默认值与保存。
"""
import config


def _build_window(qtbot, monkeypatch, *, remember: bool, default_dir: str,
                  last_path: str):
    """按指定配置构建 MainWindow（隔离 QSettings 与 config 模块属性）"""
    monkeypatch.setattr(config, "REMEMBER_LAST_PATH", remember)
    monkeypatch.setattr(config, "DEFAULT_MANGA_DIR", default_dir)

    class FakeSettings:
        def value(self, key, default=None):
            return last_path if key == "last_manga_path" else default

        def setValue(self, key, val):
            pass

    monkeypatch.setattr("gui.main_window.QSettings",
                        lambda org, app_name: FakeSettings())

    from gui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_remember_on_prefers_last_path(qtbot, monkeypatch):
    """记住上次路径=开：优先取 QSettings 上次路径，其次默认目录"""
    window = _build_window(qtbot, monkeypatch, remember=True,
                           default_dir="/default/manga", last_path="/last/manga")
    assert window.path_edit.text() == "/last/manga"


def test_remember_on_falls_back_to_default_dir(qtbot, monkeypatch):
    """记住上次路径=开 + 无上次路径：落到配置默认目录"""
    window = _build_window(qtbot, monkeypatch, remember=True,
                           default_dir="/default/manga", last_path="")
    assert window.path_edit.text() == "/default/manga"


def test_remember_off_ignores_last_path(qtbot, monkeypatch):
    """记住上次路径=关：忽略 QSettings 上次路径，直接用默认目录"""
    window = _build_window(qtbot, monkeypatch, remember=False,
                           default_dir="/default/manga", last_path="/last/manga")
    assert window.path_edit.text() == "/default/manga"


def test_empty_path_shows_prompt(qtbot, monkeypatch):
    """默认目录为空：不落任何路径，界面提示「请选择漫画库目录」"""
    window = _build_window(qtbot, monkeypatch, remember=False,
                           default_dir="", last_path="")
    assert window.path_edit.text() == ""
    assert window.path_edit.placeholderText() == "请选择漫画库目录"


def test_settings_dialog_has_new_controls(qtbot):
    """设置对话框含默认漫画目录行 + 记住上次路径开关（默认值取自 config）"""
    from gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    assert hasattr(dialog, "default_dir_edit")
    assert hasattr(dialog, "remember_last_path_switch")
    assert dialog.default_dir_edit.text() == config.DEFAULT_MANGA_DIR
    assert dialog.remember_last_path_switch.isChecked() == config.REMEMBER_LAST_PATH


def test_settings_dialog_save_new_fields(qtbot, monkeypatch, tmp_path):
    """保存后 DEFAULT_MANGA_DIR / REMEMBER_LAST_PATH 同步 config 并持久化"""
    monkeypatch.setattr(config, "USER_CONFIG_PATH", str(tmp_path / "user_config.json"))

    from gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.default_dir_edit.setText("/manga/default")
    dialog.remember_last_path_switch.setChecked(False)
    dialog._on_accept()

    assert config.DEFAULT_MANGA_DIR == "/manga/default"
    assert config.REMEMBER_LAST_PATH is False
    settings = config.load_settings()
    assert settings["default_manga_dir"] == "/manga/default"
    assert settings["remember_last_path"] is False
