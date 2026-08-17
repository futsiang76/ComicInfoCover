"""P2 封面展示测试：比例判定 / zip 封面解析 / 结果页缩略图渲染与异常角标"""
import struct
import zipfile
import zlib
from pathlib import Path

from PySide6.QtWidgets import QLabel, QPushButton

from processors.cover_utils import (get_zip_cover_info, is_cover_ratio_ok,
                                    read_cover_bytes, sort_cover_files,
                                    sort_volume_files)


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


def _make_cbz(tmp_path: Path, name: str, width: int, height: int) -> Path:
    """生成带指定尺寸 PNG 封面的 cbz 文件"""
    cbz_path = tmp_path / name
    with zipfile.ZipFile(cbz_path, "w") as zf:
        zf.writestr("000.png", _make_png(width, height))
    return cbz_path


def _result_dict(series: str, covers: dict) -> dict:
    """构造最小可渲染的结果字典"""
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


# ---------- 比例判定 ----------

def test_is_cover_ratio_ok_standard():
    """标准竖版 870x1230 判定为正常"""
    assert is_cover_ratio_ok(870, 1230) is True


def test_is_cover_ratio_ok_within_tolerance():
    """比标准略宽但在 +10% 容差内（≤0.778）判定为正常"""
    assert is_cover_ratio_ok(800, 1230) is True   # 0.650
    assert is_cover_ratio_ok(956, 1230) is True   # 0.777


def test_is_cover_ratio_ok_skinnier_than_standard():
    """比标准更瘦长的纵向图（无下界）判定为正常（007 单边逻辑）"""
    assert is_cover_ratio_ok(980, 1542) is True   # 0.636 天狱案例
    assert is_cover_ratio_ok(790, 1230) is True   # 0.642
    assert is_cover_ratio_ok(600, 1000) is True   # 0.600


def test_is_cover_ratio_ok_out_of_tolerance():
    """超过上界（过宽 / 横向扫描图）判定为异常"""
    assert is_cover_ratio_ok(958, 1230) is False  # 0.779 > 上界


def test_is_cover_ratio_ok_horizontal():
    """横向扫描图判定为异常"""
    assert is_cover_ratio_ok(1920, 1080) is False


def test_is_cover_ratio_ok_invalid():
    """非法尺寸判定为异常"""
    assert is_cover_ratio_ok(0, 0) is False
    assert is_cover_ratio_ok(-100, 100) is False


# ---------- zip 封面解析 ----------

def test_get_zip_cover_info_valid(tmp_path):
    """竖版封面：解析出宽高且比例正常"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", 100, 150)
    info = get_zip_cover_info(str(cbz))
    assert info is not None
    assert info["width"] == 100
    assert info["height"] == 150
    assert info["ratio_ok"] is True


def test_get_zip_cover_info_horizontal(tmp_path):
    """横向封面：解析出宽高且比例异常"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", 1920, 1080)
    info = get_zip_cover_info(str(cbz))
    assert info is not None
    assert info["ratio_ok"] is False

def test_get_zip_cover_info_webp(tmp_path):
    """webp 封面（含 .jpg.webp 双扩展名）：PIL 能识别宽高与比例"""
    from io import BytesIO

    from PIL import Image

    cbz_path = tmp_path / "Vol 01.cbz"
    with zipfile.ZipFile(cbz_path, "w") as zf:
        buf = BytesIO()
        Image.new("RGB", (100, 150), (153, 153, 153)).save(buf, "WEBP")
        zf.writestr("000.jpg.webp", buf.getvalue())
    info = get_zip_cover_info(str(cbz_path))
    assert info is not None
    assert info["width"] == 100
    assert info["height"] == 150
    assert info["ratio_ok"] is True


def test_get_zip_cover_info_no_image(tmp_path):
    """zip 内无图片 → 返回 None"""
    cbz = tmp_path / "empty.cbz"
    with zipfile.ZipFile(cbz, "w") as zf:
        zf.writestr("ComicInfo.xml", "<ComicInfo/>")
    assert get_zip_cover_info(str(cbz)) is None


def test_get_zip_cover_info_invalid_zip(tmp_path):
    """损坏的 zip → 返回 None 不抛异常"""
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"PK\x03\x04 not a zip")
    assert get_zip_cover_info(str(bad)) is None


def test_read_cover_bytes(tmp_path):
    """读取 zip 首图原始字节（PNG 签名校验）"""
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", 100, 150)
    data = read_cover_bytes(str(cbz))
    assert data is not None
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_read_cover_bytes_missing_file():
    """不存在的文件 → 返回 None"""
    assert read_cover_bytes("/nonexistent/x.cbz") is None


def test_sort_volume_files_natural_order():
    """卷名按自然序排序（Vol 10 排在 Vol 2 之后）"""
    names = ["Vol 10.cbz", "Vol 2.cbz", "Vol 1.cbz"]
    assert sort_volume_files(names) == ["Vol 1.cbz", "Vol 2.cbz", "Vol 10.cbz"]


def test_sort_cover_files_mixed_number_letter_first():
    """数字+字母混合名按自然序：'00a' 排 '004' 前（Komga 0.37+ 语义）"""
    assert sort_cover_files(["004.jpg", "00a.jpg"]) == ["00a.jpg", "004.jpg"]


def test_sort_cover_files_leading_zeros():
    """前导零同数值时位数多者排前（'001' < '01' < '1'）"""
    assert sort_cover_files(["1.jpg", "01.jpg", "001.jpg"]) == ["001.jpg", "01.jpg", "1.jpg"]


def test_sort_cover_files_directory_natural_order():
    """目录段保持自然序回归：C 01 < C 02 < C 10（防破坏 2026-08-14 目录排序修复）"""
    files = ["Vol 01/C 10/x.jpg", "Vol 01/C 02/x.jpg", "Vol 01/C 01/x.jpg"]
    assert [f.split("/")[1] for f in sort_cover_files(files)] == ["C 01", "C 02", "C 10"]


def test_create_result_dict_from_xml_covers(tmp_path):
    """修正模式（create_result_dict_from_xml）同样收集封面信息"""
    from processors.result_builder import create_result_dict_from_xml
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", 100, 150)
    folder_info = {"series": "Smoke", "complete": True, "total_volumes": 1}
    xml_result = {
        "comic_info_base": {"Series": "Smoke", "Status": "Completed"},
        "selected_result": {},
    }
    result = create_result_dict_from_xml(str(tmp_path), folder_info, xml_result)
    covers = result.get("covers", {})
    assert "Vol 01.cbz" in covers
    assert covers["Vol 01.cbz"]["ratio_ok"] is True


# ---------- 结果页渲染 ----------

def _group_boxes(app):
    return [app.results_layout.itemAt(i).widget()
            for i in range(app.results_layout.count())]


def test_results_table_renders_cover_and_badge(app, tmp_path, qtbot):
    """首卷正常、二卷异常：卡片无角标，展开网格后异常卷带「需裁剪」角标"""
    cover1 = _make_cbz(tmp_path, "Vol 01.cbz", 100, 150)
    cover2 = _make_cbz(tmp_path, "Vol 02.cbz", 1920, 1080)
    info1 = get_zip_cover_info(str(cover1))
    info2 = get_zip_cover_info(str(cover2))
    result = _result_dict("Test Series", {"Vol 01.cbz": info1, "Vol 02.cbz": info2})
    app.scan_results = [result]
    app.update_results_table()

    box = _group_boxes(app)[0]
    assert box is not None
    labels = box.findChildren(QLabel)
    assert any(l.text() == "📚 共 2 卷" for l in labels)
    # 首卷正常 → 未展开时无「需裁剪」角标
    assert not any(l.text() == "需裁剪" for l in labels)

    expand_btn = next(b for b in box.findChildren(QPushButton) if b.text() == "展开 ▼")
    expand_btn.click()
    assert any(l.text() == "需裁剪" for l in box.findChildren(QLabel))
    assert expand_btn.text() == "收起 ▲"


def test_results_table_badge_on_abnormal_first_volume(app, tmp_path):
    """首卷即异常：卡片直接显示「需裁剪」角标"""
    cover = _make_cbz(tmp_path, "Vol 01.cbz", 1920, 1080)
    info = get_zip_cover_info(str(cover))
    result = _result_dict("Bad First", {"Vol 01.cbz": info})
    app.scan_results = [result]
    app.update_results_table()

    box = _group_boxes(app)[0]
    assert any(l.text() == "需裁剪" for l in box.findChildren(QLabel))


def test_results_table_renders_without_covers(app):
    """无封面信息：显示占位图，不崩溃"""
    result = _result_dict("No Cover", {})
    app.scan_results = [result]
    app.update_results_table()

    box = _group_boxes(app)[0]
    assert any(l.text() == "📕" for l in box.findChildren(QLabel))


def test_results_table_multiple_series(app, tmp_path):
    """多个系列卡片各自渲染，数量正确"""
    result1 = _result_dict("Series A", {})
    result2 = _result_dict("Series B", {})
    app.scan_results = [result1, result2]
    app.update_results_table()
    assert len(_group_boxes(app)) == 2


def test_grid_columns_adaptive():
    """B5：网格列数按可用宽度自适应——窄屏保底 4 列，宽屏 8+ 列"""
    from gui.results_table import grid_columns

    assert grid_columns(200) == 4   # 极窄保底
    assert grid_columns(400) == 4
    assert grid_columns(440) == 4   # 4*110 边界
    assert grid_columns(880) == 8   # 单格 110px → 8 列
    assert grid_columns(1200) >= 10
    assert grid_columns(2000) >= 18
    assert grid_columns(3000) >= 27
