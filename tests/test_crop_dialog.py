"""裁剪对话框测试：画布拉伸（stretch=1）、记忆推荐初始框、确定后记录经验"""
import struct
import zipfile
import zlib

from gui.crop_dialog import CropDialog
from processors.crop_memory import CropMemory


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


def _make_cbz(tmp_path, name: str, width: int, height: int):
    cbz_path = tmp_path / name
    with zipfile.ZipFile(cbz_path, "w") as zf:
        zf.writestr("000.png", _make_png(width, height))
    return cbz_path


def _patch_memory(monkeypatch, tmp_path):
    """用临时记忆文件替换 CropDialog 的 CropMemory，避免读写真实记忆"""
    mem = CropMemory(memory_file=str(tmp_path / "crop_memory.json"))
    monkeypatch.setattr("gui.crop_dialog.CropMemory", lambda: mem)
    return mem


def test_crop_dialog_canvas_stretch(qtbot, tmp_path, monkeypatch):
    """画布吃掉剩余垂直空间（stretch=1）：画布高度 ≥ 窗体 60%，图片 ≥ 80%"""
    _patch_memory(monkeypatch, tmp_path)
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", 1000, 1230)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    dialog.resize(1000, 780)
    dialog.show()
    qtbot.wait(20)
    # 非 stretch 时画布只占 minimumSize（300x200，约窗体 1/3 高度）
    assert dialog.canvas.height() / dialog.height() >= 0.6
    # 竖版图等比缩放后显示高度占满画布，占比 ≥ 80%
    img_ratio = dialog.canvas._disp_rect.height() / dialog.height()
    assert img_ratio >= 0.8


def test_crop_dialog_initial_crop_centered_without_memory(qtbot, tmp_path, monkeypatch):
    """记忆无经验 → 初始裁剪框居中（1200x1230 水平居中 x=165）"""
    _patch_memory(monkeypatch, tmp_path)
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", 1200, 1230)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    assert dialog.canvas._orig_crop.x() == 165
    assert dialog.canvas._orig_crop.width() == 870
    assert dialog.canvas._orig_crop.height() == 1230


def test_crop_dialog_initial_crop_uses_memory_recommendation(qtbot, tmp_path, monkeypatch):
    """记忆有相似比例经验 → 初始裁剪框用推荐位置（x=240）"""
    mem = _patch_memory(monkeypatch, tmp_path)
    mem.add_experience(1200 / 1230, (240, 0, 870, 1230), (1200, 1230))
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", 1200, 1230)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    assert dialog.canvas._orig_crop.x() == 240
    assert dialog.canvas._orig_crop.y() == 0


def test_crop_dialog_records_experience_on_ok(qtbot, tmp_path, monkeypatch):
    """确定裁剪后记录经验（图片比例 + 裁剪位置）并持久化到记忆文件"""
    mem_file = tmp_path / "crop_memory.json"
    mem = _patch_memory(monkeypatch, tmp_path)
    cbz = _make_cbz(tmp_path, "Vol 01.cbz", 1000, 1230)
    dialog = CropDialog(str(cbz))
    qtbot.addWidget(dialog)
    dialog._on_ok()
    assert dialog.crop_region is not None
    assert mem.get_experience_count() == 1
    assert abs(mem.experiences[0].aspect_ratio - 1000 / 1230) < 1e-6
    assert mem.experiences[0].x_position_ratio == dialog.crop_region[0] / 1000

    # 记忆文件已写入，重新加载后仍能读取该经验
    assert mem_file.exists()
    mem2 = CropMemory(memory_file=str(mem_file))
    assert mem2.get_experience_count() == 1
    assert abs(mem2.experiences[0].aspect_ratio - 1000 / 1230) < 1e-6
