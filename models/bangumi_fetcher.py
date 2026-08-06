#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bangumi API封装模块 - 处理所有Bangumi相关功能
"""

import os
import re
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from thefuzz import fuzz
from zhconv import convert
import urllib3

from config import (AUTHOR_MATCH_THRESHOLD, BANGUMI_ACCESS_TOKEN,
                    FUZZ_THRESHOLD, MAX_RETRIES, SHOW_TOP_N, TIMEOUT)

# 禁用SSL警告（仅用于开发环境）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


from .author_utils import (_clean_author_name, _split_authors,
                            analyze_bangumi_author_types, extract_bangumi_authors,
                            extract_bangumi_authors_by_type, match_author)

# 可作 Genre 的 Bangumi tag 白名单（按分类聚合）
BANGUMI_GENRE_WHITELIST = {
    "分类": ["小说", "画集", "绘本", "公式书", "写真", "其他"],
    "来源": ["游戏改", "小说改", "动画改", "影视改"],  # 移除 原创、漫画改（非类别）
    "题材": ["热血", "冒险", "魔幻", "神鬼", "搞笑", "萌系", "爱情", "科幻", "魔法",
             "格斗", "武侠", "机战", "战争", "竞技", "体育", "校园", "生活", "励志",
             "历史", "伪娘", "宅男", "腐男", "腐女", "耽美", "百合", "后宫", "治愈",
             "美食", "推理", "悬疑", "恐怖", "四格", "职场", "侦探", "社会", "音乐",
             "舞蹈", "杂志", "黑道", "穿越", "玄幻", "惊悚", "乙女"],
    "受众": ["少年", "少女", "青年", "BL", "一般向", "GL", "名著", "儿童", "女性", "TL"],
}


def extract_bangumi_genre(detail: Dict) -> str:
    """从 Bangumi API tags 提取 Genre：与白名单比对，按 tags 出现顺序去重

    Returns:
        str: 命中白名单的标签，用 ", " 分隔；无命中返回空字符串
    """
    api_tags = [tag["name"] for tag in detail.get("tags", [])]
    genre = []
    seen = set()
    for tag in api_tags:
        if tag in seen:
            continue
        for category in BANGUMI_GENRE_WHITELIST.values():
            if tag in category:
                genre.append(tag)
                seen.add(tag)
                break
    return ", ".join(genre) if genre else ""


# 「卷号标记」正则：括号数字 / 中文卷册话 / 西文卷标记（不区分大小写）
# 注：中文卷册话用 [1-9]\d* 排除「第0卷」——第0卷属一卷全特殊卷（如 进击的巨人 第0卷），
# 按用户实测结论应保留，不视为系列单卷标记
_VOLUME_MARKER_RE = re.compile(
    r"[（(]\s*\d+\s*[）)]"            # 括号数字：(1) (2) （3）
    r"|第\s*[1-9]\d*\s*[卷册话]"       # 中文卷册话：第1卷 / 第2册 / 第3话
    r"|(?:vol\.?\s*\d+|#\d+|V\d+)",   # 西文卷标记：Vol.1 / Vol 1 / #1 / V1
    re.IGNORECASE,
)


def _has_volume_marker(name: str) -> bool:
    """判断名称是否带「卷号标记」（系列单卷的形态特征）

    匹配模式（name 或 name_cn 任一命中即算带标记）：
    - 括号数字：(1) (2) （3）
    - 中文卷册话：第1卷 / 第2册 / 第3话（第0卷不匹配，属一卷全特殊卷）
    - 西文卷标记：Vol.1 / Vol 1 / #1 / V1（不区分大小写）

    Args:
        name: 作品名称（name 或 name_cn）

    Returns:
        bool: True 表示名称带卷号标记
    """
    if not name:
        return False
    return bool(_VOLUME_MARKER_RE.search(name))


def _filter_series_volumes(items: List[Dict]) -> List[Dict]:
    """逐条过滤：剔除 series=False 且名称带「卷号标记」的系列单卷条目

    最终规则（用户拍板 2026-08-05，替代结果数阈值启发式）：
    - series=True（系列条目）→ 保留
    - series=False 且名称带卷号标记（系列的单卷）→ 过滤
    - series=False 但无卷号标记（外传/原画集/设定集/一卷全独立作品）→ 保留

    series 字段由搜索列表（v0/search/subjects）直接提供，无需调详情接口；
    每个条目独立判定，不依赖结果集大小。卷号标记见 _has_volume_marker。

    Args:
        items: 搜索结果列表（元素含 series/name/name_cn 字段）

    Returns:
        List[Dict]: 过滤后的结果列表
    """
    return [item for item in items
            if item.get("series", False) is not False
            or not (_has_volume_marker(item.get("name") or "")
                    or _has_volume_marker(item.get("name_cn") or ""))]


class BangumiFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=MAX_RETRIES))
        self.session.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        if BANGUMI_ACCESS_TOKEN:
            self.session.headers["Authorization"] = f"Bearer {BANGUMI_ACCESS_TOKEN}"
        
        # 禁用SSL证书验证（解决HTTPS连接问题）
        self.session.verify = False

    def search_manga(self, keyword: str, folder_info: Optional[Dict] = None) -> List[Dict]:
        """搜索漫画，返回所有匹配结果（前10个）"""
        try:
            keyword_cn = convert(keyword, "zh-cn")
            url = "https://api.bgm.tv/v0/search/subjects?limit=10"
            payload = {"keyword": keyword_cn, "filter": {"type": [1]}}  # 1=书籍/漫画
            
            response = self.session.post(
                url,
                json=payload,
                timeout=TIMEOUT
            )
            response.raise_for_status()
            results = response.json().get("data", [])

            # 逐条过滤：series=False 且名称带「卷号标记」的条目（系列的单卷）剔除；
            # 保留系列(series=True)、外传/原画集/设定集/一卷全(series=False 但无卷号标记)。
            # series 字段在搜索列表直接可用，无额外 API 请求，也不依赖结果数阈值。
            results = _filter_series_volumes(results)

            details_cache: Dict[int, Optional[Dict]] = {}  # 详情缓存：复用别名检查的详情，避免重复请求
            
            # 按作品名匹配度排序（忽略英文大小写）
            scored_results = []
            for item in results:
                title_cn = convert(item.get("name_cn", ""), "zh-cn")
                title_ori = convert(item.get("name", ""), "zh-cn")
                
                # 首先尝试主标题匹配
                main_score = max(
                    fuzz.ratio(title_cn.lower(), keyword_cn.lower()),
                    fuzz.partial_ratio(title_cn.lower(), keyword_cn.lower()),
                    fuzz.ratio(title_ori.lower(), keyword_cn.lower())
                )
                
                # 如果主标题匹配度不够，尝试匹配别名
                final_score = main_score
                if main_score < FUZZ_THRESHOLD:
                    # 获取作品详情以检查别名
                    try:
                        detail = self.get_manga_detail(item["id"])
                        details_cache[item["id"]] = detail
                        if detail:
                            # 从infobox中提取别名信息
                            infobox = detail.get("infobox", [])
                            for info_item in infobox:
                                if info_item.get("key") == "别名":
                                    aliases = info_item.get("value", [])
                                    if isinstance(aliases, list):
                                        for alias in aliases:
                                            if isinstance(alias, dict) and alias.get("v"):
                                                alias_text = convert(alias["v"], "zh-cn")
                                                alias_score = max(
                                                    fuzz.ratio(alias_text.lower(), keyword_cn.lower()),
                                                    fuzz.partial_ratio(alias_text.lower(), keyword_cn.lower())
                                                )
                                                if alias_score > final_score:
                                                    final_score = alias_score
                                                    print(f"💡 通过别名匹配: {alias_text} (匹配度: {final_score}%)")
                                    elif isinstance(aliases, str) and aliases.strip():
                                        alias_text = convert(aliases, "zh-cn")
                                        alias_score = max(
                                            fuzz.ratio(alias_text.lower(), keyword_cn.lower()),
                                            fuzz.partial_ratio(alias_text.lower(), keyword_cn.lower())
                                        )
                                        if alias_score > final_score:
                                            final_score = alias_score
                                            print(f"💡 通过别名匹配: {alias_text} (匹配度: {final_score}%)")
                                    break
                    except Exception as e:
                        print(f"⚠️  获取详情失败 [{item['id']}]: {str(e)[:30]}")
                
                if final_score >= FUZZ_THRESHOLD:
                    scored_results.append((final_score, item))
            
            # 按匹配度降序排列
            scored_results.sort(key=lambda x: x[0], reverse=True)

            api_results = [r[1] for r in scored_results[:SHOW_TOP_N]]

            # API 无结果时尝试网页搜索兜底
            if not api_results and folder_info:
                author = folder_info.get("author", "")
                aliases = folder_info.get("aliases", [])
                web_results = self._web_search_fallback(keyword, author, aliases)
                if web_results:
                    return web_results

            return api_results
        except Exception as e:
            print(f"🔴 搜索失败 [{keyword}]: {str(e)[:50]}")

            # API 异常时也尝试网页搜索兜底
            if folder_info:
                author = folder_info.get("author", "")
                aliases = folder_info.get("aliases", [])
                web_results = self._web_search_fallback(keyword, author, aliases)
                if web_results:
                    return web_results

            return []

    def _web_search_subject_ids(self, keyword: str, timeout: int = 10) -> list:
        """网页搜索 Bangumi，从搜索结果页提取 subject ID 列表"""
        try:
            from urllib.parse import quote
            url = f"https://bgm.tv/subject_search/{quote(keyword)}?cat=1"
            resp = self.session.get(url, timeout=timeout, verify=False)
            resp.raise_for_status()
            subject_ids = re.findall(r'href="/subject/(\d+)"', resp.text)
            seen = set()
            unique = []
            for sid in subject_ids:
                if sid not in seen:
                    seen.add(sid)
                    unique.append(sid)
            return unique
        except Exception as e:
            print(f"🔴 网页搜索失败 [{keyword}]: {str(e)[:50]}")
            return []

    def _web_search_fallback(self, keyword: str, author: str = "",
                              alt_keywords: list = None) -> List[Dict]:
        """网页搜索兜底策略：按优先级尝试多种搜索方式"""
        strategies = []

        # a. 书名直接搜索
        strategies.append(("书名", keyword))

        # b. 书名 + 作者名联合搜索
        if author and author != keyword:
            strategies.append(("书名+作者", f"{keyword} {author}"))

        # c. 别名搜索
        if alt_keywords:
            for alt in alt_keywords:
                if alt != keyword:
                    strategies.append(("别名", alt))

        # d. 去特殊符号再搜
        cleaned = re.sub(r'[★♪◆☆●◎◇□■△▲▽▼※〒→←↑↓♡♥]', '', keyword).strip()
        if cleaned and cleaned != keyword:
            strategies.append(("去除特殊符号", cleaned))

        for strategy_name, query in strategies:
            print(f"🔍 网页搜索 ({strategy_name}): {query}")
            ids = self._web_search_subject_ids(query)
            if not ids:
                continue
            results = []
            for sid in ids[:SHOW_TOP_N]:
                detail = self.get_manga_detail(int(sid))
                if detail:
                    results.append({
                        "id": int(sid),
                        "name": detail.get("name", ""),
                        "name_cn": detail.get("name_cn", ""),
                        "series": detail.get("series", False),  # 详情接口同样带 series，供统一过滤
                        "rating": detail.get("rating", {})
                    })
            # 与 API 搜索统一：逐条过滤 series=False 且名称带卷号标记的条目
            results = _filter_series_volumes(results)
            if results:
                print(f"✅ 网页搜索 ({strategy_name}) 找到 {len(results)} 个结果")
                return results
            else:
                print(f"⚠️ 网页搜索 ({strategy_name}) 找到 ID 但获取详情失败")

        return []

    def get_manga_detail(self, subject_id: int) -> Optional[Dict]:
        """获取漫画详细信息（含作者、出版社等）"""
        try:
            url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
            response = self.session.get(url, timeout=TIMEOUT, verify=False)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.SSLError as e:
            print(f"🔴 SSL证书验证失败 [{subject_id}]: {str(e)[:50]}")
            print(f"💡 提示：已禁用SSL验证，如果问题持续，请检查网络连接或代理设置")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"🔴 网络连接失败 [{subject_id}]: {str(e)[:50]}")
            print(f"💡 提示：请检查网络连接、DNS解析或防火墙设置")
            return None
        except requests.exceptions.Timeout as e:
            print(f"🔴 请求超时 [{subject_id}]: {str(e)[:50]}")
            print(f"💡 提示：网络响应过慢，请检查网络状态")
            return None
        except Exception as e:
            print(f"🔴 获取详情失败 [{subject_id}]: {str(e)[:50]}")
            return None


    def extract_bangumi_authors(self, detail: Dict) -> List[str]:
        """包装方法：委托到 author_utils"""
        from .author_utils import extract_bangumi_authors as _extract
        return _extract(detail)

    def extract_bangumi_authors_by_type(self, detail: Dict) -> Dict[str, List[str]]:
        """包装方法：委托到 author_utils"""
        from .author_utils import extract_bangumi_authors_by_type as _extract_by_type
        return _extract_by_type(detail)

    def match_author(self, folder_author: str, bangumi_authors: List[str]) -> bool:
        """包装方法：委托到 author_utils"""
        from .author_utils import match_author as _match
        return _match(folder_author, bangumi_authors)


    def extract_comicinfo(self, detail: Dict, folder_info: Dict) -> Dict:
        """提取ComicInfo.xml所需字段"""
        # 获取不同类型的作者信息
        author_types = extract_bangumi_authors_by_type(detail)
        
        # 正确定义角色分类 - Bangumi中的"作者"实际上是作画者
        story_roles = ["原作", "监督", "监制", "脚本", "导演", "原著"]  # 故事创作者
        art_roles = ["作者", "作画", "制作", "插画", "绘制"]        # 绘画创作者
        
        # 按角色分类收集
        story_authors = []  # 故事相关（Writer）
        art_authors = []    # 绘画相关（Penciller）
        
        for role_type, authors in author_types.items():
            if role_type in story_roles:
                story_authors.extend(authors)
            elif role_type in art_roles:
                art_authors.extend(authors)
        
        # 去重
        story_authors = list(dict.fromkeys(story_authors))
        art_authors = list(dict.fromkeys(art_authors))
        
        # 应用规则
        if len(story_authors) == 0 and len(art_authors) == 0:
            # 没有任何作者信息，使用文件夹作者
            writer_str = folder_info["author"]
            penciller_str = ""
            author_str = folder_info["author"]
        elif len(story_authors) == 0 and len(art_authors) > 0:
            # 只有绘画作者（包括Bangumi的"作者"），全部放入Writer，Penciller留空
            writer_str = ", ".join(art_authors)
            penciller_str = ""
            author_str = ", ".join(art_authors)
        elif len(story_authors) > 0 and len(art_authors) == 0:
            # 只有故事作者，全部放入Writer，Penciller留空
            writer_str = ", ".join(story_authors)
            penciller_str = ""
            author_str = ", ".join(story_authors)
        else:
            # 同时有故事作者和绘画作者，分别放入对应字段
            writer_str = ", ".join(story_authors)
            penciller_str = ", ".join(art_authors)
            author_str = ", ".join(story_authors)  # Author字段优先使用故事作者

        # 根据完结状态决定Volume字段
        # 如果已完结，填写总卷数；如果连载中，留空
        volume_value = str(folder_info["total_volumes"]) if folder_info["complete"] else ""

        # 基础信息
        info = {
            "Title": folder_info["series"],
            "Series": folder_info["series"],
            "Count": volume_value,  # 已完结填写总卷数，连载中留空
            "Volume": "",  # 单本书的卷数将在后续处理中填充
            "Author": author_str,
            "Writer": writer_str,
            "Penciller": penciller_str,
            "Publisher": "",
            "Summary": "",
            "Tags": "",
            "Genre": extract_bangumi_genre(detail),
            "LanguageISO": "zh-CN",
            "Format": "Zip",
            "Status": "Completed" if folder_info["complete"] else "Ongoing",
            "Web": f"https://bgm.tv/subject/{detail.get('id', '')}",
        }
        
        # 对于画集、设定集、番外等非单行本内容，清空Count和Volume字段
        if folder_info.get("is_non_volume", False):
            info["Count"] = ""
            info["Volume"] = ""
        
        # 补充简介（清理HTML标签）
        summary = detail.get("summary", "")
        if summary:
            clean_summary = re.sub(r'<.*?>', '', summary).strip()
            # 如果已完结，在summary最后添加"已完结"标记
            if folder_info["complete"]:
                if clean_summary:
                    clean_summary = f"{clean_summary}\n已完结。"
                else:
                    clean_summary = "已完结。" # 如果简介为空，直接设置为"已完结。"
            info["Summary"] = clean_summary

        # 补充标签：命中 Genre 白名单的词从 Tags 移除，避免与 Genre 重复
        genre_tags = set(extract_bangumi_genre(detail).split(", "))
        tags = [tag["name"] for tag in detail.get("tags", []) if tag.get("count", 0) >= 2][:10]
        tags = [t for t in tags if t not in genre_tags]
        tags = [t for t in tags if not re.match(r"^\d+$", t)]  # 去掉纯数字（如 2024）
        remaining = list(tags)
        remaining.append(info["Status"])
        info["Tags"] = ",".join(dict.fromkeys(remaining))  # 去重（保留顺序）

        # 补充出版社
        for item in detail.get("infobox", []):
            if item.get("key") == "出版社":
                value = item.get("value", "")
                if isinstance(value, list):
                    info["Publisher"] = ",".join([v.get("v", "") for v in value if v.get("v")])
                else:
                    info["Publisher"] = value.strip()
                break

