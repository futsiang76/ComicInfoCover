#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_smart_title 短篇完结规则测试（2026-08-23 新增）

覆盖：
- (短篇) → 系列名.短篇完结（原规则3 返回裸系列名，行为变更点）
- (V01全 短篇) → 系列名.短篇完结（卷分支 complete=True，短篇进 tags）
- (Vol01全 短篇) → 系列名.短篇完结（Vol 变体）
- (短篇全) → 系列名.短篇完结（无卷号变体）
- (V01全) → 系列名.单卷完结（回归，不破坏现有规则）
- (V01全 缺Part2-3) / (V01全 缺V2) → 系列名.单卷完结（括号内补充信息不进 Title）
- (V03全 缺V2) 多卷带补充 → 括号内容不进 Title（剥离后为 Vol 03）
- Vol 01 描述文字（括号外描述）→ 保留（回归）
- 常规卷/单话 → 既有规则不回归
- 有卷号的多卷系列带短篇集 tag → 不误判为短篇完结

folder_info 一律走 parse_folder_name_lenient 真实解析，保证与生产解析链一致。
"""
from parsers.file_parser import generate_smart_title, is_short_story_folder
from parsers.folder_parser_lenient import parse_folder_name_lenient


def _parse_folder(folder_name):
    """解析文件夹名得到 folder_info（与生产扫描链路一致）"""
    r = parse_folder_name_lenient(folder_name)
    assert r is not None, f"解析失败: {folder_name}"
    return r


def test_short_story_folder_title_suffix():
    """(短篇) → 系列名.短篇完结（第二元素 non_volume 保持 False）"""
    folder_info = _parse_folder("[比良贺みん也] 化身者 (短篇)")
    title, non_volume = generate_smart_title("化身者 (短篇).zip", "化身者", folder_info)
    assert title == "化身者.短篇完结"
    assert non_volume is False
    assert is_short_story_folder(folder_info) is True


def test_short_story_with_volume_title_suffix():
    """(V01全 短篇)：先命中卷号 complete=True，短篇进 tags → 也走短篇完结"""
    folder_info = _parse_folder("[作者] X (V01全 短篇)")
    assert folder_info["complete"] is True
    assert folder_info["vol_info"] == "V01全"
    assert "短篇" in folder_info["tags"]
    title, _ = generate_smart_title("X (V01全 短篇).zip", "X", folder_info)
    assert title == "X.短篇完结"


def test_short_story_vol_variant_title_suffix():
    """(Vol01全 短篇) Vol 变体 → 系列名.短篇完结"""
    folder_info = _parse_folder("[作者] X (Vol01全 短篇)")
    title, _ = generate_smart_title("X (Vol01全 短篇).zip", "X", folder_info)
    assert title == "X.短篇完结"


def test_short_story_full_variant_title_suffix():
    """(短篇全) 无卷号变体 → 系列名.短篇完结"""
    folder_info = _parse_folder("[作者] X (短篇全)")
    title, _ = generate_smart_title("X (短篇全).zip", "X", folder_info)
    assert title == "X.短篇完结"


def test_short_story_title_suffix_idempotent():
    """series_name 已带 .短篇完结 → 不重复追加"""
    folder_info = _parse_folder("[作者] X (短篇)")
    title, _ = generate_smart_title("X.zip", "X.短篇完结", folder_info)
    assert title == "X.短篇完结"


def test_single_volume_complete_unchanged():
    """(V01全) → 系列名.单卷完结（回归）"""
    folder_info = _parse_folder("[作者] X (V01全)")
    title, _ = generate_smart_title("X (V01全).zip", "X", folder_info)
    assert title == "X.单卷完结"


def test_regular_volume_unchanged():
    """常规卷文件夹内 Vol 01.zip → "Vol 01"（回归）"""
    folder_info = _parse_folder("[作者] X (V05)")
    title, _ = generate_smart_title("Vol 01.zip", "X", folder_info)
    assert title == "Vol 01"


def test_chapter_file_unchanged():
    """单话文件 → "C 01"（回归）"""
    folder_info = _parse_folder("[作者] X (V05)")
    title, _ = generate_smart_title("C01.zip", "X", folder_info)
    assert title == "C 01"


def test_multi_volume_with_short_tag_not_suffixed():
    """有卷号的多卷系列带 短篇集 tag → 不误判为短篇完结"""
    folder_info = _parse_folder("[作者] X (V10全 短篇集)")
    assert is_short_story_folder(folder_info) is False
    title, _ = generate_smart_title("X (V10全 短篇集).zip", "X", folder_info)
    assert title != "X.短篇完结"


def test_folder_info_missing_keys_safe():
    """folder_info 缺 vol_type（如 build_file_comicinfo 兜底 dict）→ 不抛异常"""
    folder_info = {"series": "X", "complete": True}
    title, _ = generate_smart_title("Vol 01.zip", "X", folder_info)
    assert title == "Vol 01"


def test_single_volume_complete_with_supplement():
    """(V01全 缺Part2-3)：zip 文件名括号内补充信息不进 Title → 系列名.单卷完结"""
    folder_info = _parse_folder("[诸星大二郎] 天塌下来那天 (V01全 缺Part2-3)")
    # 文件夹解析侧：缺卷说明照常进 tags（folder_parser_lenient 行为不变）
    assert "缺Part2-3" in folder_info["tags"]
    title, _ = generate_smart_title(
        "[诸星大二郎] 天塌下来那天 (V01全 缺Part2-3).zip", "天塌下来那天", folder_info
    )
    assert title == "天塌下来那天.单卷完结"
    assert "缺Part2-3" not in title


def test_single_volume_complete_with_supplement_short():
    """(V01全 缺V2) → 系列名.单卷完结（缺卷说明不进 Title）"""
    folder_info = _parse_folder("[作者] X (V01全 缺V2)")
    title, _ = generate_smart_title("X (V01全 缺V2).zip", "X", folder_info)
    assert title == "X.单卷完结"
    assert "缺V2" not in title


def test_volume_with_description_unchanged():
    """Vol 01 描述文字（括号外描述）→ 保留（回归）"""
    folder_info = _parse_folder("[作者] X (V05)")
    title, _ = generate_smart_title("Vol 01 描述文字.zip", "X", folder_info)
    assert title == "Vol 01 描述文字"


def test_multi_volume_with_supplement_stripped():
    """(V03全 缺V2)：多卷带补充 → 不拼补充，括号内容不进 Title → Vol 03"""
    folder_info = _parse_folder("[作者] X (V03全 缺V2)")
    assert "缺V2" in folder_info["tags"]  # 文件夹解析侧缺卷照常进 tags
    title, _ = generate_smart_title("X (V03全 缺V2).zip", "X", folder_info)
    assert title == "Vol 03"
    assert "缺V2" not in title
    assert ")" not in title
