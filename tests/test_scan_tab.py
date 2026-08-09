"""扫描面板 UI + 交互测试"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QButtonGroup, QLabel, QLineEdit, QPushButton, QTextEdit

from config import (SOURCE_BANGUMI_MIRROR_TEXT, SOURCE_BANGUMI_TEXT,
                    SOURCE_COMICVINE_TEXT, SOURCE_MANHUAGUI_TEXT)


def test_mode_radio_buttons_exist(app):
    assert isinstance(app.mode_group, QButtonGroup)
    assert len(app.mode_group.buttons()) == 4


def test_path_input_exists(app):
    assert isinstance(app.path_edit, QLineEdit)


def test_scan_buttons_exist(app):
    assert isinstance(app.scan_btn, QPushButton)
    assert isinstance(app.stop_btn, QPushButton)
    assert app.scan_btn.text() == "🚀 开始扫描"
    assert app.stop_btn.text() == "⏹️ 停止扫描"


def test_edit_xml_button_exists(app):
    assert isinstance(app.edit_xml_btn, QPushButton)
    assert "编辑XML" in app.edit_xml_btn.text()
    assert app.edit_xml_btn.isEnabled()


def test_log_area_exists(app):
    assert isinstance(app.log_text, QTextEdit)
    assert app.log_text.isReadOnly()


def test_default_path_has_no_hardcoded_manga(app):
    """启动路径不再写死 H:/Download/Manga（漫友无该目录也能正常启动）"""
    assert "H:/Download/Manga" not in app.path_edit.text()


def test_loading_cat_created(app):
    """工作小猫加载动画：SmoothMovieLabel 平滑缩放、尺寸自适应 GIF 原始帧、挂主窗口最上层（不被进度条截断）、初始隐藏、GIF 有效"""
    from PyQt6.QtGui import QMovie

    from gui.utils import SmoothMovieLabel

    assert hasattr(app, "loading_cat_label")
    assert isinstance(app.loading_cat_label, SmoothMovieLabel)
    # 尺寸自适应 GIF 原始帧尺寸（当前 loading_cat.gif 为 250x169，缩放交给 _on_frame 平滑处理）
    assert app.loading_cat_label.size() == app.loading_cat_movie.frameRect().size()
    assert not app.loading_cat_label.hasScaledContents()  # 帧缩放由 SmoothMovieLabel 平滑处理
    assert app.loading_cat_label.parent() is app
    assert app.loading_cat_label.parent() is not app.progress_bar
    assert not app.loading_cat_label.isVisible()
    assert app.loading_cat_movie.isValid()
    assert app.loading_cat_movie.state() == QMovie.MovieState.NotRunning


def test_loading_cat_start_stop(app):
    """工作小猫动画启动/停止：可见性 + 播放状态切换（幂等）"""
    from PyQt6.QtGui import QMovie

    from gui.utils import start_loading_cat, stop_loading_cat

    start_loading_cat(app)
    assert app.loading_cat_label.isVisible()
    assert app.loading_cat_movie.state() == QMovie.MovieState.Running

    stop_loading_cat(app)
    assert not app.loading_cat_label.isVisible()
    assert app.loading_cat_movie.state() == QMovie.MovieState.NotRunning


def test_loading_cat_frame_smooth_scaled(app, monkeypatch):
    """帧渲染走平滑缩放：_on_frame 以 SmoothTransformation 缩放到 label 物理尺寸，结果 setPixmap 非空"""
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QPixmap

    calls = []
    orig_scaled = QPixmap.scaled

    def fake_scaled(self, *args):
        calls.append(args)
        return orig_scaled(self, *args)

    monkeypatch.setattr(QPixmap, "scaled", fake_scaled)

    app.loading_cat_label._on_frame(0)

    assert calls, "帧渲染应调用 QPixmap.scaled"
    assert all(args[2] == Qt.TransformationMode.SmoothTransformation for args in calls)
    pix = app.loading_cat_label.pixmap()
    assert pix is not None
    assert not pix.isNull()
    dpr = app.loading_cat_label.devicePixelRatioF()
    label_size = app.loading_cat_label.size()
    expected = QSize(round(label_size.width() * dpr), round(label_size.height() * dpr))
    assert pix.size() == expected


def test_loading_cat_positioned_on_main_window(app):
    """小猫启动后左下角对齐进度条左下角：左边缘、底边缘均与进度条平齐"""
    from PyQt6.QtCore import QPoint

    from gui.utils import start_loading_cat, stop_loading_cat

    start_loading_cat(app)
    assert app.loading_cat_label.parent() is app
    progress_top_left = app.progress_bar.mapTo(app, QPoint(0, 0))
    cat_pos = app.loading_cat_label.pos()
    # 左边缘对齐进度条左边缘
    assert cat_pos.x() == progress_top_left.x()
    # 底部对齐进度条底部（label 底边 == 进度条底边）
    assert cat_pos.y() + app.loading_cat_label.height() == progress_top_left.y() + app.progress_bar.height()
    stop_loading_cat(app)


def test_source_constraint_manhuagui(app):
    """manhuagui 源：固定全匹配 + 隐藏补漏/修正/手动匹配"""
    from gui.scan_tab import _on_source_changed

    _on_source_changed(app, SOURCE_MANHUAGUI_TEXT)
    assert app.selected_source == SOURCE_MANHUAGUI_TEXT
    assert app._mode_radios[0].isChecked()
    assert app._mode_radios[0].isVisible()
    for val in (1, 2, 3):
        assert not app._mode_radios[val].isVisible()
        assert not app._mode_radios[val].isEnabled()
    assert not app.auto_turbo_check.isVisible()
    assert not app.auto_turbo_check.isChecked()


def test_source_constraint_comicvine(app):
    """ComicVine 源：同样固定全匹配 + 隐藏受限控件"""
    from gui.scan_tab import _on_source_changed

    _on_source_changed(app, "ComicVine")
    assert app._mode_radios[0].isChecked()
    for val in (1, 2, 3):
        assert not app._mode_radios[val].isVisible()
    assert not app.auto_turbo_check.isVisible()


def test_source_switch_back_to_bangumi_restores(app):
    """切回 Bangumi：模式与无人值守恢复（官方/镜像均属非受限源）"""
    from gui.scan_tab import _on_source_changed

    _on_source_changed(app, SOURCE_MANHUAGUI_TEXT)
    _on_source_changed(app, SOURCE_BANGUMI_TEXT)
    assert app.selected_source == SOURCE_BANGUMI_TEXT
    for val in (0, 1, 2, 3):
        assert app._mode_radios[val].isVisible()
    assert app.auto_turbo_check.isVisible()


def test_scan_controls_locked_during_scan(app):
    """扫描期间锁定模式选择与数据源，结束后恢复"""
    from gui.scan_controller import _lock_controls, _unlock_controls

    _lock_controls(app)
    for btn in app.mode_group.buttons():
        assert not btn.isEnabled()
    assert not app.source_combo.isEnabled()

    _unlock_controls(app)
    for btn in app.mode_group.buttons():
        assert btn.isEnabled()
    assert app.source_combo.isEnabled()


class TestGeoDetectDefaultSource:
    """IP 检测完成 → 默认数据源联动（测试不发起真实网络请求）"""

    def test_cn_detected_switches_to_mirror(self, app):
        """检测大陆 → 默认切「Bangumi 大陆镜像」"""
        from gui import source_detect

        source_detect._on_geo_detected(app, True)
        assert app.source_combo.currentText() == SOURCE_BANGUMI_MIRROR_TEXT
        assert app.selected_source == SOURCE_BANGUMI_MIRROR_TEXT

    def test_non_cn_keeps_official(self, app):
        """检测非大陆 → 保持官方默认"""
        from gui import source_detect

        source_detect._on_geo_detected(app, False)
        assert app.source_combo.currentText() == SOURCE_BANGUMI_TEXT
        assert app.selected_source == SOURCE_BANGUMI_TEXT

    def test_detect_failure_keeps_official(self, app):
        """检测失败（None）→ 保持官方默认"""
        from gui import source_detect

        source_detect._on_geo_detected(app, None)
        assert app.source_combo.currentText() == SOURCE_BANGUMI_TEXT
        assert app.selected_source == SOURCE_BANGUMI_TEXT

    def test_user_touched_source_not_overridden(self, app):
        """用户手动切过源 → 检测完成不覆盖用户选择"""
        from gui import source_detect

        app._source_user_touched = True
        source_detect._on_geo_detected(app, True)
        assert app.source_combo.currentText() == SOURCE_BANGUMI_TEXT
        assert app.selected_source == SOURCE_BANGUMI_TEXT
