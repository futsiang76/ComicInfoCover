#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bangumi 数据源直连与 v0 POST 搜索解析测试

覆盖：
- 按源直连：_api_base_for_source / _web_mirror_from_api 映射
- set_active_bangumi_source：切换模块级当前源，新 fetcher 默认跟随
- _request_json：直连所选源；失败即报错，不做自动 failover/重试
- v0 POST 搜索响应解析（data 字段）：search_manga 走 POST /v0/search/subjects
- get_manga_detail 直连所选源，失败返回 None
"""

from unittest.mock import MagicMock

import requests

import pytest

import config
from models.bangumi_fetcher import (_api_base_for_source,
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
            fetcher._request_json("GET", "/v0/search/subjects")
        fetcher.session.request.assert_called_once()

    def test_mirror_fails_no_failover(self):
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_MIRROR)
        fetcher.session.request = MagicMock(
            side_effect=requests.exceptions.Timeout("slow"))
        with pytest.raises(requests.exceptions.Timeout):
            fetcher._request_json("GET", "/v0/search/subjects")
        fetcher.session.request.assert_called_once()

    def test_5xx_raises(self):
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.session.request = MagicMock(
            return_value=JsonResponse({}, status_code=503))
        with pytest.raises(requests.exceptions.HTTPError):
            fetcher._request_json("GET", "/v0/search/subjects")
        fetcher.session.request.assert_called_once()


class TestSearchMangaV0Post:
    """测试 search_manga 走 v0 POST /v0/search/subjects 端点与参数（直连所选源）

    v0 POST response: {"data": [...]} - series/platform/images 由接口直接提供
    """

    def test_uses_v0_post_endpoint_official(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.get_manga_detail = MagicMock(return_value=None)

        def side_effect(method, url, **kwargs):
            assert method == "POST"
            assert url == OFFICIAL + "/v0/search/subjects"
            assert kwargs["params"] == {"limit": 10}
            assert kwargs["json"] == {
                "keyword": "测试作品", "filter": {"type": [1]}}
            return JsonResponse({"data": [
                {"id": 10, "name": "测试作品", "name_cn": "", "series": True}]})

        fetcher.session.request = MagicMock(side_effect=side_effect)
        results = fetcher.search_manga("測試作品")  # 繁体输入 → payload 简体
        assert [r["id"] for r in results] == [10]

    def test_v0_data_field_is_items(self, monkeypatch):
        """真实条目在 data 字段；series/platform 直接可用"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.get_manga_detail = MagicMock(return_value=None)
        fetcher.session.request = MagicMock(return_value=JsonResponse({
            "data": [
                {"id": 1, "name": "作品A", "name_cn": "作品A", "series": True,
                 "platform": "漫画"},
                {"id": 2, "name": "作品B", "name_cn": "作品B",
                 "series": False, "platform": "漫画"},
            ]}))
        results = fetcher.search_manga("作品")
        assert len(results) == 2
        assert results[0]["series"] is True
        assert results[0]["platform"] == "漫画"

    def test_missing_data_returns_empty(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.get_manga_detail = MagicMock(return_value=None)
        fetcher.session.request = MagicMock(return_value=JsonResponse({}))
        assert fetcher.search_manga("测试作品") == []

    def test_images_field_kept(self, monkeypatch):
        """v0 POST 直接提供 images（镜像已重写域名），无需归一"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.get_manga_detail = MagicMock(return_value=None)
        fetcher.session.request = MagicMock(return_value=JsonResponse({
            "data": [{"id": 1, "name": "作品A", "name_cn": "",
                      "images": {"large": "https://lain.bangumi.lol/a.jpg"}}]}))
        results = fetcher.search_manga("作品A")
        assert results[0]["images"]["large"] == "https://lain.bangumi.lol/a.jpg"

    def test_data_non_dict_items_skipped(self, monkeypatch):
        """data 内非 dict 条目跳过，仅保留 dict"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.get_manga_detail = MagicMock(return_value=None)
        fetcher.session.request = MagicMock(return_value=JsonResponse({
            "data": [{"id": 1, "name": "作品A", "name_cn": "作品A",
                      "series": True}, "junk", None, 3]}))
        results = fetcher.search_manga("作品")
        assert [r["id"] for r in results] == [1]

    def test_total_field_ignored(self, monkeypatch):
        """v0 POST 响应含 total 总数，真实条目只在 data"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.get_manga_detail = MagicMock(return_value=None)
        fetcher.session.request = MagicMock(return_value=JsonResponse({
            "total": 100, "data": [
                {"id": 1, "name": "作品A", "name_cn": "作品A", "series": True},
                {"id": 2, "name": "作品B", "name_cn": "作品B", "series": False},
            ]}))
        results = fetcher.search_manga("作品")
        assert [r["id"] for r in results] == [1, 2]

    def test_field_mapping_keeps_summary_country(self, monkeypatch):
        """v0 POST 条目保留 summary/country/date/volumes/infobox 等字段"""
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_OFFICIAL)
        fetcher.get_manga_detail = MagicMock(return_value=None)
        fetcher.session.request = MagicMock(return_value=JsonResponse({
            "data": [{
                "id": 42, "name": "原作", "name_cn": "原作",
                "summary": "简介", "country": "日本", "date": "2020-01-01",
                "volumes": 5, "infobox": [], "series": True,
            }]}))
        item = fetcher.search_manga("原作")[0]
        assert item["summary"] == "简介"
        assert item["country"] == "日本"
        assert item["volumes"] == 5
        assert item["infobox"] == []

    def test_mirror_source_search_uses_mirror_base(self, monkeypatch):
        monkeypatch.setattr(config, "BANGUMI_MIRRORS", [OFFICIAL, MIRROR1])
        fetcher = BangumiFetcher(source=config.BANGUMI_SOURCE_MIRROR)
        fetcher.get_manga_detail = MagicMock(return_value=None)
        urls = []

        def side_effect(method, url, **kwargs):
            urls.append(url)
            return JsonResponse({"data": [
                {"id": 20, "name": "测试作品", "name_cn": "", "series": True}]})

        fetcher.session.request = MagicMock(side_effect=side_effect)
        results = fetcher.search_manga("测试作品")
        assert [r["id"] for r in results] == [20]
        assert urls == [f"{MIRROR1}/v0/search/subjects"]

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
