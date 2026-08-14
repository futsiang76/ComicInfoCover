#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manhuagui 漫画数据抓取器（Playwright 无头浏览器）

用户主动选择 manhuagui 数据源时使用。
依赖：playwright + chromium（首次使用自动安装，见 models/manhuagui_deps.py）。
playwright 仅在搜索/抓取时惰性导入，因此本模块在依赖未安装时也可正常导入。
"""

import re
from typing import Dict, List, Optional
from urllib.parse import quote

from zhconv import convert


class ManhuaguiFetcher:
    """manhuagui 漫画数据抓取器（Playwright 无头浏览器，绕过反爬）

    搜索页：https://www.manhuagui.com/s/all-{keyword}-0-0-0-0-0-0-0-0.html
    详情页：https://www.manhuagui.com/comic/{id}/

    站点结构可能调整，解析采用多选择器兜底，失败时返回空结果而不是抛异常。
    """

    base_url = "https://www.manhuagui.com"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    NAV_TIMEOUT = 30000   # 页面加载超时（毫秒）
    WAIT_TIMEOUT = 15000  # 等待选择器出现超时（毫秒）

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def _ensure_browser(self) -> None:
        """惰性启动无头浏览器（首次搜索/详情时初始化）"""
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=self.USER_AGENT,
            locale="zh-CN",
            extra_http_headers={
                "Referer": self.base_url,
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        self._page = self._context.new_page()

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def search_manga(self, keyword: str) -> list[dict]:
        """搜索漫画，返回 [{title, url, cover, author, intro}]，失败返回 []

        站点标题繁简不确定（如「列印」vs「打印」），因此原词与简体转换词
        各搜一次，合并结果按 url 去重（保留先原词后简体的顺序）。

        Args:
            keyword: 搜索关键词（系列名）

        Returns:
            list[dict]: 搜索结果列表；全部变体均未找到或抓取失败时为空列表
        """
        variants = []
        for v in (keyword, convert(keyword, "zh-cn")):  # 原词 + 繁转简
            if v and v not in variants:
                variants.append(v)
        if not variants:
            return []

        merged = []  # 合并结果（按 url 去重，保序）
        seen_urls = set()
        for variant in variants:
            for item in self._search_variant(variant):
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    merged.append(item)
        return merged

    def _search_variant(self, keyword: str) -> list[dict]:
        """按单个关键词搜索；无结果或失败返回 []，不抛异常

        单个变体失败（goto 失败 / wait_for_selector 超时）由调用方捕获继续。
        """
        try:
            self._ensure_browser()
            url = f"{self.base_url}/s/{quote(keyword)}.html"
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            # 等待结果列表出现；搜索无结果时页面不含 li.cf，也会超时后走 except 返回 []
            self._page.wait_for_selector("li.cf", timeout=self.WAIT_TIMEOUT)
            results = []
            for item in self._page.query_selector_all("li.cf"):
                parsed = self._parse_search_item(item)
                if parsed:
                    results.append(parsed)
            return results
        except Exception as e:
            print(f"🔴 manhuagui 搜索失败 [{keyword}]: {str(e)[:100]}")
            return []

    def _parse_search_item(self, item) -> Optional[dict]:
        """从搜索列表项解析 {title, url, cover, author}；解析失败返回 None

        兼容多种结构：bcover 链接 + bcont 内容块，标题/作者选择器均有兜底。
        """
        link = item.query_selector("a.bcover") or item.query_selector("h3 a") or item.query_selector("a")
        if link is None:
            return None
        href = (link.get_attribute("href") or "").strip()
        # 标题：优先 a[title]，其次 img[alt]，最后文本
        title = (link.get_attribute("title") or "").strip()
        if not title:
            img = link.query_selector("img")
            title = (img.get_attribute("alt") if img else "") or ""
            title = title.strip()
        if not title:
            title = (link.inner_text() or "").strip()
        if not title or not href:
            return None
        if href.startswith("/"):
            href = self.base_url + href
        return {
            "title": title,
            "url": href,
            "cover": self._extract_cover(item),
            "author": self._extract_author(item),
            "intro": self._extract_intro(item),
        }

    def _extract_cover(self, item) -> str:
        """提取封面图地址（兼容 data-src 懒加载）"""
        img = item.query_selector("img")
        if img is None:
            return ""
        cover = img.get_attribute("data-src") or img.get_attribute("src") or ""
        return cover.strip()

    def _extract_author(self, item) -> str:
        """提取搜索项作者文本（dd.tags 内「作者：」后的链接，逗号分隔）

        真实结构：<dd class="tags"><span><strong>作者：</strong>
        <a href="/author/4793/" title="one">one</a>,<a ...>村田雄介</a></span></dd>
        """
        for dd in (item.query_selector_all(".book-detail dd") or []):
            strong = dd.query_selector("strong")
            if strong and "作者" in (strong.inner_text() or ""):
                authors = []
                for a in (dd.query_selector_all("a") or []):
                    name = (a.get_attribute("title") or a.inner_text() or "").strip()
                    if name:
                        authors.append(name)
                return ", ".join(authors)
        return ""

    def _extract_intro(self, item) -> str:
        """提取搜索项简介（dd.intro 内「简介：」后的文本）"""
        dd = item.query_selector("dd.intro")
        if dd is None:
            return ""
        text = (dd.inner_text() or "").strip()
        # 去掉「简介：」前缀和末尾的 [详情]
        text = re.sub(r"^简介\s*[:：]?\s*", "", text)
        text = re.sub(r"\[详情\]$", "", text).strip()
        return text

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def get_manga_detail(self, url: str) -> dict:
        """抓取详情页，返回 ComicInfo 兼容 dict {Title, Series, Author, Summary, ...}

        Args:
            url: 详情页地址（来自搜索结果）

        Returns:
            dict: ComicInfo 字段字典；抓取失败返回空 dict
        """
        try:
            self._ensure_browser()
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.NAV_TIMEOUT)
            self._page.wait_for_timeout(800)  # 等待动态内容渲染
            return self._parse_detail_page()
        except Exception as e:
            print(f"🔴 manhuagui 详情抓取失败 [{url}]: {str(e)[:100]}")
            return {}

    def _parse_detail_page(self) -> dict:
        """解析详情页为 ComicInfo 兼容 dict，仅保留有值的字段

        真实结构：.book-detail > .book-title > h1(标题)/h2(副标题)
        ul.detail-list > li > span > strong(标签名) + a(值)
        简介：.intro 文本
        """
        title = self._text("h1") or self._text("title")
        if not title:
            return {}

        author = ""
        genre = ""
        year = ""
        aliases = []
        for row in (self._page.query_selector_all(".book-detail .detail-list li") or []):
            for span in (row.query_selector_all("span") or []):
                strong = span.query_selector("strong")
                if strong is None:
                    continue
                label = (strong.inner_text() or "").strip()
                value_links = (span.query_selector_all("a") or [])
                values = [ (v.get_attribute("title") or v.inner_text() or "").strip()
                           for v in value_links ]
                values = [v for v in values if v]
                if not values:
                    continue
                if "作者" in label and not author:
                    author = ", ".join(values)
                elif "剧情" in label or "题材" in label:
                    genre = ", ".join(values)
                elif "年代" in label:
                    year = values[0]
                elif "别名" in label:
                    aliases.extend(values)

        # 简介：.intro 文本（去掉「展开详情」尾巴）
        summary = self._text(".intro") or self._text("#intro-all") or self._text(".book-intro")
        summary = re.sub(r"\s*展开详情\s*$", "", summary).strip()

        # 标题：中文 h1 + 别名（英文/日文）拼进 Title/Series
        alt_title = aliases[0] if aliases else ""
        subtitle = self._text(".book-title h2")  # 副标题为另一个翻译（中文/英文），优先作为 LocalizedTitle
        # h2 清洗后也作为别名进 Tags：去首尾空白与横杠（'-'/'—'/'- ' 等），与 title/详情别名去重
        h2_alias = re.sub(r"^[-—\s]+|[-—\s]+$", "", subtitle or "").strip()
        if h2_alias and h2_alias != title and h2_alias not in aliases:
            aliases.insert(0, h2_alias)
        localized_title = subtitle if subtitle and subtitle != title else alt_title

        comic_info = {
            "Title": title,
            "Series": title,
            "Writer": author,
            "Penciller": author,
            "Summary": summary,
            "Genre": genre or "漫画",
            "Tags": ", ".join(aliases),
            "Publisher": "",
            "Year": year,
            "Web": self._page.url,
        }
        if localized_title:
            comic_info["LocalizedTitle"] = localized_title
        return {key: value for key, value in comic_info.items() if value}

    def _text(self, selector: str) -> str:
        """获取页面中第一个匹配元素的文本，无匹配返回空字符串"""
        element = self._page.query_selector(selector)
        return (element.inner_text() or "").strip() if element else ""

    @staticmethod
    def _clean_author(value: str) -> str:
        """manhuagui 作者字段清洗：去前缀，按分隔符拆分为标准格式"""
        value = re.sub(r"^作者\s*[:：]?\s*", "", value.strip())
        parts = re.split(r"[/、,，]", value)
        return ", ".join(part.strip() for part in parts if part.strip())

    # ------------------------------------------------------------------
    # 资源释放
    # ------------------------------------------------------------------
    def close(self) -> None:
        """关闭浏览器实例"""
        for obj, name in ((self._context, "context"),
                          (self._browser, "browser"),
                          (self._playwright, "playwright")):
            if obj is None:
                continue
            try:
                close_fn = obj.stop if name == "playwright" else obj.close
                close_fn()
            except Exception as e:
                print(f"⚠️ manhuagui 关闭 {name} 时出错: {str(e)[:80]}")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
