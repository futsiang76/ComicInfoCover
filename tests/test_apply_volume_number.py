#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_volume_number 公共函数测试 — 统一 Volume/Number 推导逻辑

覆盖四种分支：
- detail 有 volume → 单行本（Number 取 detail.number，缺省同 volume）
- detail 只有 number → 单话（Number=话号，Volume 空）
- 文件名解析单行本（"Vol 03.zip"）→ Volume/Number 同值
- 文件名解析单话（"C 05.zip"）→ Number=话号，Volume 空
- detail 有独立 number != volume → Number 保留独立值
"""
from processors.xml_generator import apply_volume_number


def test_detail_volume_sets_both_number_same_as_volume():
    """单行本：detail 有 volume（无 number）→ Number 缺省同 Volume"""
    info = {"Title": "x"}
    apply_volume_number(info, "Some Series.zip", {"volume": "035"})
    assert info["Volume"] == "035"
    assert info["Number"] == "035"


def test_detail_number_only_sets_number_volume_empty():
    """单话：detail 有 number 无 volume → Number=话号，Volume 空"""
    info = {"Title": "x"}
    apply_volume_number(info, "Some Series.zip", {"number": "12"})
    assert info["Number"] == "12"
    assert info["Volume"] == ""


def test_detail_independent_number_overrides_volume():
    """单行本：detail 同时有 volume 和独立 number → Number 保留独立值"""
    info = {"Title": "x"}
    apply_volume_number(info, "Some Series.zip",
                        {"volume": "035", "number": "7"})
    assert info["Volume"] == "035"
    assert info["Number"] == "7"


def test_filename_volume_parses_single_volume():
    """文件名解析单行本：Vol 03 → Volume/Number 同值（zfill 宽度）"""
    info = {"Title": "x"}
    apply_volume_number(info, "Vol 03.zip")
    assert info["Volume"] == "03"
    assert info["Number"] == "03"


def test_filename_chapter_parses_single_chapter():
    """文件名解析单话：C 05 → Number=话号（含前导零），Volume 空"""
    info = {"Title": "x"}
    apply_volume_number(info, "Series C 05.zip")
    assert info["Number"] == "05"
    assert info["Volume"] == ""


def test_filename_chapter_chinese_parses():
    """文件名解析单话：第03话 → Number=03，Volume 空"""
    info = {"Title": "x"}
    apply_volume_number(info, "某漫画 第03话.zip")
    assert info["Number"] == "03"
    assert info["Volume"] == ""


def test_filename_unparsable_clears_both():
    """文件名无卷话信息 → Volume/Number 都空"""
    info = {"Title": "x", "Volume": "OLD", "Number": "OLD"}
    apply_volume_number(info, "Random File Name.zip")
    assert info["Volume"] == ""
    assert info["Number"] == ""