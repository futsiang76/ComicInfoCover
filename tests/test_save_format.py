#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存格式选择逻辑测试 — resolve_save_target / SAVE_FORMAT_EXT

覆盖四种保存格式的 target_ext 解析：
- keep：zip/cbz 原地写（target_ext=None）；rar/cbr 自动转 .cbz 且固定保留原文件
- cbz/zip/cb7：统一转对应扩展名，是否保留原文件由 delete_after_convert 决定
"""
import config
import pytest

from processors.zip_operations import resolve_save_target


def test_keep_format_zip_cbz_no_convert():
    """保持原格式 + zip/cbz → 不转换（原地写）"""
    for ext in (".cbz", ".zip"):
        target_ext, keep = resolve_save_target(f"D:/comics/a{ext}", save_format="keep")
        assert target_ext is None
        assert keep is True


@pytest.mark.parametrize("ext", [".rar", ".cbr"])
def test_keep_format_rar_auto_cbz_keeps_original(ext):
    """保持原格式 + rar/cbr → 自动转 .cbz，且固定保留原文件"""
    target_ext, keep = resolve_save_target(f"D:/comics/a{ext}", save_format="keep")
    assert target_ext == ".cbz"
    assert keep is True


def test_cbz_format_resolves_target():
    """手动选 CBZ → .cbz；delete_after_convert=True 时不保留原文件"""
    target_ext, keep = resolve_save_target("D:/comics/a.rar", save_format="cbz",
                                           delete_after_convert=True)
    assert target_ext == ".cbz"
    assert keep is False


def test_zip_format_keeps_original_when_delete_disabled():
    """手动选 ZIP → .zip；delete_after_convert=False 时保留原文件"""
    target_ext, keep = resolve_save_target("D:/comics/a.rar", save_format="zip",
                                           delete_after_convert=False)
    assert target_ext == ".zip"
    assert keep is True


def test_cb7_format_resolves_target():
    """手动选 CB7 → .cb7"""
    target_ext, keep = resolve_save_target("D:/comics/a.cbz", save_format="cb7",
                                           delete_after_convert=True)
    assert target_ext == ".cb7"
    assert keep is False


def test_resolve_save_target_reads_config_defaults():
    """save_format/delete_after_convert 缺省时读取 config 模块（默认 keep/True）"""
    target_ext, keep = resolve_save_target("D:/comics/a.cbz")
    assert target_ext is None
    assert keep is True


def test_save_format_ext_map():
    """SAVE_FORMAT_EXT 映射符合需求"""
    assert config.SAVE_FORMAT_EXT == {
        "keep": None,
        "cbz": ".cbz",
        "zip": ".zip",
        "cb7": ".cb7",
    }
