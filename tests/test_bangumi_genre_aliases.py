#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Bangumi 别名提取：name 带括号时拆分为「主名 + 括号内容」两个独立别名

修复目标（t_1e89b4cf）：
- 「白いパイロット（手塚治虫漫画全集）」→ 别名拆成「白いパイロット」+「手塚治虫漫画全集」
- 不再出现缺右括号的坏值「白いパイロット（手塚治虫漫画全集」
- 卷标括号 (V01)/(1)/第X卷 不提取，正常清理
"""

import pytest

from models.bangumi_genre import extract_bangumi_aliases, _clean_name_for_alias


class TestCleanNameForAlias:
    def test_bracket_content_removed_keep_main_name(self):
        assert _clean_name_for_alias("白いパイロット（手塚治虫漫画全集）") == "白いパイロット"

    def test_halfwidth_bracket_removed(self):
        assert _clean_name_for_alias("某作品 (第1卷)") == "某作品"

    def test_volume_markers_still_cleaned(self):
        assert _clean_name_for_alias("某作品 (V01)") == "某作品"
        assert _clean_name_for_alias("某作品（1）") == "某作品"

    def test_no_bracket_unchanged(self):
        assert _clean_name_for_alias("ガチアクタ") == "ガチアクタ"


class TestExtractBangumiAliases:
    def test_bracket_name_split_into_main_and_content(self):
        detail = {
            "name": "白いパイロット（手塚治虫漫画全集）",
            "name_cn": "白色领航员",
            "infobox": [],
        }
        assert extract_bangumi_aliases(detail) == ["白いパイロット", "手塚治虫漫画全集"]

    def test_no_broken_missing_right_paren_alias(self):
        detail = {
            "name": "白いパイロット（手塚治虫漫画全集）",
            "name_cn": "白色领航员",
            "infobox": [],
        }
        aliases = extract_bangumi_aliases(detail)
        assert "白いパイロット（手塚治虫漫画全集" not in aliases

    @pytest.mark.parametrize("name", ["某作品 (V01)", "某作品（1）", "某作品（第3卷）"])
    def test_volume_bracket_content_not_extracted(self, name):
        detail = {"name": name, "name_cn": "别称", "infobox": []}
        aliases = extract_bangumi_aliases(detail)
        assert "某作品" in aliases
        # 括号内容不进别名（V01/1/第3卷 均被跳过或纯数字剔除）
        assert not any(a in ("V01", "1", "第3卷") for a in aliases)

    def test_no_bracket_name_regression(self):
        detail = {"name": "ガチアクタ", "name_cn": "嘎嗒嘎嗒", "infobox": []}
        assert extract_bangumi_aliases(detail) == ["ガチアクタ"]

    def test_infobox_alias_still_works(self):
        detail = {
            "name": "某作品",
            "name_cn": "某作品",
            "infobox": [{"key": "别名", "value": [{"v": "Another Title"}, {"k": "来源", "v": "来源别名"}]}],
        }
        assert extract_bangumi_aliases(detail) == ["Another Title", "来源别名"]