#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集成测试：作者不匹配时 process_normal_folder 触发放宽逻辑

bug 根因：放宽逻辑插在 filter_matching_results 之后（~143-149 行），却被
`if not has_author_match`（~120 行）的 early return 挡住——作者不匹配时先走
失败流程 return，放宽从未触发。

修复后 process_normal_folder 三条路径：
  1) 作者匹配      → 正常作者过滤（filter_matching_results 被调用）
  2) 作者不匹配    → 放宽 → 有结果 → 正常单选/多选弹窗（select_result）
  3) 放宽后仍 0 结果 → 失败流程（handle_no_author_match）
"""

from unittest.mock import MagicMock

import config
import processors.scan_processors as sp


def _comic(item_id, name):
    """漫画系列结果项（relax 排序优先级最高）"""
    return {"id": item_id, "name": name, "name_cn": name,
            "series": True, "platform": "漫画"}


def _patch_handlers(monkeypatch, search_handler, match_failure_handler, template_handler):
    monkeypatch.setattr(sp, "create_search_handler", lambda fetcher: search_handler)
    monkeypatch.setattr(
        sp, "create_match_failure_handler", lambda fetcher: match_failure_handler)
    monkeypatch.setattr(sp, "create_xml_template_handler", lambda: template_handler)


def _make_harness(monkeypatch, search_handler, match_failure_handler, template_handler):
    monkeypatch.setattr(config, "AUTO_TURBO_MATCH", 0)  # 走 GUI 弹窗分支，不自动跳过
    _patch_handlers(monkeypatch, search_handler, match_failure_handler, template_handler)
    fetcher = MagicMock()
    fetcher.get_manga_detail.return_value = {"id": 1, "infobox": []}
    return fetcher


class TestProcessAuthorRelaxIntegration:
    def test_author_match_filters_normally(self, monkeypatch):
        """路径1：作者匹配 → 正常作者过滤 → 单选弹窗"""
        results = [_comic(1, "作品A")]
        search_handler = MagicMock()
        search_handler.extract_search_keywords.return_value = (["系列"], [])
        search_handler.search_with_keywords.return_value = results
        search_handler.has_author_match.return_value = True
        search_handler.filter_matching_results.return_value = results
        match_failure_handler = MagicMock()
        template_handler = MagicMock()
        template_handler.create_bangumi_template.return_value = {"xml": True}
        fetcher = _make_harness(monkeypatch, search_handler,
                                match_failure_handler, template_handler)

        captured = {}

        def gui_callback(action, **kw):
            captured["action"] = action
            captured["search_results"] = kw["search_results"]
            return kw["search_results"][0]

        out = sp.process_normal_folder(
            "C:/fakepath/dir", {"series": "系列", "author": "作者"},
            fetcher, gui_callback=gui_callback)

        search_handler.filter_matching_results.assert_called_once()
        assert captured["action"] == "select_result"
        assert out["selected_result"]["id"] == 1
        assert out["skip_files"] is False

    def test_author_not_match_relaxes_and_shows_picker(self, monkeypatch):
        """路径2（原 bug 场景）：作者不匹配 → 不走作者过滤 → 放宽 → 单选弹窗"""
        results = [_comic(1, "作品A"), _comic(2, "作品B"), _comic(3, "作品C")]
        search_handler = MagicMock()
        search_handler.extract_search_keywords.return_value = (["系列"], ["别名"])
        search_handler.search_with_keywords.return_value = results
        search_handler.has_author_match.return_value = False   # 作者不匹配
        match_failure_handler = MagicMock()
        template_handler = MagicMock()
        template_handler.create_bangumi_template.return_value = {"xml": True}
        fetcher = _make_harness(monkeypatch, search_handler,
                                match_failure_handler, template_handler)

        captured = {}

        def gui_callback(action, **kw):
            captured["action"] = action
            captured["search_results"] = kw["search_results"]
            return kw["search_results"][0]

        out = sp.process_normal_folder(
            "C:/fakepath/dir", {"series": "系列", "author": "不匹配作者"},
            fetcher, gui_callback=gui_callback)

        # 作者不匹配：绝不调用作者过滤
        search_handler.filter_matching_results.assert_not_called()
        # 放宽结果进入选择器
        assert captured["action"] == "select_result"
        assert [r["id"] for r in captured["search_results"]] == [1, 2, 3]
        # 正常返回选中结果，未走失败处理器
        assert out["selected_result"]["id"] == 1
        assert out["skip_files"] is False
        match_failure_handler.handle_no_author_match.assert_not_called()

    def test_author_not_match_relax_empty_goes_failure(self, monkeypatch):
        """路径3：作者不匹配且放宽后仍 0 结果 → 失败流程"""
        from models import author_utils
        monkeypatch.setattr(author_utils, "relax_author_filter",
                            lambda search_results, **kw: [])
        results = [_comic(1, "作品A")]
        search_handler = MagicMock()
        search_handler.extract_search_keywords.return_value = (["系列"], [])
        search_handler.search_with_keywords.return_value = results
        search_handler.has_author_match.return_value = False
        match_failure_handler = MagicMock()
        match_failure_handler.handle_no_author_match.return_value = \
            {"comic_info_base": None, "selected_result": None, "skip_files": True}
        template_handler = MagicMock()
        fetcher = _make_harness(monkeypatch, search_handler,
                                match_failure_handler, template_handler)

        # 无 GUI 回调（CLI 模式）：0 结果走 handle_no_author_match 失败流程
        out = sp.process_normal_folder(
            "C:/fakepath/dir", {"series": "系列", "author": "不匹配作者"},
            fetcher, gui_callback=None)

        search_handler.filter_matching_results.assert_not_called()
        # 0 结果未进选择逻辑，直接落入失败流程
        match_failure_handler.handle_no_author_match.assert_called_once()
        assert out["skip_files"] is True
