#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Bangumi 网页作者兜底提取（API infobox 无作者 → 网页信息栏提取）

背景：老条目 37953（CLAMP学園探偵団）API infobox 无「作者」字段，但网页版
信息栏有 `作者: <a href="/person/39">CLAMP</a>`。修复后 _extract_result_authors
在 API 提取为空时兜底抓网页提取作者，避免被无作者过滤逻辑剔除。
"""

from unittest.mock import MagicMock

import requests

from models.bangumi_fetcher import BangumiFetcher, _parse_web_authors
from processors.search_handler import SearchHandler


# 37953 真实网页信息栏结构（老条目：API 无作者，网页有）
CLAMP_PAGE_HTML = """\
<ul id="infobox">
  <li class=""><span class="tip">中文名: </span>CLAMP学園探偵団</li>
  <li class=""><span class="tip">册数: </span>3卷完</li>
  <li class=""><span class="tip">作者: </span><a href="/person/39" class="l">CLAMP</a></li>
  <li class=""><span class="tip">出版社: </span><a href="/person/518" class="l" title="角川书店">角川書店</a></li>
  <li class=""><span class="tip">连载杂志: </span>月刊<a href="/person/8516" class="l">ASUKA</a>、<a href="/person/50835" class="l">ミステリーDX</a></li>
  <li class=""><span class="tip">发售日: </span>1992-04-01</li>
  <li class=""><span class="tip">开始: </span>1992年1月号</li>
  <li class=""><span class="tip">结束: </span>1993年10月号</li>
</ul>"""


class MockResponse:
    """模拟 requests.Response"""

    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


class EncodingAwareResponse:
    """模拟 bgm.tv 响应（头无 charset）：requests 默认按 ISO-8859-1 解码，
    设置 .encoding 后才按指定编码返回 .text。用于复现/防止编码回归。"""

    def __init__(self, content, status_code=200):
        self._content = content
        self._encoding = "ISO-8859-1"
        self.status_code = status_code

    @property
    def encoding(self):
        return self._encoding

    @encoding.setter
    def encoding(self, value):
        self._encoding = value

    @property
    def text(self):
        return self._content.decode(self._encoding, errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


class TestParseWebAuthors:
    """测试 _parse_web_authors 纯 HTML 解析"""

    def test_single_author(self):
        html = '<span class="tip">作者: </span><a href="/person/39" class="l">CLAMP</a>'
        assert _parse_web_authors(html) == ["CLAMP"]

    def test_clamp_real_page(self):
        assert _parse_web_authors(CLAMP_PAGE_HTML) == ["CLAMP"]

    def test_multiple_authors_in_one_field(self):
        html = ('<span class="tip">作者: </span>'
                '<a href="/person/1" class="l">A</a>、'
                '<a href="/person/2" class="l">B</a>')
        assert _parse_web_authors(html) == ["A", "B"]

    def test_multiple_tip_fields(self):
        html = ('<span class="tip">作者: </span><a href="/person/39">CLAMP</a>'
                '<span class="tip">原作: </span><a href="/person/40">原作者</a>')
        assert _parse_web_authors(html) == ["CLAMP", "原作者"]

    def test_non_author_tips_ignored(self):
        html = ('<span class="tip">出版社: </span><a href="/person/518">角川書店</a>'
                '<span class="tip">连载杂志: </span>'
                '月刊<a href="/person/8516">ASUKA</a>、<a href="/person/50835">ミステリーDX</a>')
        assert _parse_web_authors(html) == []

    def test_author_field_without_person_link(self):
        html = '<span class="tip">作者: </span>佚名'
        assert _parse_web_authors(html) == []

    def test_empty_html(self):
        assert _parse_web_authors("") == []
        assert _parse_web_authors(None) == []

    def test_dedup(self):
        html = ('<span class="tip">作者: </span><a href="/person/39">CLAMP</a>'
                '<span class="tip">作画: </span><a href="/person/39">CLAMP</a>')
        assert _parse_web_authors(html) == ["CLAMP"]


class TestFetchWebAuthors:
    """测试 fetch_web_authors（mock 网络）"""

    def test_clamp_from_mocked_html(self):
        fetcher = BangumiFetcher()
        fetcher.session.get = MagicMock(return_value=MockResponse(CLAMP_PAGE_HTML))
        assert fetcher.fetch_web_authors(37953) == ["CLAMP"]

    def test_utf8_decoding_when_header_missing_charset(self):
        # 回归：bgm.tv 响应头无 charset，requests 默认按 ISO-8859-1 解码会乱码，
        # fetch_web_authors 必须显式指定 utf-8 才能匹配到中文 tip 字段
        fetcher = BangumiFetcher()
        fetcher.session.get = MagicMock(
            return_value=EncodingAwareResponse(CLAMP_PAGE_HTML.encode("utf-8")))
        assert fetcher.fetch_web_authors(37953) == ["CLAMP"]

    def test_returns_empty_on_http_error(self):
        fetcher = BangumiFetcher()
        fetcher.session.get = MagicMock(return_value=MockResponse("", 500))
        assert fetcher.fetch_web_authors(37953) == []

    def test_returns_empty_on_network_error(self):
        fetcher = BangumiFetcher()
        fetcher.session.get = MagicMock(
            side_effect=requests.exceptions.ConnectionError("timeout"))
        assert fetcher.fetch_web_authors(37953) == []

    def test_cache_same_id_fetches_once(self):
        fetcher = BangumiFetcher()
        fetcher.session.get = MagicMock(return_value=MockResponse(CLAMP_PAGE_HTML))
        assert fetcher.fetch_web_authors(37953) == ["CLAMP"]
        assert fetcher.fetch_web_authors(37953) == ["CLAMP"]
        assert fetcher.session.get.call_count == 1

    def test_cache_failure_not_retried(self):
        fetcher = BangumiFetcher()
        fetcher.session.get = MagicMock(return_value=MockResponse("", 500))
        assert fetcher.fetch_web_authors(37953) == []
        assert fetcher.fetch_web_authors(37953) == []
        # 失败也缓存：同一 subject_id 只抓取一次（失败即静默降级，不重试）
        assert fetcher.session.get.call_count == 1


class TestExtractResultAuthorsFallback:
    """测试 _extract_result_authors：API 无作者 → 网页兜底"""

    @staticmethod
    def _make_handler(detail, web_authors):
        fetcher = BangumiFetcher()
        fetcher.get_manga_detail = MagicMock(return_value=detail)
        fetcher.fetch_web_authors = MagicMock(return_value=web_authors)
        return SearchHandler(fetcher)

    def test_api_empty_uses_web_fallback(self):
        handler = self._make_handler({"infobox": []}, ["CLAMP"])
        authors = handler._extract_result_authors({"id": 37953})
        assert authors == ["CLAMP"]
        handler.fetcher.fetch_web_authors.assert_called_once_with(37953)

    def test_api_no_detail_uses_web_fallback(self):
        handler = self._make_handler(None, ["CLAMP"])
        authors = handler._extract_result_authors({"id": 37953})
        assert authors == ["CLAMP"]

    def test_api_has_authors_no_web_fetch(self):
        detail = {"infobox": [{"key": "作者", "value": [{"v": "CLAMP"}]}]}
        handler = self._make_handler(detail, [])
        authors = handler._extract_result_authors({"id": 378339})
        assert authors == ["CLAMP"]
        handler.fetcher.fetch_web_authors.assert_not_called()


class TestFilterMatchingResultsIntegration:
    """集成：37953 无 API 作者经网页兜底后保留在结果中（3 条都保留）"""

    def test_clamp_all_three_kept(self):
        fetcher = BangumiFetcher()
        results = [
            {"id": 37953, "name": "CLAMP学園探偵団"},
            {"id": 378339, "name": "CLAMP学園探偵団 完全版"},
            {"id": 378727, "name": "CLAMP学園探偵団 愛蔵版"},
        ]
        no_author_detail = {"infobox": [{"key": "中文名", "value": "CLAMP学園探偵団"}]}
        with_author_detail = {"infobox": [{"key": "作者", "value": [{"v": "CLAMP"}]}]}
        fetcher.get_manga_detail = MagicMock(side_effect=[
            no_author_detail,     # 37953：API 无作者 → 网页兜底
            with_author_detail,   # 378339
            with_author_detail,   # 378727
        ])
        fetcher.fetch_web_authors = MagicMock(return_value=["CLAMP"])
        handler = SearchHandler(fetcher)
        matched = handler.filter_matching_results(results, {"author": "CLAMP"}, 70)
        assert [r["id"] for r in matched] == [37953, 378339, 378727]
        fetcher.fetch_web_authors.assert_called_once_with(37953)
