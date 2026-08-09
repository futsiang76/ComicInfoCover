"""主窗口初始化、tab 切换测试"""
from PyQt6.QtWidgets import QTabWidget, QToolButton


def test_window_title(app):
    assert app.windowTitle() == "ComicInfo XML Creator"


def test_has_tab_widget(app):
    assert isinstance(app.tab_widget, QTabWidget)
    assert app.tab_widget.count() >= 2


def test_default_tab_is_scan(app):
    assert app.tab_widget.currentIndex() == 0


def test_gear_button_exists(app):
    gear = app.tab_widget.cornerWidget()
    assert gear is not None
    assert isinstance(gear, QToolButton)
    assert gear.toolTip() == "菜单"


def test_gear_menu_has_five_actions(app):
    gear = app.tab_widget.cornerWidget()
    assert gear is not None
    menu = gear.menu()
    assert menu is not None
    labels = [action.text() for action in menu.actions()]
    assert labels == ["应用设置", "法律声明", "使用说明", "版本", "检查更新"]


def test_close_window_no_crash(app, qtbot):
    app.close()
    qtbot.wait(100)
