# -*- coding: utf-8 -*-
"""folder_parser 别名提取增强 + manhuagui 搜索别名补搜 测试"""
import pytest

from parsers.folder_parser import parse_folder_name


def _parse(folder_name: str):
    result = parse_folder_name(folder_name)
    assert result is not None, f"解析失败: {folder_name}"
    return result


class TestSeriesAliasExtraction:
    """问题1：从系列名中提取非中文原名/译名作为别名"""

    def test_hunter_x_hunter(self):
        # 英文原名混在系列名里 → 拆出别名
        r = _parse("[富坚义博] 全职猎人 HUNTER×HUNTER (V35全)")
        assert r["series"] == "全职猎人"
        assert r["aliases"] == ["HUNTER×HUNTER"]

    def test_dragon_ball_katakana(self):
        # 日文假名原名混在系列名里 → 拆出别名
        r = _parse("[鸟山明] 龙珠 ドラゴンボール (V42全)")
        assert r["series"] == "龙珠"
        assert r["aliases"] == ["ドラゴンボール"]

    def test_pure_chinese_no_alias(self):
        # 纯中文系列名 → 别名保持为空
        r = _parse("[宇佐崎白×西修] 魔男伊奇 (V06)")
        assert r["series"] == "魔男伊奇"
        assert r["aliases"] == []

    def test_one_punch_man(self):
        r = _parse("[ONE] 一拳超人 ワンパンマン (V25全)")
        assert r["series"] == "一拳超人"
        assert r["aliases"] == ["ワンパンマン"]

    def test_all_non_chinese_keeps_original(self):
        # 全非中文系列名 → 保持原样，不拆别名
        r = _parse("[作者] HUNTER×HUNTER (V10)")
        assert r["series"] == "HUNTER×HUNTER"
        assert r["aliases"] == []

    def test_bracket_alias_still_works(self):
        # 原有方括号别名逻辑保留
        r = _parse("[作者] 全职猎人 [猎人] (V35全)")
        assert r["series"] == "全职猎人"
        assert r["aliases"] == ["猎人"]

    def test_bracket_plus_series_alias_dedup(self):
        # 括号别名 + 系列名别名合并去重
        r = _parse("[作者] 龙珠 ドラゴンボール [龙珠Z] (V42全)")
        assert r["series"] == "龙珠"
        assert "ドラゴンボール" in r["aliases"]
        assert "龙珠Z" in r["aliases"]

    def test_clamp_series_keeps_full_name(self):
        # 问题1：非中文片段与作者名相同 → 并入系列名，不提取为别名
        r = _parse("[Clamp] CLAMP学園探偵団 (V02全)")
        assert r["series"] == "CLAMP学園探偵団"  # 完整作品名，不截断
        assert "Clamp" not in r["aliases"]  # 作者名不进别名
        assert all("(" not in a and "V0" not in a for a in r["aliases"])  # 卷标不进别名
        assert r["author"] == "Clamp"

    def test_clamp_lowercase_author_case_insensitive(self):
        # 作者名大小写不敏感：作者栏 CLAMP / 系列名 Clamp 视为相同
        r = _parse("[CLAMP] Clamp学園探偵団 (V02全)")
        assert r["series"] == "Clamp学園探偵団"
        assert "Clamp" not in r["aliases"]
        assert r["aliases"] == []


class TestManhuaguiAliasFallback:
    """问题2：manhuagui 主词无结果时用别名补搜"""

    @pytest.fixture
    def patch_route(self, monkeypatch):
        """打桩 route_search + 结果选择弹窗，记录搜索关键词调用与弹窗结果"""
        from gui import manhuagui_scan
        from processors import search_handler

        calls = []
        dialog_results = []

        def fake_route(keyword, folder_info, source="manhuagui"):
            calls.append(keyword)
            if keyword == "全职猎人":
                return []  # 主词无结果
            return [{"id": "123", "name": keyword, "name_cn": keyword,
                     "url": "http://example.com/comic/123/",
                     "author": folder_info.get("author", "")}]

        monkeypatch.setattr(search_handler, "search_manga", fake_route)
        # 结果选择弹窗 → 记录传入结果并模拟用户跳过，避免进入 GUI/网络
        monkeypatch.setattr(
            manhuagui_scan, "show_result_selection_dialog",
            lambda mw, results, folder_info, allow_id_search=True: (
                dialog_results.append(results) or None))

        class FakeLog:
            def __init__(self):
                self.items = []

            def append(self, s):
                self.items.append(s)

        mw = type("MW", (), {"log_text": FakeLog()})()
        return calls, dialog_results, mw

    def test_main_no_result_uses_alias(self, patch_route):
        from gui import manhuagui_scan

        calls, dialog_results, mw = patch_route
        folder_info = {"series": "全职猎人", "aliases": ["HUNTER×HUNTER"],
                       "author": "富坚义博"}
        result = manhuagui_scan._search_and_select_manhuagui(
            mw, "/fake/path", folder_info, None, None)
        assert calls == ["全职猎人", "HUNTER×HUNTER"]  # 先主词后别名
        assert any("用别名「HUNTER×HUNTER」" in item for item in mw.log_text.items)
        # 弹窗收到别名命中的结果（而非别名关键词本身）
        assert [r["name"] for r in dialog_results[0]] == ["HUNTER×HUNTER"]
        assert result == (None, None)  # 模拟用户跳过选择

    def test_main_has_result_no_alias_search(self, patch_route):
        from gui import manhuagui_scan

        calls, dialog_results, mw = patch_route
        folder_info = {"series": "魔男伊奇", "aliases": [], "author": "作者"}
        result = manhuagui_scan._search_and_select_manhuagui(
            mw, "/fake/path", folder_info, None, None)
        assert calls == ["魔男伊奇"]  # 主词命中，不触发别名补搜
        assert not any("用别名" in item for item in mw.log_text.items)
        assert result == (None, None)

    def test_author_mismatch_filtered(self, monkeypatch):
        """问题2：主词搜到的结果若作者不匹配，不进入弹窗并继续别名补搜"""
        from gui import manhuagui_scan
        from processors import search_handler

        calls = []
        dialog_results = []

        def fake_route(keyword, folder_info, source="manhuagui"):
            calls.append(keyword)
            if keyword == "CLAMP学園探偵団":
                # 主词搜到 2 个结果，但作者均不是 CLAMP（作者被误当作品名）
                return [
                    {"id": "1", "name": "CLAMP学園探偵団", "url": "u1",
                     "author": "别家作者A"},
                    {"id": "2", "name": "CLAMP学園探偵団", "url": "u2",
                     "author": "别家作者B"},
                ]
            if keyword == "CLAMP":
                # 旧逻辑会用作者名 CLAMP 补搜；新逻辑应排除作者关键词
                return [{"id": "3", "name": "CLAMP学園探偵団", "url": "u3",
                         "author": "CLAMP"}]
            return []

        monkeypatch.setattr(search_handler, "search_manga", fake_route)
        monkeypatch.setattr(
            manhuagui_scan, "show_result_selection_dialog",
            lambda mw, results, folder_info, allow_id_search=True: (
                dialog_results.append(results) or None))
        # search_failure → 直接跳过，避免进 GUI
        monkeypatch.setattr(manhuagui_scan, "show_no_result_dialog",
                            lambda mw, folder_info, allow_id_search=False,
                                   id_search_kind="bangumi": None)

        class FakeLog:
            def __init__(self):
                self.items = []

            def append(self, s):
                self.items.append(s)

        mw = type("MW", (), {"log_text": FakeLog()})()
        folder_info = {"series": "CLAMP学園探偵団", "aliases": ["CLAMP"],
                       "author": "CLAMP"}
        result = manhuagui_scan._search_and_select_manhuagui(
            mw, "/fake/path", folder_info, None, None)
        # 作者名 CLAMP 不应作为搜索词；主词结果作者不匹配 → 无匹配 → 走 search_failure
        assert calls == ["CLAMP学園探偵団"]
        assert dialog_results == []
        assert result == (None, None)

    def test_author_matched_passes_to_dialog(self, monkeypatch):
        """主词结果含作者匹配项时，仅匹配项进入弹窗"""
        from gui import manhuagui_scan
        from processors import search_handler

        calls = []
        dialog_results = []

        def fake_route(keyword, folder_info, source="manhuagui"):
            calls.append(keyword)
            return [
                {"id": "1", "name": "CLAMP学園探偵団", "url": "u1",
                 "author": "CLAMP"},
                {"id": "2", "name": "CLAMP学園探偵団", "url": "u2",
                 "author": "别家作者B"},
            ]

        monkeypatch.setattr(search_handler, "search_manga", fake_route)
        monkeypatch.setattr(
            manhuagui_scan, "show_result_selection_dialog",
            lambda mw, results, folder_info, allow_id_search=True: (
                dialog_results.append(results) or None))

        class FakeLog:
            def __init__(self):
                self.items = []

            def append(self, s):
                self.items.append(s)

        mw = type("MW", (), {"log_text": FakeLog()})()
        folder_info = {"series": "CLAMP学園探偵団", "aliases": [],
                       "author": "CLAMP"}
        result = manhuagui_scan._search_and_select_manhuagui(
            mw, "/fake/path", folder_info, None, None)
        assert calls == ["CLAMP学園探偵団"]  # 不触发别名补搜
        assert len(dialog_results) == 1
        assert [r["id"] for r in dialog_results[0]] == ["1"]  # 不匹配项被过滤
        assert result == (None, None)
