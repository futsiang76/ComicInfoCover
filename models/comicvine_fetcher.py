#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComicVine 漫画数据抓取器（requests 直连 API，无浏览器依赖）

用户主动选择 ComicVine 数据源时使用，抓取欧美漫画元数据，支持 series（系列）与
volume（卷）双粒度：搜索时两资源合并返回（每条带 resource_type 标注），详情按
资源类型走 /series/4075-{id}/ 或 /volume/4050-{id}/。
API 文档: https://comicvine.gamespot.com/api/documentation
- 搜索: /api/search/?api_key=KEY&format=json&resources=series|volume&query={keyword}
- 详情: /api/series/4075-{id}/ 或 /api/volume/4050-{id}/?api_key=KEY&format=json
（注意 series 与 volume 的资源前缀不同：series=4075-，volume=4050-，以搜索返回的 api_detail_url 为准）
响应: {"status_code": 1=OK, "error": ..., "results": [...]}；100=Invalid API Key
速率限制: 200 请求/小时/资源；连接/网络类错误不重试，报回即止。
注意: volume 详情默认不含 person_credits（该字段在 issue 资源上），role 映射对
缺失数据安全降级——Writer/Penciller/Colorist 留空，由 XML 模板用文件夹作者兜底。
"""

import unicodedata
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from thefuzz import fuzz

import config

BASE_URL = "https://comicvine.gamespot.com/api"


def _get_api_key() -> str:
    """返回 ComicVine API Key；未配置时打印提示并返回空串

    Key 从 config.COMICVINE_API_KEY 读取（config 启动加载时已做
    user_config.json 主源 → secrets.py legacy 降级），设置对话框
    保存后下一次请求即生效。两个源都未配置时返回空串，不崩溃。
    """
    api_key = (config.COMICVINE_API_KEY or "").strip()
    if not api_key:
        print("⚠️   ComicVine API Key 未配置，请到「设置」中填写后重试")
    return api_key

# person_credits role → ComicInfo 字段映射（其余 role 忽略）
ROLE_FIELD_MAP = {
    "writer": "Writer",
    "penciller": "Penciller",
    "colorist": "Colorist",
}


def _normalize_for_match(text: str) -> str:
    """变音符号归一：NFD 分解后移除组合字符（Mn 类），José→Jose

    只用于比对归一（搜索排序/匹配），不改变原始数据。
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").lower()


class ComicVineFetcher:
    """ComicVine 数据抓取器（requests 直连，无 Playwright 依赖）

    搜索同时请求 series+volume 两资源并合并（每条带 resource_type 标注）；
    详情按资源类型映射为 ComicInfo 字段字典（volume 含角色字段，series 无）。
    """

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ComicInfoScratcher/1.0 (comic metadata fetcher)"

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def search_series_and_volumes(self, keyword: str) -> List[Dict]:
        """按关键词同时搜索系列（series）与卷（volume），合并返回

        文件夹粒度可能是整个系列也可能是单卷，两资源一起搜让用户在结果弹窗中
        按标注的类型自然选择。每条结果带 resource_type 字段（'series'/'volume'），
        series 结果排在 volume 之前。

        Args:
            keyword: 搜索关键词（系列名）

        Returns:
            list[dict]: series + volume 混合原始结果（含 id/name/publisher/
                        start_year/resource_type 等，由调用方转为选择对话框格式）；
                        未找到或请求失败时为空列表（网络类错误不重试，报回即止）
        """
        results = []
        api_key = _get_api_key()
        if not api_key:
            return []
        for resource in ("series", "volume"):
            url = (f"{BASE_URL}/search/?api_key={api_key}"
                   f"&format=json&resources={resource}&query={quote(keyword)}")
            data = self._get_json(url)
            if not data:
                continue
            items = data.get("results")
            if not isinstance(items, list):
                continue
            for item in items:
                item["resource_type"] = resource
                results.append(item)
        # 按关键词模糊匹配度降序排序（fuzz.ratio，精确匹配排最前，部分匹配排后）。
        # 比对前做变音符号归一（José→Jose），只影响排序不改变原始数据。
        # 只排序不过滤——保留全部结果供用户选择；同匹配度保持原顺序（series 在前）。
        keyword_norm = _normalize_for_match(keyword)
        results.sort(
            key=lambda item: fuzz.ratio(keyword_norm, _normalize_for_match(item.get("name") or "")),
            reverse=True,
        )
        return results

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def get_volume_detail(self, volume_id: int) -> Dict:
        """按 volume ID 抓取详情，映射为 ComicInfo 兼容字段字典

        Args:
            volume_id: ComicVine volume ID（数字部分，如 29996，URL 前缀 4050-）

        Returns:
            dict: ComicInfo 字段字典（见 _build_comic_info）；请求失败/ID 无效
                  时返回空 dict
        """
        api_key = _get_api_key()
        if not api_key:
            return {}
        url = f"{BASE_URL}/volume/4050-{volume_id}/?api_key={api_key}&format=json"
        data = self._get_json(url)
        if not data:
            return {}
        results = data.get("results")
        if isinstance(results, list):
            results = results[0] if results else {}
        if not isinstance(results, dict):
            return {}
        return self._build_comic_info(results)

    def get_series_detail(self, series_id: int) -> Dict:
        """按 series ID 抓取详情，映射为 ComicInfo 兼容字段字典

        Args:
            series_id: ComicVine series ID（数字部分，如 31，URL 前缀 4075-，
                       与 volume 的 4050- 不同，见搜索结果 api_detail_url）

        Returns:
            dict: ComicInfo 字段字典（见 _build_series_info）；请求失败/ID 无效
                  时返回空 dict
        """
        api_key = _get_api_key()
        if not api_key:
            return {}
        url = f"{BASE_URL}/series/4075-{series_id}/?api_key={api_key}&format=json"
        data = self._get_json(url)
        if not data:
            return {}
        results = data.get("results")
        if isinstance(results, list):
            results = results[0] if results else {}
        if not isinstance(results, dict):
            return {}
        return self._build_series_info(results)

    @staticmethod
    def _build_comic_info(volume: Dict) -> Dict:
        """将 volume 资源 JSON 映射为 ComicInfo 兼容字段（仅保留有值字段）

        映射: name→Title/Series、count_of_issues→Count、publisher.name→Publisher、
        start_year→Year、deck→Summary、site_detail_url→Web、
        person_credits 按 role→Writer/Penciller/Colorist、aliases→Tags。
        """
        comic_info = {
            "Title": volume.get("name", ""),
            "Series": volume.get("name", ""),
            "Count": str(volume.get("count_of_issues") or ""),
            "Publisher": (volume.get("publisher") or {}).get("name", ""),
            "Year": str(volume.get("start_year") or ""),
            "Summary": volume.get("deck", "") or "",
            "Web": volume.get("site_detail_url", "") or "",
        }
        comic_info.update(ComicVineFetcher._extract_credits(volume))
        aliases = volume.get("aliases")
        if aliases:
            alias_list = [a.strip() for a in str(aliases).split("\n") if a.strip()]
            if alias_list:
                comic_info["Tags"] = ", ".join(alias_list)
        return {key: value for key, value in comic_info.items() if value}

    @staticmethod
    def _build_series_info(series: Dict) -> Dict:
        """将 series 资源 JSON 映射为 ComicInfo 兼容字段（仅保留有值字段）

        与 volume 映射（_build_comic_info）的差异：series 无 person_credits
        （角色在 issue 资源层），Count 取 volume_count（系列下卷数，如有）。

        Args:
            series: ComicVine series 资源 dict（详情接口返回）

        Returns:
            dict: ComicInfo 字段字典（仅含非空字段）
        """
        comic_info = {
            "Title": series.get("name", ""),
            "Series": series.get("name", ""),
            "Count": str(series.get("volume_count") or ""),
            "Publisher": (series.get("publisher") or {}).get("name", ""),
            "Year": str(series.get("start_year") or ""),
            "Summary": series.get("deck", "") or "",
            "Web": series.get("site_detail_url", "") or "",
        }
        aliases = series.get("aliases")
        if aliases:
            alias_list = [a.strip() for a in str(aliases).split("\n") if a.strip()]
            if alias_list:
                comic_info["Tags"] = ", ".join(alias_list)
        return {key: value for key, value in comic_info.items() if value}

    @staticmethod
    def _extract_credits(volume: Dict) -> Dict:
        """从 person_credits 按 role 提取 Writer/Penciller/Colorist（其余 role 忽略）

        Args:
            volume: ComicVine volume 资源 dict

        Returns:
            dict: {Writer/Penciller/Colorist: "名字, 名字"}，无命中返回空 dict
        """
        fields = {}
        for credit in volume.get("person_credits") or []:
            role = str(credit.get("role") or "").strip().lower()
            target = ROLE_FIELD_MAP.get(role)
            if not target:
                continue
            name = str(credit.get("name") or "").strip()
            if not name:
                continue
            names = [n.strip() for n in fields.get(target, "").split(",") if n.strip()]
            if name not in names:
                names.append(name)
            fields[target] = ", ".join(names)
        return fields

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _get_json(self, url: str) -> Optional[Dict]:
        """GET 请求并校验 ComicVine 响应；失败返回 None（网络类错误不重试）

        Args:
            url: 完整 API URL

        Returns:
            dict: 响应 JSON；请求异常/状态码非 1 时返回 None
        """
        try:
            response = self.session.get(url, timeout=config.TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"🔴 ComicVine 请求失败: {str(e)[:120]}")
            return None
        except ValueError as e:
            print(f"🔴 ComicVine 响应解析失败: {str(e)[:120]}")
            return None
        if data.get("status_code") != 1:
            if data.get("status_code") == 100:
                print("🔴 ComicVine API Key 无效（status_code=100），请检查设置中的 ComicVine API Key")
            else:
                print(f"🔴 ComicVine API 错误 (status_code={data.get('status_code')}): "
                      f"{str(data.get('error'))[:120]}")
            return None
        return data

    # ------------------------------------------------------------------
    # 资源释放
    # ------------------------------------------------------------------
    def close(self) -> None:
        """关闭底层 HTTP 会话"""
        self.session.close()
