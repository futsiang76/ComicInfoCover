#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Bangumi 网页搜索兜底策略"""

import re
from unittest.mock import MagicMock, patch

import requests

from models.bangumi_fetcher import BangumiFetcher


class MockResponse:
    """模拟 requests.Response"""
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


class TestWebSearchSubjectIds:
    """测试 _web_search_subject_ids 提取逻辑"""

    def test_extracts_single_id(self):
        fetcher = BangumiFetcher()
        html = '<a href="/subject/12345">Test</a>'
        fetcher.session.get = MagicMock(return_value=MockResponse(html))
        ids = fetcher._web_search_subject_ids("test")
        assert ids == ["12345"]

    def test_extracts_multiple_ids(self):
        fetcher = BangumiFetcher()
        html = '''
        <a href="/subject/1">A</a>
        <a href="/subject/2">B</a>
        <a href="/subject/3">C</a>
        '''
        fetcher.session.get = MagicMock(return_value=MockResponse(html))
        ids = fetcher._web_search_subject_ids("test")
        assert ids == ["1", "2", "3"]

    def test_dedup_ids(self):
        fetcher = BangumiFetcher()
        html = '<a href="/subject/10">A</a><a href="/subject/10">B</a>'
        fetcher.session.get = MagicMock(return_value=MockResponse(html))
        ids = fetcher._web_search_subject_ids("test")
        assert ids == ["10"]

    def test_returns_empty_on_http_error(self):
        fetcher = BangumiFetcher()
        fetcher.session.get = MagicMock(return_value=MockResponse("", 500))
        ids = fetcher._web_search_subject_ids("test")
        assert ids == []

    def test_returns_empty_on_network_error(self):
        fetcher = BangumiFetcher()
        fetcher.session.get = MagicMock(
            side_effect=requests.exceptions.ConnectionError("timeout"))
        ids = fetcher._web_search_subject_ids("test")
        assert ids == []


class TestWebSearchFallback:
    """测试 _web_search_fallback 兜底策略"""

    def test_returns_empty_when_all_strategies_fail(self):
        fetcher = BangumiFetcher()
        fetcher._web_search_subject_ids = MagicMock(return_value=[])
        results = fetcher._web_search_fallback("作品名")
        assert results == []

    def test_stops_on_first_successful_strategy(self):
        fetcher = BangumiFetcher()
        # First strategy (书名) succeeds, shouldn't try others
        fetcher._web_search_subject_ids = MagicMock(return_value=["123"])
        fetcher.get_manga_detail = MagicMock(return_value={
            "name": "Test", "name_cn": "测试", "rating": {}
        })
        results = fetcher._web_search_fallback("作品名", author="作者名", alt_keywords=["别名"])
        assert len(results) == 1
        assert results[0]["id"] == 123
        # Only called once (first strategy) — not second or third
        assert fetcher._web_search_subject_ids.call_count == 1

    def test_tries_all_strategies_in_order(self):
        fetcher = BangumiFetcher()
        # First two strategies fail, third succeeds
        fetcher._web_search_subject_ids = MagicMock(side_effect=[
            [],  # 书名
            [],  # 书名+作者
            ["456"],  # 别名
        ])
        fetcher.get_manga_detail = MagicMock(return_value={
            "name": "Test", "name_cn": "测试", "rating": {}
        })
        results = fetcher._web_search_fallback("作品名", author="作者名", alt_keywords=["别名"])
        assert len(results) == 1
        assert results[0]["id"] == 456
        assert fetcher._web_search_subject_ids.call_count == 3

    def test_skip_strategy_when_author_equals_keyword(self):
        fetcher = BangumiFetcher()
        fetcher._web_search_subject_ids = MagicMock(return_value=["789"])
        fetcher.get_manga_detail = MagicMock(return_value={
            "name": "Test", "name_cn": "测试", "rating": {}
        })
        results = fetcher._web_search_fallback("作品", author="作品")
        # 书名+作者 strategy should be skipped because author == keyword
        # Only 书名 strategy should run
        assert len(results) == 1
        assert fetcher._web_search_subject_ids.call_count == 1

    def test_removes_special_characters_strategy(self):
        fetcher = BangumiFetcher()
        fetcher._web_search_subject_ids = MagicMock(side_effect=[
            [],  # 书名（含特殊符号）
            ["999"],  # 去除特殊符号
        ])
        fetcher.get_manga_detail = MagicMock(return_value={
            "name": "Test", "name_cn": "测试", "rating": {}
        })
        results = fetcher._web_search_fallback("作品★名♪")
        assert len(results) == 1
        assert fetcher._web_search_subject_ids.call_count == 2

    def test_cleaned_keyword_not_duplicate_of_original(self):
        """确保"去除特殊符号"策略只在清理后关键词与原关键词不同时触发"""
        fetcher = BangumiFetcher()
        fetcher._web_search_subject_ids = MagicMock(return_value=[])
        # 关键词不含特殊符号，不应该有"去除特殊符号"策略
        fetcher._web_search_fallback("普通书名")
        # Should have exactly 1 call (just 书名)
        assert fetcher._web_search_subject_ids.call_count == 1
