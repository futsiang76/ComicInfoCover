#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L193: 文件格式兼容 cbz/cbr/rar/7z 保存/读取测试

覆盖范围：
- cbz（=zip）：走 zipfile 读写，扩展名保留 .cbz（不做格式转换）
- cbr/rar/7z：走 7-Zip —— 读取 XML、写入 XML + 格式转换（解压→写XML→重压.cbz，keep 模式固定保留原文件）
- 读取路径：read_xml_from_zip / check_zip_xml_files 对 4 种格式均可直接读

说明：7-Zip 只支持解压 RAR、不支持创建 RAR，本机未装 WinRAR。
cbr/rar 测试文件用 7z 创建 zip 压缩归档 + 对应扩展名模拟，
验证"扩展名 → 7-Zip 转换链路"逻辑；7z 解压按内容嗅探格式，链路与真 RAR 一致。
"""

import os
import subprocess
import zipfile

import pytest

from processors.zip_operations import (add_file_to_zip, check_zip_xml_files,
                                       read_xml_from_zip)

SEVEN_ZIP = r"D:\Program Files\7-Zip\7z.exe"

SAMPLE_XML = """<?xml version="1.0"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <Title>测试漫画</Title>
    <Series>测试系列</Series>
    <Volume>1</Volume>
    <Manga>Yes</Manga>
</ComicInfo>
"""


def _has_seven_zip() -> bool:
    return os.path.exists(SEVEN_ZIP)


def _make_archive(archive_path: str, src_dir: str) -> None:
    """用 7-Zip 创建 zip 压缩归档（内容来自 src_dir 下的文件）"""
    result = subprocess.run(
        [SEVEN_ZIP, 'a', '-tzip', '-y', str(archive_path), f'{src_dir}/*'],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def cbz_file(tmp_path):
    """用 zipfile 创建真实 .cbz（含图片占位，无 XML）"""
    path = tmp_path / "test_vol1.cbz"
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as zf:
        zf.writestr("001.jpg", b"fake-image-bytes-001")
        zf.writestr("002.jpg", b"fake-image-bytes-002")
    return str(path)


@pytest.fixture(params=["cbr", "rar", "7z"])
def seven_zip_archive(tmp_path, request):
    """用 7z 创建归档（无 XML，扩展名按参数模拟 cbr/rar/7z）"""
    if not _has_seven_zip():
        pytest.skip("7-Zip 未安装，跳过归档格式测试")
    ext = request.param
    src_dir = tmp_path / f"src_{ext}"
    src_dir.mkdir()
    (src_dir / "001.jpg").write_bytes(b"fake-image-bytes-001")
    (src_dir / "002.jpg").write_bytes(b"fake-image-bytes-002")
    archive = tmp_path / f"test_vol1.{ext}"
    _make_archive(archive, src_dir)
    return str(archive)


@pytest.fixture(params=["cbr", "rar", "7z"])
def seven_zip_archive_with_xml(tmp_path, request):
    """用 7z 创建含 ComicInfo.xml 的归档（用于直接读取/检查链路）"""
    if not _has_seven_zip():
        pytest.skip("7-Zip 未安装，跳过归档格式测试")
    ext = request.param
    src_dir = tmp_path / f"src_xml_{ext}"
    src_dir.mkdir()
    (src_dir / "001.jpg").write_bytes(b"fake-image-bytes-001")
    (src_dir / "ComicInfo.xml").write_text(SAMPLE_XML, encoding="utf-8")
    archive = tmp_path / f"xml_vol1.{ext}"
    _make_archive(archive, src_dir)
    return str(archive)


# ---------- cbz（zipfile 路径） ----------

def test_cbz_save_xml_keeps_extension(cbz_file):
    """cbz 保存 XML 后扩展名保留 .cbz（cbz=zip 不走格式转换）"""
    assert add_file_to_zip(cbz_file, SAMPLE_XML)
    assert cbz_file.lower().endswith('.cbz')
    assert os.path.exists(cbz_file)


def test_cbz_read_xml_roundtrip(cbz_file):
    """cbz 保存后可用 read_xml_from_zip 读回内容"""
    assert add_file_to_zip(cbz_file, SAMPLE_XML)
    info = read_xml_from_zip(cbz_file)
    assert info is not None
    assert info.get("Title") == "测试漫画"
    assert info.get("Series") == "测试系列"
    assert info.get("Volume") == "1"


def test_cbz_check_xml_files(cbz_file):
    """cbz 保存后 check_zip_xml_files 能检测到目标 XML 且内容一致"""
    assert add_file_to_zip(cbz_file, SAMPLE_XML)
    exists, matches, other = check_zip_xml_files(cbz_file, SAMPLE_XML)
    assert exists is True
    assert matches is True
    assert other == []


def test_cbz_read_missing_xml_returns_none(cbz_file):
    """cbz 无 XML 时 read_xml_from_zip 返回 None"""
    assert read_xml_from_zip(cbz_file) is None


# ---------- cbr/rar/7z（7-Zip 保存 + 格式转换链路） ----------

def test_archive_save_converts_to_cbz(seven_zip_archive):
    """cbr/rar/7z 保存 XML 后自动转换为同名 .cbz（keep 模式固定保留原文件）"""
    original = seven_zip_archive
    base = os.path.splitext(original)[0]
    assert add_file_to_zip(original, SAMPLE_XML)
    converted = base + ".cbz"
    assert os.path.exists(converted)
    assert os.path.exists(original)  # keep 模式固定保留原文件，不删除


def test_archive_read_xml_after_conversion(seven_zip_archive):
    """cbr/rar/7z 转换后的 .cbz 可读回 XML 内容（图片文件保留）"""
    original = seven_zip_archive
    base = os.path.splitext(original)[0]
    assert add_file_to_zip(original, SAMPLE_XML)
    converted = base + ".cbz"
    info = read_xml_from_zip(converted)
    assert info is not None
    assert info.get("Title") == "测试漫画"
    with zipfile.ZipFile(converted, 'r') as zf:
        names = zf.namelist()
        assert "ComicInfo.xml" in names
        assert "001.jpg" in names


def test_archive_check_xml_files_after_conversion(seven_zip_archive):
    """cbr/rar/7z 转换后的 .cbz 能被 check_zip_xml_files 识别"""
    original = seven_zip_archive
    base = os.path.splitext(original)[0]
    assert add_file_to_zip(original, SAMPLE_XML)
    converted = base + ".cbz"
    exists, matches, other = check_zip_xml_files(converted, SAMPLE_XML)
    assert exists is True
    assert matches is True


# ---------- cbr/rar/7z（7-Zip 直接读取链路，不转换） ----------

def test_archive_read_xml_direct(seven_zip_archive_with_xml):
    """含 XML 的 cbr/rar/7z 可直接用 read_xml_from_zip 读取"""
    info = read_xml_from_zip(seven_zip_archive_with_xml)
    assert info is not None
    assert info.get("Title") == "测试漫画"
    assert info.get("Manga") == "Yes"


def test_archive_check_xml_direct(seven_zip_archive_with_xml):
    """含 XML 的 cbr/rar/7z 可直接用 check_zip_xml_files 检测"""
    exists, matches, other = check_zip_xml_files(seven_zip_archive_with_xml, SAMPLE_XML)
    assert exists is True
    assert matches is True
    assert other == []


def test_archive_check_xml_mismatch_direct(seven_zip_archive_with_xml):
    """内容不一致时 check_zip_xml_files 返回 matches=False"""
    different_xml = SAMPLE_XML.replace("<Title>测试漫画</Title>",
                                       "<Title>另一本</Title>")
    exists, matches, other = check_zip_xml_files(seven_zip_archive_with_xml, different_xml)
    assert exists is True
    assert matches is False


# ---------- prechecked 复用（save_thread 避免二次 check 重复打印字段日志） ----------

def test_add_file_to_zip_prechecked_skips_recheck(cbz_file, monkeypatch, capsys):
    """prechecked 传入时 add_file_to_zip 复用调用方 check 结果，不再二次 check

    复现 save_thread 场景：先 check_zip_xml_files 发现内容不一致
    （_compare_xml_content 打印一次「字段 修改/删除」日志），再调
    add_file_to_zip —— 传 prechecked 后内部应跳过 check，比较次数不变、
    字段差异日志只出现一次；不传 prechecked 时内部仍会自行 check（对照）。
    """
    import config
    import processors.zip_operations as zo

    # 固定 keep 模式，确保走原地写路径（不触发格式转换分支）
    monkeypatch.setattr(config, "SAVE_FORMAT", "keep")

    # 先写入 SAMPLE_XML，让目标 XML 存在
    assert add_file_to_zip(cbz_file, SAMPLE_XML)

    # 构造内容不一致的 XML（Title 变化 → 触发字段差异日志）
    different_xml = SAMPLE_XML.replace("<Title>测试漫画</Title>",
                                       "<Title>另一本</Title>")

    # 统计 _compare_xml_content 调用次数
    real_compare = zo._compare_xml_content
    compare_calls = {"n": 0}

    def counting_compare(existing_xml, new_xml):
        compare_calls["n"] += 1
        return real_compare(existing_xml, new_xml)

    monkeypatch.setattr(zo, "_compare_xml_content", counting_compare)

    # 模拟 save_thread：先 check 一次（1 次比较 + 1 条字段日志）
    target_exists, content_matches, other_xml_files = check_zip_xml_files(cbz_file, different_xml)
    assert target_exists is True
    assert content_matches is False
    first_calls = compare_calls["n"]
    assert first_calls == 1

    # prechecked 复用：add_file_to_zip 内部不再 check → 比较次数与字段日志均不增加
    assert add_file_to_zip(cbz_file, different_xml,
                           prechecked=(target_exists, content_matches, other_xml_files))
    assert compare_calls["n"] == first_calls
    assert str(capsys.readouterr().out).count("📋 字段") == 1

    # 对照：不传 prechecked 时内部仍自行 check（比较次数 +1，字段日志再打一条）
    before = compare_calls["n"]
    assert add_file_to_zip(cbz_file, SAMPLE_XML)
    assert compare_calls["n"] == before + 1
    assert str(capsys.readouterr().out).count("📋 字段") == 1
