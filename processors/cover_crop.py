#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面裁剪执行（P3）— 新增裁剪图到 ZIP，不替换原图

流程对齐 007 zip_handler/step4_process._replace_cover 语义：
    原图 cover.jpg → 重命名 cover__old.jpg（保留）
    裁剪生成 cover__new.jpg（新增）
    重新打包 ZIP，cover__new 排第一位（漫画软件读取的封面）

打包顺序控制：直接用 zipfile 重建，__new 条目最先写入，
其余条目保持原顺序，最小改动且不依赖 007 打包逻辑。
"""
import os
import tempfile
import zipfile
from contextlib import ExitStack
from pathlib import Path
from typing import Dict, Optional, Tuple

from .cover_utils import get_zip_cover_info, get_zip_first_image, read_zip_entry
from .image_cropper import ImageCropper
from .utils import zip_lock


def _cover_pair_names(cover_name: str) -> Tuple[str, str]:
    """生成 __old / __new 文件名（保留目录与扩展名，如 images/000.png → images/000__new.png）

    用字符串拼接而非 Path，确保 ZIP 条目名统一使用 '/' 分隔符。
    """
    dirname, basename = cover_name.rsplit("/", 1) if "/" in cover_name else ("", cover_name)
    stem, suffix = os.path.splitext(basename)
    prefix = f"{dirname}/" if dirname else ""
    return prefix + f"{stem}__old{suffix}", prefix + f"{stem}__new{suffix}"


def _crop_cover_bytes(original_bytes: bytes, cover_name: str,
                      crop_region: Tuple[int, int, int, int]) -> Optional[bytes]:
    """用 ImageCropper 将原图裁剪为竖版，返回新图字节（临时文件用完即删）"""
    suffix = os.path.splitext(cover_name)[1] or ".jpg"
    cropper = ImageCropper()
    with tempfile.TemporaryDirectory(prefix="cover_crop_") as tmpdir:
        src = Path(tmpdir) / f"src{suffix}"
        dst = Path(tmpdir) / f"dst{suffix}"
        try:
            src.write_bytes(original_bytes)
        except OSError:
            return None
        if not cropper.crop_image(src, dst, crop_region):
            return None
        try:
            return dst.read_bytes()
        except OSError:
            return None


def _rebuild_zip(zip_path: str, cover_name: str, old_name: str, new_name: str,
                 old_bytes: bytes, new_bytes: bytes) -> bool:
    """重建 ZIP：__new 第一位，原封面重命名 __old，其余条目顺序不变"""
    tmp_path = zip_path + ".tmp"
    # 封面裁剪也是 zip 原地写：与 XML 写盘同一把文件级互斥锁，避免与另一
    # 实例的保存/裁剪并发重写同一 zip
    lock_stack = ExitStack()
    try:
        if not lock_stack.enter_context(zip_lock(zip_path)):
            return False
        with zipfile.ZipFile(zip_path, "r") as zin, \
                zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            # 1. __new 排第一位（漫画软件读取的封面）
            new_info = zipfile.ZipInfo(new_name)
            new_info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(new_info, new_bytes)
            # 2. 其余条目保持原顺序（原封面重命名为 __old）
            for info in zin.infolist():
                if info.filename == cover_name:
                    old_info = zipfile.ZipInfo(old_name, date_time=info.date_time)
                    old_info.compress_type = info.compress_type
                    old_info.external_attr = info.external_attr
                    zout.writestr(old_info, old_bytes)
                elif info.filename == new_name:
                    continue  # __new 已写入，跳过重复条目
                elif info.is_dir():
                    zout.writestr(info, b"")
                else:
                    zout.writestr(info, zin.read(info.filename))
        os.replace(tmp_path, zip_path)
        return True
    except Exception as e:
        print(f"⚠️   ZIP 重建失败 [{os.path.basename(zip_path)}]: {str(e)[:60]}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False
    finally:
        lock_stack.close()


def crop_zip_cover(zip_path: str,
                   crop_region: Tuple[int, int, int, int]) -> Optional[Dict]:
    """对 zip 首图执行裁剪并新增 __new 封面

    原图重命名为 __old 保留，__new 写入 zip 第一位。

    Args:
        zip_path: zip/cbz 文件路径
        crop_region: 原图坐标裁剪区域 (x, y, width, height)

    Returns:
        成功返回重新解析的封面信息（{"path","width","height","ratio_ok"}），失败返回 None
    """
    cover_name = get_zip_first_image(zip_path)
    if not cover_name:
        return None
    original_bytes = read_zip_entry(zip_path, cover_name)
    if not original_bytes:
        return None
    new_bytes = _crop_cover_bytes(original_bytes, cover_name, crop_region)
    if not new_bytes:
        return None
    old_name, new_name = _cover_pair_names(cover_name)
    if not _rebuild_zip(zip_path, cover_name, old_name, new_name,
                        original_bytes, new_bytes):
        return None
    return get_zip_cover_info(zip_path)
