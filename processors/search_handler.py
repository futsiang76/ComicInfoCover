#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搜索处理器模块 - 负责Bangumi搜索相关功能
"""

import re
from typing import Dict, List, Optional, Tuple

from models.bangumi_fetcher import BangumiFetcher


class SearchHandler:
    """搜索处理器类"""
    
    def __init__(self, fetcher: BangumiFetcher):
        """初始化搜索处理器
        
        Args:
            fetcher: Bangumi获取器实例
        """
        self.fetcher = fetcher
    
    def extract_search_keywords(self, folder_path: str, folder_info: Dict) -> Tuple[List[str], List[str]]:
        """提取搜索关键词和别名
        
        Args:
            folder_path: 文件夹路径
            folder_info: 文件夹信息字典
            
        Returns:
            Tuple: (搜索关键词列表, 别名关键词列表)
        """
        search_keywords = []
        alt_keywords = []
        
        # 主要搜索：仅系列名
        search_keywords.append(folder_info['series'])
        
        # 别名处理
        if folder_info.get('aliases'):
            for alias in folder_info['aliases']:
                alt_keywords.append(alias)
        
        # 清理关键词：移除方括号和括号内的内容
        cleaned_search_keywords = []
        for keyword in search_keywords:
            cleaned_keyword = re.sub(r'\[.*?\]', '', keyword).strip()
            # 忽略大小写去重
            if cleaned_keyword and cleaned_keyword.lower() not in [kw.lower() for kw in cleaned_search_keywords]:
                cleaned_search_keywords.append(cleaned_keyword)
        
        # 清理别名关键词
        cleaned_alt_keywords = []
        for keyword in alt_keywords:
            cleaned_keyword = re.sub(r'\[.*?\]', '', keyword).strip()
            if cleaned_keyword and cleaned_keyword.lower() not in [kw.lower() for kw in cleaned_alt_keywords]:
                cleaned_alt_keywords.append(cleaned_keyword)
        
        return cleaned_search_keywords, cleaned_alt_keywords
    
    def search_with_keywords(self, keywords: List[str], folder_info: Optional[Dict] = None) -> List[Dict]:
        """使用关键词列表搜索Bangumi
        
        Args:
            keywords: 关键词列表
            folder_info: 文件夹信息（用于网页搜索兜底）
            
        Returns:
            List[Dict]: 搜索结果列表
        """
        search_results = []
        
        # 只使用第一个关键词（系列名）进行搜索
        if keywords:
            keyword = keywords[0]
            print(f"🔍 正在搜索Bangumi: {keyword}")
            temp_results = self.fetcher.search_manga(keyword, folder_info)
            if temp_results:
                search_results = temp_results
                print(f"✅ 使用系列名 '{keyword}' 找到 {len(search_results)} 个结果")
            else:
                print(f"❌ 系列名 '{keyword}' 未找到结果")
        
        return search_results
    
    def _extract_result_authors(self, result: Dict) -> List[str]:
        """从单个搜索结果提取 Bangumi 作者

        优先经详情接口 infobox 提取；为空（老条目 infobox 无作者字段）时
        兜底抓取网页信息栏提取作者。
        """
        detail = self.fetcher.get_manga_detail(result["id"])
        authors = self.fetcher.extract_bangumi_authors(detail) if detail else []
        if not authors:
            authors = self.fetcher.fetch_web_authors(result["id"])
        return authors

    def filter_matching_results(self, search_results: List[Dict], folder_info: Dict, 
                               author_match_threshold: float) -> List[Dict]:
        """过滤匹配的搜索结果
        
        Args:
            search_results: 搜索结果列表
            folder_info: 文件夹信息字典
            author_match_threshold: 作者匹配阈值
            
        Returns:
            List[Dict]: 匹配的搜索结果列表
        """
        from models.author_utils import filter_results_by_author
        return filter_results_by_author(
            search_results, folder_info["author"], self._extract_result_authors,
            threshold=author_match_threshold)

    def has_author_match(self, search_results: List[Dict], folder_info: Dict) -> bool:
        """检查搜索结果中是否有作者匹配

        Args:
            search_results: 搜索结果列表
            folder_info: 文件夹信息字典

        Returns:
            bool: 是否有作者匹配
        """
        from models.author_utils import filter_results_by_author
        return bool(filter_results_by_author(
            search_results, folder_info["author"], self._extract_result_authors))

    def search_by_id(self, subject_id: int) -> Optional[Dict]:
        """按Bangumi ID搜索
        
        Args:
            subject_id: Bangumi ID
            
        Returns:
            Optional[Dict]: 搜索结果或None
        """
        print(f"🔍 正在按Bangumi ID查找: {subject_id}")
        detail = self.fetcher.get_manga_detail(subject_id)
        if detail:
            result = {
                "id": subject_id,
                "name": detail.get("name", ""),
                "name_cn": detail.get("name_cn", ""),
                "rating": detail.get("rating", {})
            }
            print(f"  ✅ ID查找成功: {result.get('name_cn') or result.get('name')}")
            return result
        else:
            print(f"❌ 未找到ID为 {subject_id} 的作品")
            return None


def create_search_handler(fetcher: BangumiFetcher) -> SearchHandler:
    """创建搜索处理器实例
    
    Args:
        fetcher: Bangumi获取器实例
        
    Returns:
        SearchHandler: 搜索处理器实例
    """
    return SearchHandler(fetcher)


# ----------------------------------------------------------------------
# 数据源路由（用户主动选择 manhuagui / ComicVine 时使用）
# ----------------------------------------------------------------------
MANHUAGUI_SOURCE = "manhuagui"
COMICVINE_SOURCE = "comicvine"
BANGUMI_SOURCE = "bangumi"


def _to_manhuagui_result(item: Dict) -> Dict:
    """manhuagui 搜索结果 → 选择对话框兼容格式

    选择对话框要求 id/name/name_cn/rating 字段；额外保留 url/cover/author
    供详情页抓取使用。id 取详情页 URL 中的漫画数字ID，无则退回完整 URL。
    """
    url = item.get("url", "")
    match = re.search(r"/comic/(\d+)/", url)
    display_id = match.group(1) if match else url
    return {
        "id": display_id,
        "name": item.get("title", ""),
        "name_cn": item.get("title", ""),
        "url": url,
        "cover": item.get("cover", ""),
        "author": item.get("author", ""),
        "rating": {"score": "", "count": 0},
    }


def _to_comicvine_result(item: Dict) -> Dict:
    """ComicVine 搜索结果 → 选择对话框兼容格式

    选择对话框要求 id/name/name_cn/rating 字段；额外保留 url/cover/publisher/
    resource_type/start_year/count_of_issues 供详情抓取与结果展示使用。id 为
    资源数字 ID（详情 URL 前缀 4050-），resource_type 区分 series/volume 以决定
    详情端点（series→get_series_detail，volume→get_volume_detail）。
    """
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "name_cn": item.get("name", ""),
        "url": item.get("site_detail_url", ""),
        "cover": (item.get("image") or {}).get("original_url", ""),
        "publisher": (item.get("publisher") or {}).get("name", ""),
        "resource_type": item.get("resource_type", "volume"),
        "start_year": item.get("start_year"),
        "count_of_issues": item.get("count_of_issues"),
        "rating": {"score": "", "count": 0},
    }


def search_manga(keyword: str, folder_info: Optional[Dict] = None,
                 source: str = BANGUMI_SOURCE) -> List[Dict]:
    """按数据源路由搜索漫画

    Args:
        keyword: 搜索关键词（系列名）
        folder_info: 文件夹信息（Bangumi 网页搜索兜底使用）
        source: 数据源 'bangumi' | 'manhuagui' | 'comicvine'

    Returns:
        List[Dict]: 搜索结果列表；bangumi 含 id/name/name_cn/rating，
                    manhuagui 额外含 url/cover/author，comicvine 额外含
                    url/cover/publisher/resource_type/start_year/count_of_issues
    """
    if source == MANHUAGUI_SOURCE:
        from models.manhuagui_fetcher import ManhuaguiFetcher
        fetcher = ManhuaguiFetcher()
        try:
            raw_results = fetcher.search_manga(keyword)
            return [_to_manhuagui_result(item) for item in raw_results]
        finally:
            fetcher.close()
    if source == COMICVINE_SOURCE:
        from models.comicvine_fetcher import ComicVineFetcher
        fetcher = ComicVineFetcher()
        try:
            raw_results = fetcher.search_series_and_volumes(keyword)
            return [_to_comicvine_result(item) for item in raw_results]
        finally:
            fetcher.close()
    return BangumiFetcher().search_manga(keyword, folder_info)
