"""P3 裁剪交互测试：封面裁剪执行（__old/__new + 打包顺序）/ 裁剪对话框 / 结果页点击裁剪"""
import os
import struct
import zipfile
import zlib
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QSizePolicy

import gui.crop_queue as cq
import gui.results_table as rt
from gui.crop_dialog import CropDialog
from gui.results_table import ClickableLabel
from gui.title_edit_dialog import TitleEditDialog
from processors.cover_crop import crop_zip_cover
from processors.cover_utils import (get_zip_cover_info, get_zip_first_image,
                                    is_cover_ratio_ok, read_zip_entry)

HORIZONTAL = (1920, 1080)   # 横向扫描图 → 比例异常
PORTRAIT = (100, 150)       # 竖版 → 比例正常
CROP_REGION = (0, 0, 764, 1080)  # 870:1230 比例（居中默认框等价区域）


def _make_png(width: int, height: int) -> bytes:
    """生成最小合法 PNG（RGB 纯色）"""
    def chunk(typ: bytes, data: bytes) -> bytes:
        payload = typ + data
        return (struct.pack(">I", len(data)) + payload
                + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\x99\x99\x99" * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def _make_cbz(tmp_path: Path, name: str, entries: dict) -> Path:
    """生成指定条目的 cbz 文件（entries: 名称 → 字节内容）"""
    cbz_path = tmp_path / name
    with zipfile.ZipFile(cbz_path, "w") as zf:
        for entry_name, data in entries.items():
            zf.writestr(entry_name, data)
    return cbz_path


def _horizontal_cbz(tmp_path: Path, name: str = "Vol 01.cbz") -> Path:
    """生成横向封面（1920x1080，比例异常）的 cbz"""
    return _make_cbz(tmp_path, name, {"000.png": _make_png(*HORIZONTAL)})


def _zip_entries(cbz_path: Path) -> list:
    with zipfile.ZipFile(cbz_path, "r") as zf:
        return zf.infolist()


def _result_dict(series: str, covers: dict) -> dict:
    """构造最小可渲染的结果字典（对齐 test_cover_display）"""
    return {
        "folder_path": "/tmp/dummy",
        "folder_name": f"{series} Folder",
        "series": series,
        "file_titles": {k: k for k in covers},
        "file_details": {k: {"volume": i + 1} for i, k in enumerate(covers)},
        "covers": covers,
        "locked_files": set(),
        "count": str(len(covers)),
        "writer": "",
        "penciller": "",
        "colorist": "",
        "web": "",
        "year": "",
        "month": "",
        "status": "Completed",
        "summary": "",
        "genre": "",
        "tags": "",
        "manga": "Yes",
        "process_status": "已修改",
    }


def _group_boxes(app):
    return [app.results_layout.itemAt(i).widget()
            for i in range(app.results_layout.count())]


def _auto_close_dialog(accept: bool = True):
    """在嵌套事件循环中自动关闭当前模态裁剪对话框（走真实按钮路径）"""
    def _close():
        dlg = QApplication.activeModalWidget()
        if isinstance(dlg, CropDialog):
            if accept:
                ok_btn = dlg.findChild(QPushButton, "crop_ok")
                if ok_btn and ok_btn.isEnabled():
                    ok_btn.click()
                    return
            dlg.reject()
    QTimer.singleShot(150, _close)


# ---------- 封面裁剪执行 ----------

def test_crop_zip_cover_creates_new_and_old(tmp_path):
    """裁剪后：原图重命名 __old 保留、新增 __new、__new 排 zip 第一位"""
    cbz = _horizontal_cbz(tmp_path)
    original = read_zip_entry(str(cbz), "000.png")
    assert get_zip_cover_info(str(cbz))["ratio_ok"] is False

    info = crop_zip_cover(str(cbz), CROP_REGION)

    assert info is not None
    assert info["ratio_ok"] is True  # 裁剪后比例正常
    with zipfile.ZipFile(cbz, "r") as zf:
        names = zf.namelist()
        assert "000__new.png" in names
        assert "000__old.png" in names
        assert "000.png" not in names  # 原图被重命名，不再以原名存在
        assert zf.infolist()[0].filename == "000__new.png"  # __new 排第一位
        assert zf.read("000__old.png") == original  # 原图字节完整保留
        new_data = zf.read("000__new.png")
    assert new_data[:8] == b"\x89PNG\r\n\x1a\n"


def test_crop_zip_cover_new_is_valid_portrait(tmp_path):
    """裁剪图尺寸符合竖版 870x1230 比例"""
    cbz = _horizontal_cbz(tmp_path)
    crop_zip_cover(str(cbz), CROP_REGION)
    with zipfile.ZipFile(cbz, "r") as zf:
        new_data = zf.read("000__new.png")
    from PIL import Image
    import io
    with Image.open(io.BytesIO(new_data)) as img:
        width, height = img.size
    assert is_cover_ratio_ok(width, height) is True


def test_crop_zip_cover_preserves_other_entries(tmp_path):
    """裁剪后其余条目保留且相对顺序不变"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", {
        "000.png": _make_png(*HORIZONTAL),
        "ComicInfo.xml": b"<ComicInfo/>",
        "001.png": _make_png(*PORTRAIT),
        "sub/note.txt": b"note",
    })
    crop_zip_cover(str(cbz), CROP_REGION)
    names = [i.filename for i in _zip_entries(cbz)]
    assert names[0] == "000__new.png"
    # 其余条目保留（__old 原位替换原图）
    assert names[1:].index("ComicInfo.xml") < names[1:].index("001.png")
    assert "sub/note.txt" in names


def test_crop_zip_cover_nested_path(tmp_path):
    """封面在子目录中：__old/__new 保留目录前缀"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", {
        "images/000.png": _make_png(*HORIZONTAL),
        "ComicInfo.xml": b"<ComicInfo/>",
    })
    crop_zip_cover(str(cbz), CROP_REGION)
    with zipfile.ZipFile(cbz, "r") as zf:
        assert zf.infolist()[0].filename == "images/000__new.png"
        assert "images/000__old.png" in zf.namelist()
    assert get_zip_cover_info(str(cbz))["ratio_ok"] is True


def test_crop_zip_cover_invalid_zip_returns_none(tmp_path):
    """损坏的 zip → 返回 None 不抛异常"""
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"not a zip")
    assert crop_zip_cover(str(bad), CROP_REGION) is None


def test_get_zip_first_image(tmp_path):
    """首图定位：返回排序最小的图片条目名"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", {
        "ComicInfo.xml": b"<ComicInfo/>",
        "000.png": _make_png(*PORTRAIT),
    })
    assert get_zip_first_image(str(cbz)) == "000.png"


# ---------- 裁剪对话框 ----------

def test_crop_dialog_accept_returns_ratio_locked_region(qtbot, tmp_path):
    """确定：返回原图坐标且锁定 870:1230 比例"""
    cbz = _horizontal_cbz(tmp_path)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    _auto_close_dialog(accept=True)
    result = dialog.exec()

    assert result == CropDialog.DialogCode.Accepted
    x, y, w, h = dialog.crop_region
    assert abs(w / h - 870 / 1230) < 0.01
    assert w <= HORIZONTAL[0] and h <= HORIZONTAL[1]


def test_crop_dialog_cancel_returns_none(qtbot, tmp_path):
    """取消：crop_region 为 None，不裁剪"""
    cbz = _horizontal_cbz(tmp_path)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    _auto_close_dialog(accept=False)
    assert dialog.exec() == CropDialog.DialogCode.Rejected
    assert dialog.crop_region is None
    assert get_zip_first_image(str(cbz)) == "000.png"  # zip 未被修改


def test_crop_dialog_skip_semantics(qtbot, tmp_path):
    """跳过：语义标记 SKIP_PROCESS（对齐 007）"""
    cbz = _horizontal_cbz(tmp_path)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    dialog._on_skip()
    assert dialog.crop_region == "SKIP_PROCESS"
    assert dialog.result() == CropDialog.DialogCode.Rejected


def test_crop_dialog_no_image_shows_error(qtbot, tmp_path):
    """zip 内无图片：对话框不崩，确定按钮禁用"""
    cbz = _make_cbz(tmp_path, "empty.cbz", {"ComicInfo.xml": b"<ComicInfo/>"})
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.isEnabled() is False
    dialog.close()


def test_crop_dialog_has_maximize_button(qtbot, tmp_path):
    """裁剪窗体带右上角最大化按钮（WindowMaximizeButtonHint）"""
    from PySide6.QtCore import Qt

    cbz = _horizontal_cbz(tmp_path)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    try:
        assert bool(dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)
    finally:
        dialog.close()


def test_crop_canvas_image_fills_edges(qtbot):
    """图片贴边等比缩放：小图放大填满画布边缘（不再限制 1.0，不留多余留白）"""
    from PySide6.QtGui import QImage, QPixmap

    from gui.crop_dialog import _CropCanvas

    canvas = _CropCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(800, 600)
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(0x999999)
    canvas.set_pixmap(QPixmap.fromImage(img))
    try:
        rect = canvas._disp_rect
        assert rect.width() > 100  # 被放大
        assert abs(rect.width() - 800) < 0.5 or abs(rect.height() - 600) < 0.5  # 贴边
    finally:
        canvas.close()


# ---------- 结果页点击裁剪 ----------

def test_results_table_click_crop_flow(app, tmp_path, qtbot):
    """点击「需裁剪」封面 → 裁剪对话框确定 → 角标消失 + zip 写入 __new"""
    cbz = _horizontal_cbz(tmp_path, "Vol 01.cbz")
    info = get_zip_cover_info(str(cbz))
    assert info["ratio_ok"] is False
    result = _result_dict("Crop Series", {"Vol 01.cbz": info})
    app.scan_results = [result]
    app.update_results_table()

    box = _group_boxes(app)[0]
    clickable = box.findChildren(ClickableLabel)
    assert len(clickable) == 1  # 封面可点击（异常时带「需裁剪」角标）

    _auto_close_dialog(accept=True)
    clickable[0].clicked.emit()  # 触发裁剪（对话框自动确定）
    qtbot.waitUntil(lambda: not getattr(app, "crop_running", False), timeout=5000)

    with zipfile.ZipFile(cbz, "r") as zf:
        assert zf.infolist()[0].filename == "000__new.png"
    # 重渲染后角标消失、信息更新为正常比例；封面仍可点击裁剪
    assert result["covers"]["Vol 01.cbz"]["ratio_ok"] is True
    box2 = _group_boxes(app)[0]
    labels = box2.findChildren(QLabel)
    assert not any(l.text() == "需裁剪" for l in labels)
    assert len(box2.findChildren(ClickableLabel)) == 1  # 比例正常仍可点击，但无角标


def test_results_table_click_crop_cancel_no_change(app, tmp_path, qtbot):
    """点击后取消：zip 不被修改，角标保留"""
    cbz = _horizontal_cbz(tmp_path, "Vol 01.cbz")
    info = get_zip_cover_info(str(cbz))
    result = _result_dict("Cancel Series", {"Vol 01.cbz": info})
    app.scan_results = [result]
    app.update_results_table()

    box = _group_boxes(app)[0]
    clickable = box.findChildren(ClickableLabel)
    _auto_close_dialog(accept=False)
    clickable[0].clicked.emit()

    assert get_zip_first_image(str(cbz)) == "000.png"  # 未被裁剪
    assert any(l.text() == "需裁剪" for l in box.findChildren(QLabel))


# ---------- B3 结果页布局：缩略图顶部间距 / 裁剪封面贴按钮 / 合格封面可点击 ----------

def _find_layout_containing_label(box, text: str):
    """递归查找直接包含指定文本 QLabel 的布局（结果卡片的 cover_block）"""
    def walk(layout):
        if layout is None:
            return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, QLabel) and widget.text() == text:
                return layout
            found = walk(item.layout())
            if found:
                return found
            if widget is not None:
                found = walk(widget.layout())
                if found:
                    return found
        return None

    return walk(box.layout())


def test_results_table_cover_top_margin(app, tmp_path):
    """缩略图顶部有间距（不顶头）：cover_block 上边距 = 8、间距 = 0"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", {"000.png": _make_png(*PORTRAIT)})
    info = get_zip_cover_info(str(cbz))
    result = _result_dict("Margin Series", {"Vol 01.cbz": info})
    app.scan_results = [result]
    app.update_results_table()

    box = _group_boxes(app)[0]
    cover_block = _find_layout_containing_label(box, "裁剪封面")
    assert cover_block is not None
    assert cover_block.contentsMargins().top() == 8  # 缩略图与卡片顶部留间距
    assert cover_block.spacing() == 0  # 缩略图/标签/按钮之间无默认间距


def test_results_table_crop_label_tight_to_expand(app, tmp_path):
    """「裁剪封面」贴紧「展开」按钮：标签固定高度、无内边距、与按钮间距 0"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", {"000.png": _make_png(*PORTRAIT)})
    info = get_zip_cover_info(str(cbz))
    result = _result_dict("Tight Series", {"Vol 01.cbz": info})
    app.scan_results = [result]
    app.update_results_table()

    box = _group_boxes(app)[0]
    cover_block = _find_layout_containing_label(box, "裁剪封面")
    assert cover_block is not None
    assert cover_block.spacing() == 0  # 标签与展开按钮之间无间距
    crop_label = [l for l in box.findChildren(QLabel) if l.text() == "裁剪封面"][0]
    assert crop_label.contentsMargins().top() == 0  # 标签无内边距
    assert crop_label.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed  # 不随高度拉伸


def test_results_table_qualified_cover_clickable(app, tmp_path):
    """合格封面（比例正常）也可点击裁剪，但无红色「需裁剪」角标"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", {"000.png": _make_png(*PORTRAIT)})
    info = get_zip_cover_info(str(cbz))
    assert info["ratio_ok"] is True
    result = _result_dict("Clickable Series", {"Vol 01.cbz": info})
    app.scan_results = [result]
    app.update_results_table()

    box = _group_boxes(app)[0]
    assert len(box.findChildren(ClickableLabel)) == 1  # 封面可点击
    assert not any(l.text() == "需裁剪" for l in box.findChildren(QLabel))


def test_title_edit_dialog_shows_cover_thumbnails(tmp_path):
    """逐卷编辑对话框含封面缩略图列：合格封面无角标、异常封面带红色角标"""
    good_cbz = _make_cbz(tmp_path, "Vol 01.cbz", {"000.png": _make_png(*PORTRAIT)})
    bad_cbz = _make_cbz(tmp_path, "Vol 02.cbz", {"000.png": _make_png(*HORIZONTAL)})
    data = {
        "series": "Cover Edit Series",
        "file_titles": {"Vol 01.cbz": "Vol 01", "Vol 02.cbz": "Vol 02"},
        "file_details": {"Vol 01.cbz": {"volume": "1"}, "Vol 02.cbz": {"volume": "2"}},
        "covers": {
            "Vol 01.cbz": get_zip_cover_info(str(good_cbz)),
            "Vol 02.cbz": get_zip_cover_info(str(bad_cbz)),
        },
    }
    dialog = TitleEditDialog(data)
    assert dialog.title_table.columnCount() == 8
    assert dialog.title_table.rowCount() == 2
    # 两行都渲染了可点击封面缩略图
    clickables = dialog.title_table.findChildren(ClickableLabel)
    assert len(clickables) == 2
    # 仅异常封面（Vol 02）带红色「需裁剪」角标
    badges = [l for l in dialog.title_table.findChildren(QLabel) if l.text() == "需裁剪"]
    assert len(badges) == 1
    dialog.close()


def test_title_edit_dialog_cover_cell_clickable(qtbot, tmp_path, monkeypatch):
    """逐卷编辑封面缩略图点击绑定：合格封面同样可点击弹裁剪界面"""
    good_cbz = _make_cbz(tmp_path, "Vol 01.cbz", {"000.png": _make_png(*PORTRAIT)})
    data = {
        "series": "Cover Click Series",
        "file_titles": {"Vol 01.cbz": "Vol 01"},
        "file_details": {"Vol 01.cbz": {"volume": "1"}},
        "covers": {"Vol 01.cbz": get_zip_cover_info(str(good_cbz))},
    }
    dialog = TitleEditDialog(data)
    clickable = dialog.title_table.cellWidget(0, 7).findChild(ClickableLabel)
    assert clickable is not None
    # 行为验证（PySide6 的 receivers() 不统计 Python 槽）：
    # 模拟点击 → 应触发 _open_single_crop_flow（弹裁剪界面）
    import gui.title_edit_dialog as ted
    calls = []
    monkeypatch.setattr(ted, "_open_single_crop_flow",
                        lambda *a, **k: calls.append(a))
    clickable.clicked.emit()
    assert calls, "点击合格封面应触发裁剪流程"
    assert calls[0][2] == "Vol 01.cbz"  # (self, covers, filename, ...)
    dialog.close()


# ---------- B1 裁剪窗体可放大 ----------

def test_crop_dialog_resizable_scales_canvas(qtbot, tmp_path):
    """B1：裁剪窗体可放大/缩回——画布不再固定尺寸，随窗口 resize，裁剪框比例仍锁定"""
    cbz = _horizontal_cbz(tmp_path)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    dialog.show()

    # 画布不再固定尺寸（原 960x620 固定，现在可直接 resize）
    dialog.canvas.resize(800, 600)
    QApplication.processEvents()
    assert dialog.canvas.size().width() == 800

    # 窗口放大 → 画布随布局变大
    dialog.resize(1200, 900)
    QApplication.processEvents()
    wide_w = dialog.canvas.width()
    assert wide_w > 400
    # 窗口缩回 → 画布同步变小
    dialog.resize(720, 540)
    QApplication.processEvents()
    assert dialog.canvas.width() < wide_w

    # 缩放后裁剪框比例仍锁定 870:1230
    x, y, w, h = dialog.canvas.crop_region()
    assert w > 0 and h > 0
    assert abs(w / h - 870 / 1230) < 0.01
    dialog.close()


# ---------- B2 跳过 → 自动打开下一张需裁剪的图 ----------

def test_crop_queue_skip_advances_to_next(app, tmp_path, monkeypatch, qtbot):
    """B2：跳过当前图 → 自动打开下一张需裁剪的图；确认后完成队列"""
    cbz1 = _horizontal_cbz(tmp_path, "Vol 01.cbz")
    cbz2 = _horizontal_cbz(tmp_path, "Vol 02.cbz")
    info1 = get_zip_cover_info(str(cbz1))
    info2 = get_zip_cover_info(str(cbz2))
    result = _result_dict("Queue Series", {"Vol 01.cbz": info1, "Vol 02.cbz": info2})
    app.scan_results = [result]
    app.update_results_table()

    # 假对话框：第一张「跳过」（Rejected+SKIP_PROCESS），第二张「确认」（Accepted+区域）
    expected_seq = iter([
        (QDialog.DialogCode.Rejected, "SKIP_PROCESS", cbz1),
        (QDialog.DialogCode.Accepted, (0, 0, 764, 1080), cbz2),
    ])

    class FakeCropDialog:
        def __init__(self, zip_path, parent=None):
            self.zip_path = zip_path
            self.crop_region = None

        def exec(self):
            code, region, expected = next(expected_seq)
            assert os.path.basename(self.zip_path) == os.path.basename(str(expected))
            self.crop_region = region
            return code

    monkeypatch.setattr(cq, "CropDialog", FakeCropDialog)

    rt._open_crop_flow(app, result, "Vol 01.cbz")
    qtbot.waitUntil(lambda: not getattr(app, "crop_running", False), timeout=5000)

    with zipfile.ZipFile(cbz2, "r") as zf:
        assert zf.infolist()[0].filename == "000__new.png"  # 第二张被裁剪
    with zipfile.ZipFile(cbz1, "r") as zf:
        assert "000.png" in zf.namelist()  # 第一张仅跳过，未改动
    assert result["covers"]["Vol 02.cbz"]["ratio_ok"] is True
    assert result["covers"]["Vol 01.cbz"]["ratio_ok"] is False


def test_crop_queue_cancel_stops_flow(app, tmp_path, monkeypatch):
    """B2：取消 → 关闭但不推进，后续需裁剪封面不再弹出"""
    cbz1 = _horizontal_cbz(tmp_path, "Vol 01.cbz")
    cbz2 = _horizontal_cbz(tmp_path, "Vol 02.cbz")
    info1 = get_zip_cover_info(str(cbz1))
    info2 = get_zip_cover_info(str(cbz2))
    result = _result_dict("Queue Series", {"Vol 01.cbz": info1, "Vol 02.cbz": info2})
    app.scan_results = [result]

    opened = []

    class FakeCropDialog:
        def __init__(self, zip_path, parent=None):
            opened.append(zip_path)
            self.crop_region = None

        def exec(self):
            self.crop_region = None  # 取消
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(cq, "CropDialog", FakeCropDialog)

    rt._open_crop_flow(app, result, "Vol 01.cbz")

    assert len(opened) == 1  # 取消后不再推进到下一张
    assert not getattr(app, "crop_running", False)
    with zipfile.ZipFile(cbz1, "r") as zf:
        assert "000.png" in zf.namelist()
    with zipfile.ZipFile(cbz2, "r") as zf:
        assert "000.png" in zf.namelist()
