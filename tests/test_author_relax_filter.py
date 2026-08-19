#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试作者过滤 0 结果时放宽 relax_author_filter 的排序行为

作者名可能因繁简/中日英/假名差异比对失败，此时不直接「无结果」，
而是按 series/platform 排序（漫画系列 > 漫画单卷 > 其它[小说等]）
取前 limit 个系列名匹配结果。sorted 稳定排序，同优先级保持原顺序。
"""

from models.author_utils import relax_author_filter


def _item(item_id, platform, series=False):
    return {"id": item_id, "name": f"作品{item_id}", "name_cn": "",
            "series": series, "platform": platform}


class TestRelaxAuthorFilter:
    """测试 relax_author_filter 排序"""

    def test_comic_series_first_then_comic_then_other(self):
        """漫画系列在前、漫画次之、其它（小说等）最后"""
        results = [
            _item(1, "小说", series=True),     # 小说系列
            _item(2, "漫画", series=True),     # 漫画系列
            _item(3, "漫画", series=False),    # 漫画单卷
            _item(4, "小说", series=False),    # 小说
            _item(5, "漫画", series=True),     # 漫画系列
        ]
        out = relax_author_filter(results, limit=5)
        ids = [r["id"] for r in out]
        # 漫画系列(2,5) 在前，其次漫画(3)，再次其它(1,4)
        assert ids == [2, 5, 3, 1, 4]

    def test_takes_first_limit(self):
        """取前 limit 个（漫画系列优先填满上限）"""
        results = [
            _item(1, "漫画", series=True),
            _item(2, "漫画", series=True),
            _item(3, "漫画", series=True),
            _item(4, "漫画", series=True),
            _item(5, "漫画", series=True),
            _item(6, "漫画", series=True),
            _item(7, "小说", series=True),
        ]
        out = relax_author_filter(results, limit=5)
        assert [r["id"] for r in out] == [1, 2, 3, 4, 5]

    def test_same_priority_keeps_original_order(self):
        """同优先级保持 search_results 原顺序（稳定排序）"""
        results = [
            _item(1, "漫画", series=False),
            _item(2, "漫画", series=False),
            _item(3, "漫画", series=False),
        ]
        out = relax_author_filter(results, limit=5)
        assert [r["id"] for r in out] == [1, 2, 3]

    def test_only_other_kept(self):
        """全是其它（小说等）时按原顺序取前 limit"""
        results = [
            _item(1, "小说", series=True),
            _item(2, "小说", series=False),
            _item(3, "小说", series=True),
            _item(4, "小说", series=False),
            _item(5, "小说", series=True),
            _item(6, "小说", series=False),
        ]
        out = relax_author_filter(results, limit=5)
        assert [r["id"] for r in out] == [1, 2, 3, 4, 5]

    def test_limit_default_five(self):
        """默认 limit=5"""
        results = [
            _item(1, "小说", series=False),
            _item(2, "小说", series=False),
            _item(3, "小说", series=False),
            _item(4, "漫画", series=True),
            _item(5, "漫画", series=True),
            _item(6, "漫画", series=True),
            _item(7, "漫画", series=True),
            _item(8, "漫画", series=True),
        ]
        out = relax_author_filter(results)
        assert len(out) == 5
        # 漫画系列(4,5,6,7,8)填满前5
        assert [r["id"] for r in out] == [4, 5, 6, 7, 8]

    def test_missing_fields_treated_as_other(self):
        """缺 series/platform 字段按其它兜底，不受影响"""
        results = [
            {"id": 1, "name": "作品1"},                # 无 series/platform
            _item(2, "漫画", series=True),
            _item(3, "", series=False),                 # 空 platform
        ]
        out = relax_author_filter(results, limit=5)
        assert [r["id"] for r in out] == [2, 1, 3]

    def test_empty_input(self):
        """空输入返回空列表"""
        assert relax_author_filter([]) == []
