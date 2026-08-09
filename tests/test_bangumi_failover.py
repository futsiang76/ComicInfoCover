#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bangumi 数据源直连与 v2 GET 搜索解析测试

覆盖：
- 按源直连：_api_base_for_source / _web_mirror_from_api 映射
- set_active_bangumi_source：切换模块级当前源，新 fetcher 默认跟随
- _request_json：直连所选源；失败即报错，不做自动 failover/重试
- v2 GET 搜索响应解析（_parse_search_response）：list 字段/字段映射/容错
- search_manga 走 v2 GET 路径与所选源参数
- get_manga_detail 直连所选源，失败返回 None
"""

from unittest.mock import MagicMock
from urllib.parse import quote

import requests

import pytest

import config
from models.bangumi_fetcher import (_api_base_for_source,
                                    _parse_search_response,
                                    _web_mirror_from_api, BangumiFetcher,
                                    set_active_bangumi_source)

OFFICIAL = "https://api.bgm.tv"
MIRROR1 = "https://api.bangumi.lol"
MIRROR2 = "https://bgmapi.anibt.net"


class JsonResponse:
    """模拟带 JSON 数据的 requests.Response"""

    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class TestSourceBaseMapping:
    """测试数据源标识 → API/网页域名映射"""

    def test_official_maps_to_bgm_api(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS",
                            [OFFICIAL, MIRROR1, MIRROR2])
        assert _api_base_for_source(config.BANGUMI_SOURCE_OFFICIAL) == OFFICIAL

    def test_mirror_maps_to_bangumi_lol(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS",
                            [OFFICIAL, MIRROR1, MIRROR2])
        assert _api_base_for_source(config.BANGUMI_SOURCE_MIRROR) == MIRROR1

    def test_unknown_source_falls_back_official(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS",
                            [OFFICIAL, MIRROR1])
        assert _api_base_for_source("manhuagui") == OFFICIAL

    def test_empty_mirrors_raises(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [])
        with pytest.raises(requests.exceptions.RequestException):
            _api_base_for_source(config.BANGUMI_SOURCE_OFFICIAL)

    def test_mirror_missing_falls_back_second_item(self, monkeypatch):
        """镜像域名不在列表时回退列表次项（官方取首项）"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR2])
        assert _api_base_for_source(config.BANGUMI_SOURCE_MIRROR) == MIRROR2

    def test_web_mirror_from_api(self):
        """API 域名 → 网页域名：去 api 前缀 / anibt 特殊规则"""
        assert _web_mirror_from_api(OFFICIAL) == "https://bgm.tv"
        assert _web_mirror_from_api(MIRROR1) == "https://bangumi.lol"
        assert _web_mirror_from_api(MIRROR2) == "https://bgmmi.anibt.net"


class TestActiveSource:
    """测试模块级当前源与 fetcher 默认跟随"""

    def test_default_source_is_official(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        set_active_bangumi_source(config.BANGUMI_SOURCE_OFFICIAL)
        fetcher = BangumiFetcher()
        assert fetcher._base_url == OFFICIAL
        assert fetcher._web_base == "https://bgm.tv"

    def test_set_mirror_then_new_fetcher_uses_mirror(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        set_active_bangumi_source(config.BANGUMI_SOURCE_MIRROR)
        fetcher = BangumiFetcher()
        assert fetcher._base_url == MIRROR1
        assert fetcher._web_base == "https://bangumi.lol"

    def test_invalid_source_resets_to_official(self, monkeypatch):
        """非 Bangumi 源标识按官方处理（防御性兜底）"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        set_active_bangumi_source(config.BANGUMI_SOURCE_MIRROR)
        set_active_bangumi_source("comicvine")
        assert BangumiFetcher()._base_url == OFFICIAL

    def test_explicit_source_constructor_arg(self, monkeypatch):
        """构造参数显式指定源优先于模块级当前源"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        set_active_bangumi_source(config.BANGUMI_SOURCE_OFFICIAL)
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_MIRROR)
        assert fetcher._base_url == MIRROR1


class TestRequestJsonDirectConnect:
    """测试 _request_json 按所选源直连、失败即报错"""

    @pytest.fixture(autouse=True)
    def _mirrors(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS",
                            [OFFICIAL, MIRROR1, MIRROR2])

    def test_official_source_uses_official_base(self):
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.session.request = MagicMock(return_value=JsonResponse({"ok": True}))
        assert fetcher._request_json("GET", "/v0/subjects/1") == {"ok": True}
        fetcher.session.request.assert_called_once()
        url = fetcher.session.request.call_args.args[1]
        assert url == f"{OFFICIAL}/v0/subjects/1"

    def test_mirror_source_uses_mirror_base(self):
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_MIRROR)
        fetcher.session.request = MagicMock(return_value=JsonResponse({"ok": True}))
        assert fetcher._request_json("GET", "/v0/subjects/1") == {"ok": True}
        url = fetcher.session.request.call_args.args[1]
        assert url == f"{MIRROR1}/v0/subjects/1"

    def test_official_fails_no_failover(self):
        """官方失败 → 立即抛错，只请求一次，不切镜像"""
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.session.request = MagicMock(
            side_effect=requests.exceptions.ConnectionError("blocked"))
        with pytest.raises(requests.exceptions.ConnectionError):
            fetcher._request_json("GET", "/search/subject/foo")
        fetcher.session.request.assert_called_once()

    def test_mirror_fails_no_failover(self):
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_MIRROR)
        fetcher.session.request = MagicMock(
            side_effect=requests.exceptions.Timeout("slow"))
        with pytest.raises(requests.exceptions.Timeout):
            fetcher._request_json("GET", "/search/subject/foo")
        fetcher.session.request.assert_called_once()

    def test_5xx_raises(self):
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.session.request = MagicMock(
            return_value=JsonResponse({}, status_code=503))
        with pytest.raises(requests.exceptions.HTTPError):
            fetcher._request_json("GET", "/search/subject/foo")
        fetcher.session.request.assert_called_once()


class TestParseSearchResponse:
    """测试 v2 GET 搜索响应解析（list 字段 + 字段映射）"""

    def test_list_field_is_items(self):
        """真实条目在 list 字段；results 是 int 总数"""
        data = {
            "results": 3,
            "list": [
                {"id": 1, "name": "作品A", "name_cn": "", "series": True},
                {"id": 2, "name": "作品B", "name_cn": "作品B中文", "series": False},
                {"id": 3, "name": "作品C", "name_cn": "", "series": False},
            ],
        }
        items = _parse_search_response(data)
        assert len(items) == 3
        assert items[0]["id"] == 1
        assert items[1]["name_cn"] == "作品B中文"
        assert items[0]["series"] is True

    def test_results_int_is_not_list(self):
        data = {"results": 2, "list": [{"id": 1}, {"id": 2}]}
        items = _parse_search_response(data)
        assert [i["id"] for i in items] == [1, 2]

    def test_missing_list_returns_empty(self):
        assert _parse_search_response({"results": 0}) == []
        assert _parse_search_response({}) == []

    def test_list_non_dict_items_skipped(self):
        data = {"results": 2, "list": [{"id": 1}, "junk", None, 3]}
        items = _parse_search_response(data)
        assert [i["id"] for i in items] == [1]

    def test_images_normalized(self):
        data = {"results": 1, "list": [{"id": 1, "name": "A"}]}
        items = _parse_search_response(data)
        assert items[0]["images"] == {}
        assert items[0]["images"].get("large") is None

    def test_field_mapping_keeps_summary_country(self):
        data = {"results": 1, "list": [{
            "id": 42, "name": "原作", "name_cn": "中文名",
            "summary": "简介", "country": "日本", "date": "2020-01-01",
            "volumes": 5, "infobox": [],
        }]}
        item = _parse_search_response(data)[0]
        assert item["summary"] == "简介"
        assert item["country"] == "日本"
        assert item["volumes"] == 5
        assert item["infobox"] == []


class TestSearchMangaV2Get:
    """测试 search_manga 走 v2 GET 端点与参数（直连所选源）"""

    def test_uses_v2_get_endpoint_official(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.get_manga_detail = MagicMock(return_value=None)

        def side_effect(method, url, **kwargs):
            assert method == "GET"
            assert url.startswith(OFFICIAL + "/search/subject/")
            assert kwargs["params"] == {"type": 1, "responseGroup": "small"}
            return JsonResponse({"results": 1, "list": [
                {"id": 10, "name": "测试作品", "name_cn": "", "series": True}]})

        fetcher.session.request = MagicMock(side_effect=side_effect)
        results = fetcher.search_manga("测试作品")
        assert [r["id"] for r in results] == [10]

    def test_mirror_source_search_uses_mirror_base(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_MIRROR)
        fetcher.get_manga_detail = MagicMock(return_value=None)
        urls = []

        def side_effect(method, url, **kwargs):
            urls.append(url)
            return JsonResponse({"results": 1, "list": [
                {"id": 20, "name": "测试作品", "name_cn": "", "series": True}]})

        fetcher.session.request = MagicMock(side_effect=side_effect)
        results = fetcher.search_manga("测试作品")
        assert [r["id"] for r in results] == [20]
        assert urls == [f"{MIRROR1}/search/subject/{quote('测试作品')}"]

    def test_mirror_failure_no_switch_to_official(self, monkeypatch):
        """镜像失败 → 搜索报错返回空，不自动切官方"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_MIRROR)
        fetcher.session.request = MagicMock(
            side_effect=requests.exceptions.ConnectionError("down"))
        assert fetcher.search_manga("测试作品") == []
        fetcher.session.request.assert_called_once()


class TestGetMangaDetailDirectConnect:
    """测试 get_manga_detail 直连所选源，失败返回 None"""

    def test_official_detail_uses_v0_path(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.session.request = MagicMock(return_value=JsonResponse(
            {"id": 5, "name": "作品", "name_cn": "", "series": True}))
        detail = fetcher.get_manga_detail(5)
        assert detail["id"] == 5
        url = fetcher.session.request.call_args.args[1]
        assert url == f"{OFFICIAL}/v0/subjects/5"

    def test_mirror_detail_uses_mirror_base(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_MIRROR)
        fetcher.session.request = MagicMock(return_value=JsonResponse(
            {"id": 6, "name": "作品", "name_cn": "", "series": True}))
        detail = fetcher.get_manga_detail(6)
        assert detail["id"] == 6
        url = fetcher.session.request.call_args.args[1]
        assert url == f"{MIRROR1}/v0/subjects/6"

    def test_detail_all_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.session.request = MagicMock(
            side_effect=requests.exceptions.ConnectionError("down"))
        assert fetcher.get_manga_detail(5) is None
