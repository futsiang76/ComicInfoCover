"""DialogBridge 与 XML 弹窗测试"""
import threading

from PySide6.QtWidgets import QWidget

from gui.gui_dialogs import DialogBridge


def test_dialogbridge_created(qtbot):
    """DialogBridge 创建成功"""
    parent = QWidget()
    qtbot.addWidget(parent)
    bridge = DialogBridge(parent)
    assert bridge._waiting is False
    assert isinstance(bridge._event, threading.Event)


def test_dialogbridge_cancel(qtbot):
    """DialogBridge 取消等待"""
    parent = QWidget()
    qtbot.addWidget(parent)
    bridge = DialogBridge(parent)
    bridge._waiting = True
    bridge._event.clear()
    bridge.cancel()
    assert bridge._waiting is False


def test_dialogbridge_invoke(qtbot, monkeypatch):
    """DialogBridge invoke get_text 正常返回"""
    parent = QWidget()
    qtbot.addWidget(parent)
    bridge = DialogBridge(parent)
    monkeypatch.setattr(
        "gui.gui_dialogs.DialogBridge._show_text_dialog",
        staticmethod(lambda p, title="", prompt="", default="": "test_result")
    )
    result = bridge.invoke("get_text", title="Test", prompt="Enter:")
    assert result == "test_result"


def test_build_stats_html_int_version():
    """int 版 stats（scan_controller）：统计区 + 两个文件列表区块"""
    from gui.dialogs import _build_xml_stats_html

    stats = {
        "total_files": 25,
        "files_with_xml": 15,
        "files_without_xml": 10,
        "sample_files": [f"有{i}.cbz" for i in range(1, 11)],
        "no_xml_files": [f"无{i}.cbz" for i in range(1, 11)],
    }
    html = _build_xml_stats_html(stats)

    # 统计区计数
    assert "总文件数：25 个" in html
    assert "已有XML：15 个 ✅" in html
    assert "无XML文件：10 个 ❌" in html
    # 两个文件列表区块（前10 + 超10省略号带总数）
    assert "📁 已有XML的文件：" in html
    assert "📂 没有XML的文件：" in html
    assert "有1.cbz" in html
    assert "无1.cbz" in html
    # 有XML 15>10 → 省略号带总数；无XML 恰好10 → 不省略
    assert "共 15 个" in html
    assert "共 10 个" not in html
    # 不再出现「示例」区块
    assert "示例" not in html


def test_build_stats_html_list_version():
    """list 版 stats（xml_mode_handler）：统计区取 len + 两个文件列表区块"""
    from gui.dialogs import _build_xml_stats_html

    stats = {
        "total_files": 20,
        "files_with_xml": [f"有{i}.cbz" for i in range(1, 6)],
        "files_without_xml": [f"无{i}.cbz" for i in range(1, 13)],
        "sample_files": [f"有{i}.cbz" for i in range(1, 6)],
        "folder_name": "测试系列",
    }
    html = _build_xml_stats_html(stats)

    # 统计区：list 版取 len 显示计数
    assert "总文件数：20 个" in html
    assert "已有XML：5 个 ✅" in html
    assert "无XML文件：12 个 ❌" in html
    # 两个文件列表区块（无XML 12>10 → 省略号带总数）
    assert "📁 已有XML的文件：" in html
    assert "📂 没有XML的文件：" in html
    assert "有1.cbz" in html
    assert "无1.cbz" in html
    assert "共 12 个" in html
    # 不再出现「示例」区块
    assert "示例" not in html


def test_check_xml_before_scan_no_xml_files(tmp_path):
    """check_xml_before_scan 返回的 stats 含 no_xml_files（前10）与 sample_files（前10）"""
    import zipfile

    from gui.scan_controller import check_xml_before_scan

    with_dir = tmp_path / "有xml"
    without_dir = tmp_path / "无xml"
    with_dir.mkdir()
    without_dir.mkdir()
    for i in range(1, 13):
        with zipfile.ZipFile(with_dir / f"有{i}.zip", "w") as zf:
            zf.writestr("ComicInfo.xml", "<ComicInfo/>")
    for i in range(1, 13):
        with zipfile.ZipFile(without_dir / f"无{i}.zip", "w") as zf:
            zf.writestr("page1.jpg", "data")

    has_xml, stats = check_xml_before_scan(None, str(tmp_path))

    assert has_xml is True
    assert stats["files_with_xml"] == 12
    assert stats["files_without_xml"] == 12
    assert len(stats["sample_files"]) == 10
    assert len(stats["no_xml_files"]) == 10
    # 无XML示例只包含无XML文件
    assert all("无" in f for f in stats["no_xml_files"])


def _build_xml_options_html(mw):
    """调用弹窗实际使用的 HTML 构建函数"""
    from gui.dialogs import _build_xml_options_html as build

    return build(mw)


def _make_mw(selected_source):
    """构造带 selected_source 的假 mw"""
    return type("FakeMw", (), {"selected_source": selected_source})()


def test_xml_options_html_manhuagui():
    """selected_source=manhuagui → 渲染文本含显示名"""
    html = _build_xml_options_html(_make_mw("manhuagui"))
    assert "重新从manhuagui获取信息并生成新的XML文件" in html
    assert "不进行manhuagui搜索" in html


def test_xml_options_html_comicvine():
    """selected_source=ComicVine → 渲染文本含 ComicVine"""
    html = _build_xml_options_html(_make_mw("ComicVine"))
    assert "重新从ComicVine获取信息并生成新的XML文件" in html
    assert "不进行ComicVine搜索" in html


def test_xml_options_html_bangumi_default():
    """selected_source=Bangumi（官方） → 渲染文本显示 Bangumi（去掉括号后缀）"""
    html = _build_xml_options_html(_make_mw("Bangumi（官方）"))
    assert "重新从Bangumi获取信息并生成新的XML文件" in html
    assert "不进行Bangumi搜索" in html
    assert "Bangumi（官方）" not in html


def test_xml_options_html_mw_none_defaults_bangumi():
    """mw 为 None → 渲染文本默认 Bangumi"""
    html = _build_xml_options_html(None)
    assert "重新从Bangumi获取信息并生成新的XML文件" in html
    assert "不进行Bangumi搜索" in html


def test_xml_options_html_source_combo_fallback():
    """无 selected_source 时回退 source_combo.currentText()"""
    class FakeCombo:
        def currentText(self):
            return "manhuagui"

    mw = type("FakeMw", (), {"source_combo": FakeCombo()})()
    html = _build_xml_options_html(mw)
    assert "重新从manhuagui获取信息并生成新的XML文件" in html

