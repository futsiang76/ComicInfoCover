#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面工具 - ZIP 封面提取与竖版比例检测（P2 展示用）

比例判定规则继承 007_zipCoverCropper（只读引用，不修改 007 文件）：
    - config/config_manager.py：标准封面 870x1230（宽高比 0.707），±10% 容差
    - image_handler/cover_detector.py：文件名分段排序规则（取排序最小者为首卷封面）

图片尺寸直接从文件头解析（PNG/JPEG/GIF/BMP），不依赖 PIL。
"""
import os
import re
import struct
import zipfile
from functools import cmp_to_key
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 支持的图片扩展名（与 007 supported_image_extensions 一致）
SUPPORTED_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

# 标准封面尺寸与容差（继承 007 config 默认值）
STANDARD_WIDTH = 870
STANDARD_HEIGHT = 1230
ASPECT_RATIO_TOLERANCE = 0.1

# 单张封面最大读取字节数（防超大图占满内存）
MAX_COVER_BYTES = 30 * 1024 * 1024

# 解析尺寸所需的最小前缀字节数
_PREFIX_BYTES = 4096


def is_cover_ratio_ok(width: int, height: int) -> bool:
    """判断封面宽高比是否在标准范围（870x1230 ±10%，即 0.643~0.778）

    继承 007 ConfigManager.is_valid_aspect_ratio 的双边容差逻辑：
    超范围（过大如横版扫描图、过瘦长）均视为「需裁剪」异常。
    """
    if width <= 0 or height <= 0:
        return False
    aspect = width / height
    standard = STANDARD_WIDTH / STANDARD_HEIGHT
    low = standard / (1 + ASPECT_RATIO_TOLERANCE)
    high = standard * (1 + ASPECT_RATIO_TOLERANCE)
    return low <= aspect <= high


def split_segments(filename: str) -> List[str]:
    """按 [-_.] 分段文件名（拷贝自 007 image_handler/cover_detector.py，来源见文件头）"""
    return re.split(r"[-_.]", Path(filename).stem.lower())


def _compare_segment(a: str, b: str) -> int:
    """比较单个分段：数字段按数值比较，非数字按字典序"""
    a_is_num = a.isdigit()
    b_is_num = b.isdigit()
    if a_is_num and b_is_num:
        na, nb = int(a), int(b)
        if na != nb:
            return na - nb
        if len(a) != len(b):
            return len(b) - len(a)  # "01" 排在 "1" 前（与 007 一致）
        return 0
    if a != b:
        return -1 if a < b else 1
    return 0


def _custom_compare(f1: str, f2: str) -> int:
    """分段逐位比较（拷贝自 007 custom_compare，取排序最小者为默认封面）"""
    segs1 = split_segments(f1)
    segs2 = split_segments(f2)
    for s1, s2 in zip(segs1, segs2):
        result = _compare_segment(s1, s2)
        if result != 0:
            return result
    return len(segs1) - len(segs2)


def sort_cover_files(filenames: List[str]) -> List[str]:
    """按 007 分段排序规则排序 zip 内图片，返回列表首项即默认封面"""
    return sorted(filenames, key=cmp_to_key(_custom_compare))


def natural_sort_key(name: str) -> list:
    """自然排序 key：数字段按数值比较（'Vol 2' < 'Vol 10'）

    用于对漫画卷文件名排序以确定首卷（007 排序规则针对 zip 内页码，
    卷文件名的 'Vol 2'/'Vol 10' 需要按数值比较）。
    """
    parts = re.split(r"(\d+)", os.path.splitext(name)[0].lower())
    return [int(p) if p.isdigit() else p for p in parts]


def sort_volume_files(filenames: List[str]) -> List[str]:
    """按自然顺序排序漫画卷文件名（用于取首卷封面 / 卷网格展示）"""
    return sorted(filenames, key=natural_sort_key)


def _image_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """从图片文件头解析宽高，不依赖 PIL（返回 (width, height) 或 None）"""
    if len(data) < 26:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    if data[:6] in (b"GIF87a", b"GIF89a"):
        width, height = struct.unpack("<HH", data[6:10])
        return width, height
    if data[:2] == b"BM":
        width, height = struct.unpack("<ii", data[18:26])
        return abs(width), abs(height)
    if data[:2] == b"\xff\xd8":
        return _jpeg_dimensions(data)
    return None  # WebP 等未支持格式，交由 UI 占位图兜底


def _jpeg_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """解析 JPEG 尺寸：逐段扫描 SOF 标记（SOF0~SOF15，排除 DHT/JPG/DAC）"""
    pos = 2
    n = len(data)
    while pos + 9 <= n:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        # 独立标记（无长度字段）：SOI、TEM
        if marker in (0xD8, 0x01):
            pos += 2
            continue
        # RST0~RST7
        if 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        # EOI / SOS：其后为压缩数据，不可能再有 SOF
        if marker in (0xD9, 0xDA):
            break
        if pos + 4 > n:
            break
        seg_len = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if seg_len < 2:
            break
        # SOF0-3、SOF5-7、SOF9-11、SOF13-15（排除 DHT 0xC4、JPG 0xC8、DAC 0xCC）
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
            return width, height
        pos += 2 + seg_len
    return None


def _first_image_name(zf: zipfile.ZipFile) -> Optional[str]:
    """返回 zip 内第一个图片文件（按 007 排序规则取最小者，视为封面）"""
    images = [
        info.filename
        for info in zf.infolist()
        if not info.is_dir()
        and os.path.splitext(info.filename)[1].lower() in SUPPORTED_IMAGE_EXTS
    ]
    if not images:
        return None
    return sort_cover_files(images)[0]


def _read_prefix(zf: zipfile.ZipFile, name: str, size: int = _PREFIX_BYTES) -> bytes:
    """读取 zip 内文件的前缀字节（避免读全图仅用于解析尺寸）"""
    with zf.open(name) as f:
        return f.read(size)


def get_zip_first_image(zip_path: str) -> Optional[str]:
    """返回 zip 内排序最小的图片条目名（当前封面），供 P3 裁剪定位原图"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return _first_image_name(zf)
    except Exception as e:
        print(f"⚠️   封面定位失败 [{os.path.basename(zip_path)}]: {str(e)[:60]}")
        return None


def read_zip_entry(zip_path: str, entry_name: str) -> Optional[bytes]:
    """读取 zip 内指定条目原始字节（P3 裁剪原图用，不受 MAX_COVER_BYTES 限制）"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return zf.read(entry_name)
    except Exception as e:
        print(f"⚠️   读取 zip 条目失败 [{os.path.basename(zip_path)}]: {str(e)[:60]}")
        return None


def get_zip_cover_info(zip_path: str) -> Optional[Dict]:
    """解析 zip 首图尺寸与比例判定

    Returns:
        {"path", "width", "height", "ratio_ok"}，无图片/格式不支持/失败返回 None
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            name = _first_image_name(zf)
            if name is None:
                return None
            prefix = _read_prefix(zf, name)
            dims = _image_dimensions(prefix)
            if dims is None:
                return None
            width, height = dims
            return {
                "path": zip_path,
                "width": width,
                "height": height,
                "ratio_ok": is_cover_ratio_ok(width, height),
            }
    except Exception as e:
        print(f"⚠️  封面尺寸解析失败 [{os.path.basename(zip_path)}]: {str(e)[:60]}")
        return None


def read_cover_bytes(zip_path: str) -> Optional[bytes]:
    """读取 zip 首图原始字节（供 UI 渲染缩略图，超大图返回 None 由占位图兜底）"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            name = _first_image_name(zf)
            if name is None:
                return None
            info = zf.getinfo(name)
            if info.file_size > MAX_COVER_BYTES:
                return None
            return zf.read(name)
    except Exception as e:
        print(f"⚠️  封面读取失败 [{os.path.basename(zip_path)}]: {str(e)[:60]}")
        return None
