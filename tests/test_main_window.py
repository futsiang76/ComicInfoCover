"""主窗口初始化、tab 切换测试"""
from PySide6.QtWidgets import QTabWidget, QPushButton


def test_window_title(app):
    assert app.windowTitle() == "ComicScratch"


def test_has_tab_widget(app):
    assert isinstance(app.tab_widget, QTabWidget)
    assert app.tab_widget.count() >= 2


def test_default_tab_is_scan(app):
    assert app.tab_widget.currentIndex() == 0


def test_gear_button_exists(app):
    gear = app.tab_widget.cornerWidget()
    assert gear is not None
    assert isinstance(gear, QPushButton)
    assert gear.text() == "\u2699"
    assert gear.toolTip() == "菜单"


def test_gear_menu_base_actions(app):
    menu = app._gear_menu
    assert menu is not None
    labels = [action.text() for action in menu.actions()]
    # 基础 5 项始终存在
    for base in ("应用设置", "法律声明", "使用说明", "版本", "检查更新"):
        assert base in labels
    # 赞助项按配置可选（sponsor_enabled=True 时出现）
    import config
    if config.SPONSOR_ENABLED:
        assert "赞助支持" in labels


def test_gear_menu_popup_pos_within_window(app, qtbot):
    """菜单弹出位置右缘不超出主窗口右边界"""
    app.show()
    qtbot.wait(100)
    gear = app.tab_widget.cornerWidget()
    pos = app._gear_menu_popup_pos(gear, app._gear_menu)
    menu_width = app._gear_menu.sizeHint().width()
    window_right = app.mapToGlobal(app.rect().topRight()).x()
    assert pos.x() + menu_width <= window_right
    assert pos.y() >= 0


def test_render_markdown_headings_not_plaintext(app):
    """法律声明/使用说明渲染为 HTML：## 符号消失，标题变大字号加粗"""
    md = "## 一、软件性质声明\n\n正文 **加粗** 与 [链接](https://example.com)"
    html = app._render_markdown(md)
    assert "##" not in html
    assert "<h2>" in html
    assert "一、软件性质声明" in html
    assert "<strong>加粗</strong>" in html
    assert 'href="https://example.com"' in html


def test_close_window_no_crash(app, qtbot):
    app.close()
    qtbot.wait(100)
