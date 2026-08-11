"""所有扫描源下「检测到已有XML」弹窗触发测试

验证 XML 分流已统一到 BaseScanThread.check_existing_xml：
- 全匹配（Bangumi）/ manhuagui / ComicVine 三个源，有 XML 文件夹都必须触发
  gui_callback('xml_exists')，不得漏源。
"""
import zipfile

from PySide6.QtWidgets import QLabel

from gui.base_scan_thread import RESULT_READY
from gui.comicvine_scan import ComicVineScanThread
from gui.full_match_scan import FullMatchThread
from gui.manhuagui_scan import ManhuaguiScanThread


class _CallbackRecorder:
    """记录弹窗回调，按配置返回选择结果"""

    def __init__(self, choice="skip"):
        self.choice = choice
        self.calls = []

    def __call__(self, action, **params):
        self.calls.append((action, params))
        if action == "edit_result":
            return {"accepted": True, "data": params.get("result")}
        if action == "select_result":
            results = params.get("search_results") or []
            return results[0] if results else None
        if action == "search_failure":
            return {"action": "skip", "value": None}
        return self.choice


def _make_folder_with_xml(tmp_path, name="测试系列"):
    """创建含一个带 ComicInfo.xml 卷的系列文件夹"""
    folder = tmp_path / name
    folder.mkdir()
    with zipfile.ZipFile(folder / "vol1.zip", "w") as zf:
        zf.writestr("ComicInfo.xml",
                    "<ComicInfo><Series>测试系列</Series></ComicInfo>")
    return folder


def _make_folder_info(series="测试系列"):
    return {"series": series}


def _full_match_thread(manga_root, recorder):
    thread = FullMatchThread(str(manga_root), None, parent=None)
    thread._gui_callback = recorder
    thread._fetcher = object()  # 避免创建真实 fetcher
    return thread


def _single_series_thread(thread_cls, manga_root, recorder):
    thread = thread_cls(str(manga_root), None, folders=[], parent=None)
    thread._gui_callback = recorder
    thread._fetcher = object()
    thread._template_handler = object()
    return thread


def test_full_match_thread_xml_exists_triggered(tmp_path):
    """Bangumi 全匹配：有 XML 文件夹 → gui_callback('xml_exists') 触发，skip 跳过"""
    folder = _make_folder_with_xml(tmp_path)
    recorder = _CallbackRecorder(choice="skip")
    thread = _full_match_thread(tmp_path, recorder)

    out = thread.search_and_select(str(folder), _make_folder_info())

    assert "xml_exists" in [c[0] for c in recorder.calls]
    assert out is None


def test_full_match_thread_xml_exists_modify(tmp_path):
    """Bangumi 全匹配：选 modify → 从 XML 构建只读结果，返回 RESULT_READY"""
    folder = _make_folder_with_xml(tmp_path)
    recorder = _CallbackRecorder(choice="modify")
    thread = _full_match_thread(tmp_path, recorder)

    out = thread.search_and_select(str(folder), _make_folder_info())

    assert isinstance(out, tuple) and out[0] is RESULT_READY
    result = out[1]
    assert result.get("skipped") is False
    assert result.get("process_status") == "已修改"


def test_full_match_thread_xml_exists_cancel(tmp_path):
    """Bangumi 全匹配：选 cancel → 终止整个扫描（_is_running=False）"""
    folder = _make_folder_with_xml(tmp_path)
    recorder = _CallbackRecorder(choice="cancel")
    thread = _full_match_thread(tmp_path, recorder)

    out = thread.search_and_select(str(folder), _make_folder_info())

    assert out is None
    assert thread._is_running is False


def test_manhuagui_thread_xml_exists_triggered(tmp_path):
    """manhuagui：有 XML 文件夹 → gui_callback('xml_exists') 触发，skip 跳过"""
    folder = _make_folder_with_xml(tmp_path)
    recorder = _CallbackRecorder(choice="skip")
    thread = _single_series_thread(ManhuaguiScanThread, tmp_path, recorder)

    out = thread.search_and_select(str(folder), _make_folder_info())

    assert "xml_exists" in [c[0] for c in recorder.calls]
    assert out is None


def test_manhuagui_thread_xml_exists_modify(tmp_path):
    """manhuagui：选 modify → 返回 RESULT_READY 只读结果"""
    folder = _make_folder_with_xml(tmp_path)
    recorder = _CallbackRecorder(choice="modify")
    thread = _single_series_thread(ManhuaguiScanThread, tmp_path, recorder)

    out = thread.search_and_select(str(folder), _make_folder_info())

    assert isinstance(out, tuple) and out[0] is RESULT_READY
    assert out[1].get("process_status") == "已修改"


def test_comicvine_thread_xml_exists_triggered(tmp_path):
    """ComicVine：有 XML 文件夹 → gui_callback('xml_exists') 触发，skip 跳过"""
    folder = _make_folder_with_xml(tmp_path)
    recorder = _CallbackRecorder(choice="skip")
    thread = _single_series_thread(ComicVineScanThread, tmp_path, recorder)

    out = thread.search_and_select(str(folder), _make_folder_info())

    assert "xml_exists" in [c[0] for c in recorder.calls]
    assert out is None


def test_comicvine_thread_xml_exists_modify(tmp_path):
    """ComicVine：选 modify → 返回 RESULT_READY 只读结果"""
    folder = _make_folder_with_xml(tmp_path)
    recorder = _CallbackRecorder(choice="modify")
    thread = _single_series_thread(ComicVineScanThread, tmp_path, recorder)

    out = thread.search_and_select(str(folder), _make_folder_info())

    assert isinstance(out, tuple) and out[0] is RESULT_READY
    assert out[1].get("process_status") == "已修改"


def test_xml_exists_dialog_new_render_smoke(qtbot, monkeypatch):
    """冒烟：show_xml_exists_dialog 渲染为统计区 + 两列表（前10+省略号）+ 无示例区块"""
    from gui import dialogs
    from gui.dialogs import show_xml_exists_dialog

    # dialog.exec() 为模态阻塞调用：替换为记录实例 + 立即返回的假 exec，避免测试挂起
    created = []

    class _SpyDialog(dialogs.QDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

        def exec(self):  # 非阻塞，模拟用户点「重新扫描」
            return 2

    monkeypatch.setattr(dialogs, "QDialog", _SpyDialog)

    stats = {
        "total_files": 25,
        "files_with_xml": [f"有{i}.cbz" for i in range(1, 13)],
        "files_without_xml": [f"无{i}.cbz" for i in range(1, 9)],
        "sample_files": [f"有{i}.cbz" for i in range(1, 11)],
        "folder_name": "测试系列",
        "series": "测试系列",
    }
    show_xml_exists_dialog(None, stats)
    assert created, "对话框未被创建"
    dialog = created[0]
    qtbot.addWidget(dialog)
    texts = [lbl.text() for lbl in dialog.findChildren(QLabel)]

    # 标题含系列名与提示
    assert "检测到已有XML文件" in dialog.windowTitle()
    assert "测试系列" in dialog.windowTitle()
    # 统计区
    assert any("📊 检测统计：" in t for t in texts)
    assert any("总文件数：25 个" in t for t in texts)
    assert any("已有XML：12 个 ✅" in t for t in texts)
    assert any("无XML文件：8 个 ❌" in t for t in texts)
    # 两列表：前10 + 省略号带总数（有XML 12>10 → 省略；无XML 8 → 不省略）
    assert any("📁 已有XML的文件：" in t and "共 12 个" in t for t in texts)
    assert any("📂 没有XML的文件：" in t for t in texts)
    assert not any("共 8 个" in t for t in texts)  # 8 ≤ 10 → 不省略，无总数行
    # 无「示例」区块
    assert not any("示例" in t for t in texts)
    dialog.close()
