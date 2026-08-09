#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Bangumi 搜索结果「series 字段 + 卷号标记」逐条过滤（最终规则）

规则（用户拍板 2026-08-05，替代结果数阈值启发式）：
- series=True（系列条目）→ 保留
- series=False 且名称带「卷号标记」的条目（系列的单卷）→ 过滤
- series=False 但无卷号标记（外传/原画集/设定集/一卷全独立作品，如 蓦然回首）→ 保留

卷号标记 _has_volume_marker：括号数字 (1)（2）/ 中文卷册话 第1卷（第0卷不算）/
西文 Vol.1 #1 V1。每个条目独立判定，不依赖结果集大小，无额外详情请求。
"""

from unittest.mock import MagicMock

from models.bangumi_fetcher import (_filter_series_volumes, _has_volume_marker,
                                    BangumiFetcher)


class JsonResponse:
    """模拟带 JSON 数据的 requests.Response"""

    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class TestHasVolumeMarker:
    """测试 _has_volume_marker 卷号标记判定"""

    def test_paren_half_width(self):
        assert _has_volume_marker("CLAMP学園探偵団 (1)") is True

    def test_paren_full_width(self):
        assert _has_volume_marker("测试系列（2）") is True

    def test_paren_with_spaces(self):
        assert _has_volume_marker("测试 ( 3 )") is True

    def test_paren_zero_is_marker(self):
        # (0) 属括号数字标记：咒术回战 (0) 东京都立咒术高等专门学校 应被过滤
        assert _has_volume_marker("呪術廻戦 (0) 東京都立呪術高等専門学校") is True

    def test_chinese_volume(self):
        assert _has_volume_marker("测试 第1卷") is True

    def test_chinese_book(self):
        assert _has_volume_marker("测试 第2册") is True

    def test_chinese_chapter(self):
        assert _has_volume_marker("测试 第3话") is True

    def test_chinese_multi_digit_volume(self):
        assert _has_volume_marker("测试 第10卷") is True

    def test_chinese_volume_zero_not_marker(self):
        # 第0卷属一卷全特殊卷，不是系列单卷标记（进击的巨人 第0卷 应保留）
        assert _has_volume_marker("进击的巨人 第0卷") is False

    def test_japanese_kanji_volume_not_marker(self):
        # 日文「巻」不在 [卷册话] 内，不匹配
        assert _has_volume_marker("進撃の巨人 第0巻") is False

    def test_vol_dot(self):
        assert _has_volume_marker("Test Vol.4") is True

    def test_vol_space(self):
        assert _has_volume_marker("Test Vol 5") is True

    def test_vol_lowercase(self):
        assert _has_volume_marker("Test vol 6") is True

    def test_hash_number(self):
        assert _has_volume_marker("Test #7") is True

    def test_v_number_uppercase(self):
        assert _has_volume_marker("Test V8") is True

    def test_v_number_lowercase(self):
        assert _has_volume_marker("Test v9") is True

    def test_no_marker_plain_name(self):
        assert _has_volume_marker("一拳超人") is False

    def test_no_marker_empty(self):
        assert _has_volume_marker("") is False

    def test_no_marker_none(self):
        assert _has_volume_marker(None) is False

    def test_no_marker_number_suffix(self):
        # 无括号/卷/Vol 前缀的纯数字后缀不算卷号标记
        assert _has_volume_marker("进击的巨人 0") is False

    def test_no_marker_japanese_volume_word(self):
        # 日文「巻」字不含括号数字，不算
        assert _has_volume_marker("進撃の巨人 0") is False


class TestFilterSeriesVolumes:
    """测试 _filter_series_volumes 逐条过滤（series 字段 + 卷号标记）"""

    @staticmethod
    def _item(iid, name, name_cn="", series=False):
        return {"id": iid, "name": name, "name_cn": name_cn, "series": series}

    def test_keeps_series_true_with_marker(self):
        """series=True（系列/爱藏版）即使带卷号标记也保留"""
        items = [self._item(1, "呪術廻戦 (1)", series=True)]
        result = _filter_series_volumes(items)
        assert [r["id"] for r in result] == [1]

    def test_filters_series_false_with_paren_marker(self):
        """series=False 且名称带括号数字 → 过滤（CLAMP学園探偵団 (1) 场景）"""
        items = [self._item(1, "CLAMP学園探偵団 (1)", series=False)]
        assert _filter_series_volumes(items) == []

    def test_filters_series_false_with_fullwidth_marker(self):
        items = [self._item(1, "测试系列（2）", series=False)]
        assert _filter_series_volumes(items) == []

    def test_filters_series_false_with_chinese_marker(self):
        items = [self._item(1, "测试系列 第3卷", series=False)]
        assert _filter_series_volumes(items) == []

    def test_filters_series_false_with_western_marker(self):
        items = [self._item(1, "Test Series Vol.4", series=False)]
        assert _filter_series_volumes(items) == []

    def test_filters_series_false_paren_zero(self):
        """(0) 是括号数字标记：咒术回战 0 应被过滤"""
        items = [self._item(1, "呪術廻戦 (0) 東京都立呪術高等専門学校", series=False)]
        assert _filter_series_volumes(items) == []

    def test_filters_marker_in_name_cn(self):
        """卷号标记命中 name_cn 同样过滤（咒喰ノ契リ (1) 场景）"""
        items = [self._item(1, "呪喰ノ契リ", "呪喰ノ契リ (1)", series=False)]
        assert _filter_series_volumes(items) == []

    def test_keeps_series_false_no_marker(self):
        """series=False 但无卷号标记 → 保留（外传/原画集/设定集/一卷全）"""
        items = [
            self._item(1, "CLAMP学園探偵団 誕生日", series=False),   # 外传
            self._item(2, "NORTH SIDE", series=False),              # 原画集
            self._item(3, "SOUTH SIDE", series=False),              # 原画集
            self._item(4, "設定資料集", series=False),               # 设定集
            self._item(5, "蓦然回首", series=False),                 # 一卷全
        ]
        result = _filter_series_volumes(items)
        assert [r["id"] for r in result] == [1, 2, 3, 4, 5]

    def test_keeps_series_false_volume_zero(self):
        """series=False 且名称为「第0卷」无卷号标记 → 保留（进击的巨人 第0卷）"""
        items = [self._item(1, "進撃の巨人 0", "进击的巨人 第0卷", series=False)]
        result = _filter_series_volumes(items)
        assert [r["id"] for r in result] == [1]

    def test_missing_series_defaults_false_no_marker_kept(self):
        """无 series 字段（默认 False）且无卷号标记 → 保留（保守兜底）"""
        items = [{"id": 1, "name": "一拳超人", "name_cn": "一拳超人"}]
        result = _filter_series_volumes(items)
        assert [r["id"] for r in result] == [1]

    def test_missing_series_defaults_false_with_marker_filtered(self):
        """无 series 字段但带卷号标记 → 过滤（与 series=False 同判）"""
        items = [{"id": 1, "name": "一拳超人 (1)", "name_cn": ""}]
        assert _filter_series_volumes(items) == []

    def test_series_none_kept(self):
        """series=None（异常数据）按非 False 处理 → 保留"""
        items = [{"id": 1, "name": "测试 (1)", "name_cn": "", "series": None}]
        result = _filter_series_volumes(items)
        assert [r["id"] for r in result] == [1]

    def test_mixed_set(self):
        """混合场景：仅过滤 series=False 且带卷号标记的条目"""
        items = [
            self._item(1, "CLAMP学園探偵団", series=True),
            self._item(2, "CLAMP学園探偵団 (1)", series=False),   # 过滤
            self._item(3, "CLAMP学園探偵団 (2)", series=False),   # 过滤
            self._item(4, "CLAMP学園探偵団 誕生日", series=False),  # 保留（外传）
            self._item(5, "NORTH SIDE", series=False),            # 保留（原画集）
        ]
        result = _filter_series_volumes(items)
        assert [r["id"] for r in result] == [1, 4, 5]

    def test_empty_list(self):
        assert _filter_series_volumes([]) == []


class TestSearchMangaSeriesVolumeFilter:
    """测试 search_manga 逐条过滤集成行为"""

    def _make_fetcher(self, search_items):
        fetcher = BangumiFetcher()
        fetcher.session.post = MagicMock(return_value=JsonResponse({"data": search_items}))
        fetcher.get_manga_detail = MagicMock(return_value=None)
        return fetcher

    def test_clamp_scenario(self):
        """CLAMP学園探偵団 场景：过滤 series=False 带卷号标记的 (1)(2)(3)，
        保留系列(series=True)与外传/原画集/设定集(series=False 无卷号)"""
        search_items = [
            {"id": 1, "name": "CLAMP学園探偵団", "name_cn": "CLAMP学園探偵団", "series": True},
            {"id": 2, "name": "CLAMP学園探偵団 (1)", "name_cn": "", "series": False},
            {"id": 3, "name": "CLAMP学園探偵団 (2)", "name_cn": "", "series": False},
            {"id": 4, "name": "CLAMP学園探偵団 (3)", "name_cn": "", "series": False},
            {"id": 5, "name": "CLAMP学園探偵団 誕生日", "name_cn": "CLAMP学園探偵団 誕生日",
             "series": False},
            {"id": 6, "name": "CLAMP学園探偵団 NORTH SIDE", "name_cn": "CLAMP学園探偵団 NORTH SIDE",
             "series": False},
            {"id": 7, "name": "CLAMP学園探偵団 設定資料集", "name_cn": "CLAMP学園探偵団 設定資料集",
             "series": False},
        ]
        fetcher = self._make_fetcher(search_items)
        results = fetcher.search_manga("CLAMP学園探偵団")
        result_ids = [r["id"] for r in results]
        assert 2 not in result_ids and 3 not in result_ids and 4 not in result_ids
        assert all(i in result_ids for i in [1, 5, 6, 7])

    def test_attack_on_titan_scenario(self):
        """进击的巨人 场景：第0卷无括号数字、原画集等全部保留（不过滤）"""
        search_items = [
            # 真实数据：卷号是纯数字后缀（如 进击的巨人 1），无括号/第X卷 标记 → 不触发过滤
            {"id": i, "name": f"進撃の巨人 {i}", "name_cn": f"进击的巨人 {i}",
             "series": False} for i in range(1, 8)
        ] + [
            # 第0卷属一卷全特殊卷，不算卷号标记 → 保留
            {"id": 10, "name": "進撃の巨人 0", "name_cn": "进击的巨人 第0卷", "series": False},
            # 原画集：series=False 且无卷号标记 → 保留
            {"id": 11, "name": "進撃の巨人 原画集", "name_cn": "进击的巨人 原画集",
             "series": False},
        ]
        fetcher = self._make_fetcher(search_items)
        results = fetcher.search_manga("进击的巨人")
        assert len(results) == 9

    def test_jujutsu_scenario(self):
        """咒术回战 场景：过滤 咒术回战 0((0)) 与 呪喰ノ契リ (1)，保留系列与其它"""
        search_items = [
            {"id": 1, "name": "呪術廻戦", "name_cn": "咒术回战", "series": True},
            {"id": 2, "name": "呪術廻戦 (0) 東京都立呪術高等専門学校", "name_cn": "咒术回战 0",
             "series": False},
            {"id": 3, "name": "呪喰ノ契リ", "name_cn": "呪喰ノ契リ (1)", "series": False},
            {"id": 4, "name": "呪術廻戦 ファンブック", "name_cn": "咒术回战 公式书",
             "series": False},
        ]
        fetcher = self._make_fetcher(search_items)
        results = fetcher.search_manga("咒术回战")
        result_ids = [r["id"] for r in results]
        assert 2 not in result_ids and 3 not in result_ids
        assert all(i in result_ids for i in [1, 4])

    def test_look_back_scenario(self):
        """蓦然回首 场景：单条一卷全（series=False 无卷号）→ 保留"""
        search_items = [
            {"id": 342254, "name": "ルックバック", "name_cn": "蓦然回首", "series": False},
        ]
        fetcher = self._make_fetcher(search_items)
        results = fetcher.search_manga("蓦然回首")
        assert [r["id"] for r in results] == [342254]

    def test_one_punch_scenario(self):
        """一拳超人 场景：无卷号标记 → 全部保留"""
        search_items = [
            {"id": i, "name": f"一拳超人 {i}", "name_cn": f"一拳超人 {i}", "series": False}
            for i in range(1, 8)
        ]
        fetcher = self._make_fetcher(search_items)
        results = fetcher.search_manga("一拳超人")
        assert len(results) == 7

    def test_no_detail_fetch_for_filtering(self):
        """过滤判定不依赖详情：高匹配条目无需为过滤请求详情"""
        search_items = [{"id": 20, "name": "未知作品", "name_cn": "", "series": False}]
        fetcher = self._make_fetcher(search_items)
        results = fetcher.search_manga("未知作品")
        assert [r["id"] for r in results] == [20]
        assert fetcher.get_manga_detail.call_count == 0

    def test_keeps_alias_matched_item(self):
        """低匹配条目经别名匹配后保留（详情仅用于别名检查，不用于过滤）"""
        search_items = [{"id": 30, "name": "完全无关作品", "name_cn": "", "series": False}]
        fetcher = BangumiFetcher()
        fetcher.session.post = MagicMock(return_value=JsonResponse({"data": search_items}))
        fetcher.get_manga_detail = MagicMock(return_value={
            "id": 30, "volumes": 0, "series": False,
            "infobox": [{"key": "别名", "value": [{"v": "别名目标"}]}],
        })
        results = fetcher.search_manga("别名目标")
        assert [r["id"] for r in results] == [30]
        assert fetcher.get_manga_detail.call_count == 1


class TestWebSearchFallbackFilter:
    """测试 _web_search_fallback 与 API 搜索统一的逐条过滤"""

    @staticmethod
    def _detail(sid, name, name_cn="", series=False):
        return {"id": sid, "name": name, "name_cn": name_cn, "series": series, "rating": {}}

    def test_filters_series_false_marked(self):
        """series=False 且带卷号标记 → 过滤；series=True 带标记与无标记 → 保留"""
        fetcher = BangumiFetcher()
        fetcher._web_search_subject_ids = MagicMock(return_value=["1", "2", "3", "4"])
        fetcher.get_manga_detail = MagicMock(side_effect=[
            self._detail(1, "测试作品 (1)", series=False),   # 过滤
            self._detail(2, "测试作品 (2)", series=True),    # 系列 → 保留
            self._detail(3, "测试作品 外传", series=False),   # 无卷号 → 保留
            self._detail(4, "测试作品 设定集", series=False),  # 无卷号 → 保留
        ])
        results = fetcher._web_search_fallback("测试作品")
        assert [r["id"] for r in results] == [2, 3, 4]

    def test_keeps_volume_zero(self):
        """第0卷无卷号标记 → 保留"""
        fetcher = BangumiFetcher()
        fetcher._web_search_subject_ids = MagicMock(return_value=["1", "2"])
        fetcher.get_manga_detail = MagicMock(side_effect=[
            self._detail(1, "進撃の巨人 0", "进击的巨人 第0卷", series=False),
            self._detail(2, "進撃の巨人 1", "进击的巨人 第1卷", series=False),
        ])
        results = fetcher._web_search_fallback("进击的巨人")
        assert [r["id"] for r in results] == [1]
