"""ComicVine 数据源测试 — URL 构造 / 字段映射 / 结果路由（不测网络）"""
import config
import pytest
import requests

from models.comicvine_fetcher import ComicVineFetcher


@pytest.fixture(autouse=True)
def _use_dummy_api_key():
    """提供非空 API Key，保证请求能走到 FakeSession（不依赖真实配置）"""
    config.COMICVINE_API_KEY = "test_api_key"
    yield
    config.apply_settings(config.DEFAULT_SETTINGS)


class FakeResponse:
    """伪造 requests.Response：raise_for_status 无操作，json 返回预设 payload"""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """伪造 requests.Session：记录最近 URL，可配置抛错"""

    def __init__(self, payload=None, exc=None):
        self.payload = payload
        self.exc = exc
        self.last_url = None

    def get(self, url, timeout=None):
        self.last_url = url
        if self.exc is not None:
            raise self.exc
        return FakeResponse(self.payload)


class FakeSessionByResource:
    """伪造 requests.Session：按 URL 中 resources= 参数分别返回 series/volume 结果"""

    def __init__(self, series_payload=None, volume_payload=None):
        self.series_payload = series_payload
        self.volume_payload = volume_payload
        self.last_urls = []

    def get(self, url, timeout=None):
        self.last_urls.append(url)
        if "resources=series" in url:
            return FakeResponse(self.series_payload)
        return FakeResponse(self.volume_payload)


# ----------------------------------------------------------------------
# _build_comic_info 字段映射
# ----------------------------------------------------------------------

def _sample_volume():
    """构造一个覆盖全部映射字段的 ComicVine volume 资源 dict"""
    return {
        "name": "Batman",
        "id": 29996,
        "count_of_issues": 12,
        "start_year": 2016,
        "publisher": {"name": "DC Comics"},
        "deck": "The Dark Knight returns to Gotham.",
        "site_detail_url": "https://comicvine.gamespot.com/batman/4050-29996/",
        "person_credits": [
            {"name": "Tom King", "role": "writer"},
            {"name": "David Finch", "role": "penciller"},
            {"name": "Jordie Bellaire", "role": "colorist"},
            {"name": "Mikel Janin", "role": "inker"},
            {"name": "John Doe", "role": "editor"},
        ],
        "aliases": "Batman (2016)\nThe Dark Knight",
    }


def _sample_series():
    """构造一个覆盖 series 映射字段的 ComicVine series 资源 dict

    真实 API 实测：series 详情无 count_of_issues/volume_count（只有
    count_of_episodes 剧集数，与漫画期数无关），故样本不含计数字段。
    """
    return {
        "name": "Batman",
        "id": 31,
        "start_year": 1966,
        "publisher": {"name": "DC Comics"},
        "deck": "The adventures of Batman.",
        "site_detail_url": "https://comicvine.gamespot.com/batman/4075-31/",
        "aliases": "The Dark Knight\nBruce Wayne",
    }


def test_build_comic_info_field_mapping():
    """字段映射：name→Series/Title、count→Count、publisher→Publisher、
    start_year→Year、deck→Summary、site_detail_url→Web、roles→Writer/Penciller/Colorist"""
    info = ComicVineFetcher._build_comic_info(_sample_volume())
    assert info["Series"] == "Batman"
    assert info["Title"] == "Batman"
    assert info["Count"] == "12"
    assert info["Publisher"] == "DC Comics"
    assert info["Year"] == "2016"
    assert info["Summary"] == "The Dark Knight returns to Gotham."
    assert info["Web"] == "https://comicvine.gamespot.com/batman/4050-29996/"
    assert info["Writer"] == "Tom King"
    assert info["Penciller"] == "David Finch"
    assert info["Colorist"] == "Jordie Bellaire"
    # inker/editor 不在映射内，不出现
    assert "Mikel Janin" not in str(info)
    assert info["Tags"] == "Batman (2016), The Dark Knight"


def test_build_comic_info_dedup_and_skip_empty():
    """同 role 多人去重合并；空值字段被剔除；无 person_credits 不报错"""
    volume = _sample_volume()
    volume["person_credits"] = [
        {"name": "Tom King", "role": "writer"},
        {"name": "Tom King", "role": "writer"},   # 重复名只保留一次
        {"name": "Scott Snyder", "role": "writer"},
    ]
    info = ComicVineFetcher._build_comic_info(volume)
    assert info["Writer"] == "Tom King, Scott Snyder"
    # 空字段剔除：deck 置空后 Summary 键不存在
    volume["deck"] = ""
    info = ComicVineFetcher._build_comic_info(volume)
    assert "Summary" not in info
    # 无 person_credits 键
    del volume["person_credits"]
    info = ComicVineFetcher._build_comic_info(volume)
    assert "Writer" not in info


def test_build_comic_info_missing_optional_fields():
    """publisher 为 None / aliases 缺失 / count 为 0 时安全降级"""
    volume = {"name": "Watchmen", "publisher": None, "count_of_issues": 0,
              "person_credits": None}
    info = ComicVineFetcher._build_comic_info(volume)
    assert info["Series"] == "Watchmen"
    assert "Publisher" not in info
    assert "Count" not in info
    assert "Tags" not in info


# ----------------------------------------------------------------------
# URL 构造（session.get 打桩，不发起真实网络请求）
# ----------------------------------------------------------------------

def test_search_series_and_volumes_urls_and_merge(monkeypatch):
    """双资源搜索：series+volume 各发一次请求，结果合并且每条带 resource_type，series 在前"""
    fetcher = ComicVineFetcher()
    series_item = {"id": 31, "name": "Batman", "start_year": 1966}
    volume_item = {"id": 126840, "name": "Batman", "count_of_issues": 1287,
                   "start_year": 1954}
    session = FakeSessionByResource(
        series_payload={"status_code": 1, "error": "OK", "results": [series_item]},
        volume_payload={"status_code": 1, "error": "OK", "results": [volume_item]},
    )
    fetcher.session = session
    results = fetcher.search_series_and_volumes("Batman")
    assert len(session.last_urls) == 2
    assert "api_key=" in session.last_urls[0] and "format=json" in session.last_urls[0]
    assert "resources=series" in session.last_urls[0]
    assert "resources=volume" in session.last_urls[1]
    assert "query=Batman" in session.last_urls[0]
    assert "query=Batman" in session.last_urls[1]
    assert [r["resource_type"] for r in results] == ["series", "volume"]
    assert results[0]["id"] == 31
    assert results[1]["id"] == 126840


def test_search_series_and_volumes_partial_failure(monkeypatch):
    """单资源请求失败不阻断另一资源：volume 结果仍返回并标注 resource_type"""
    fetcher = ComicVineFetcher()
    session = FakeSessionByResource(
        series_payload={"status_code": 101, "error": "Object Not Found"},
        volume_payload={"status_code": 1, "error": "OK",
                        "results": [{"id": 126840, "name": "Batman"}]},
    )
    fetcher.session = session
    results = fetcher.search_series_and_volumes("Batman")
    assert len(results) == 1
    assert results[0]["id"] == 126840
    assert results[0]["resource_type"] == "volume"


def test_normalize_for_match_strips_diacritics():
    """变音符号归一：José→jose、lópez→lopez，仅影响比对不影响原始数据"""
    from models.comicvine_fetcher import _normalize_for_match

    assert _normalize_for_match("José") == "jose"
    assert _normalize_for_match("José lópez") == "jose lopez"
    assert _normalize_for_match("Ünïcödé") == "unicode"
    assert _normalize_for_match("Batman") == "batman"


def test_search_sort_diacritics_normalized(monkeypatch):
    """搜索排序：关键词 Jose 与结果 José 视为相同（变音归一），精确匹配排最前"""
    fetcher = ComicVineFetcher()
    session = FakeSessionByResource(
        series_payload={"status_code": 1, "error": "OK",
                        "results": [{"id": 1, "name": "José"}]},
        volume_payload={"status_code": 1, "error": "OK",
                        "results": [{"id": 2, "name": "Unrelated"}]},
    )
    fetcher.session = session
    results = fetcher.search_series_and_volumes("Jose")
    assert results[0]["name"] == "José"      # 归一后精确匹配排最前
    assert results[1]["name"] == "Unrelated"
    # 原始数据未被改写
    assert results[0]["name"] == "José"


def test_get_volume_detail_url_and_mapping(monkeypatch):
    """详情 URL 为 /volume/4050-{id}/，返回字段已映射为 ComicInfo 格式"""
    fetcher = ComicVineFetcher()
    session = FakeSession(payload={"status_code": 1, "error": "OK",
                                   "results": _sample_volume()})
    fetcher.session = session
    info = fetcher.get_volume_detail(29996)
    assert "/volume/4050-29996/" in session.last_url
    assert info["Series"] == "Batman"
    assert info["Count"] == "12"
    assert info["Web"] == "https://comicvine.gamespot.com/batman/4050-29996/"


def test_get_volume_detail_list_results(monkeypatch):
    """详情接口 results 为单元素列表时取第一个"""
    fetcher = ComicVineFetcher()
    session = FakeSession(payload={"status_code": 1, "error": "OK",
                                   "results": [_sample_volume()]})
    fetcher.session = session
    info = fetcher.get_volume_detail(29996)
    assert info["Series"] == "Batman"


def test_get_series_detail_url_and_mapping(monkeypatch):
    """series 详情 URL 前缀为 4075-（与 volume 的 4050- 不同），字段映射为 ComicInfo 格式"""
    fetcher = ComicVineFetcher()
    session = FakeSession(payload={"status_code": 1, "error": "OK",
                                   "results": _sample_series()})
    fetcher.session = session
    info = fetcher.get_series_detail(31)
    assert "/series/4075-31/" in session.last_url
    assert info["Series"] == "Batman"
    assert info["Title"] == "Batman"
    assert info["Year"] == "1966"
    assert info["Publisher"] == "DC Comics"
    assert info["Web"] == "https://comicvine.gamespot.com/batman/4075-31/"
    assert info["Tags"] == "The Dark Knight, Bruce Wayne"
    assert "Count" not in info   # series 详情无 count_of_issues/volume_count（实测）
    assert "Writer" not in info  # series 无 person_credits


def test_build_series_info_uses_volume_count():
    """series 若带 volume_count 则映射为 Count（API 暂不返回，防御性保留）"""
    series = _sample_series()
    series["volume_count"] = 99
    info = ComicVineFetcher._build_series_info(series)
    assert info["Count"] == "99"


# ----------------------------------------------------------------------
# 错误处理（不重试，报回即止）
# ----------------------------------------------------------------------

def test_invalid_api_key_returns_empty(monkeypatch):
    """status_code=100（Invalid API Key）→ 搜索 [] / 详情 {}，并提示检查 key"""
    fetcher = ComicVineFetcher()
    fetcher.session = FakeSession(payload={"status_code": 100,
                                           "error": "Invalid API Key"})
    assert fetcher.search_series_and_volumes("Batman") == []
    assert fetcher.get_volume_detail(29996) == {}
    assert fetcher.get_series_detail(31) == {}


def test_network_error_returns_empty(monkeypatch):
    """连接类错误（ConnectionError/DNS）→ 空结果，不抛异常、不重试"""
    fetcher = ComicVineFetcher()
    fetcher.session = FakeSession(exc=requests.exceptions.ConnectionError("DNS failure"))
    assert fetcher.search_series_and_volumes("Batman") == []
    fetcher.session = FakeSession(exc=requests.exceptions.Timeout("timed out"))
    assert fetcher.get_volume_detail(29996) == {}
    assert fetcher.get_series_detail(31) == {}


def test_non_ok_status_returns_empty(monkeypatch):
    """其他非 1 状态码（如 101 Object Not Found）→ 空结果"""
    fetcher = ComicVineFetcher()
    fetcher.session = FakeSession(payload={"status_code": 101, "error": "Object Not Found"})
    assert fetcher.search_series_and_volumes("Batman") == []
    assert fetcher.get_volume_detail(999999) == {}
    assert fetcher.get_series_detail(999999) == {}


# ----------------------------------------------------------------------
# 结果路由与选择对话框格式
# ----------------------------------------------------------------------

def test_to_comicvine_result():
    """搜索结果转换为选择对话框兼容格式（id/name/name_cn/url/rating + resource_type）"""
    from processors.search_handler import _to_comicvine_result
    result = _to_comicvine_result(_sample_volume())
    assert result["id"] == 29996
    assert result["name"] == "Batman"
    assert result["name_cn"] == "Batman"
    assert result["url"] == "https://comicvine.gamespot.com/batman/4050-29996/"
    assert result["publisher"] == "DC Comics"
    assert result["rating"] == {"score": "", "count": 0}
    # 无 resource_type 字段时默认 volume（兼容旧数据）
    assert result["resource_type"] == "volume"
    assert result["start_year"] == 2016
    assert result["count_of_issues"] == 12


def test_to_comicvine_result_series():
    """series 搜索结果保留 resource_type=series 与年份，无 count_of_issues"""
    from processors.search_handler import _to_comicvine_result
    item = {"id": 31, "name": "Batman", "resource_type": "series", "start_year": 1966}
    result = _to_comicvine_result(item)
    assert result["resource_type"] == "series"
    assert result["start_year"] == 1966
    assert result["count_of_issues"] is None


def test_format_result_display_comicvine():
    """comicvine 结果标注类型：series→（系列）+年份，volume→（卷）+年份+期数"""
    from gui.gui_dialogs import _format_result_display
    series = {"id": 31, "name": "Batman", "name_cn": "Batman",
              "resource_type": "series", "start_year": 1966}
    assert _format_result_display(series) == "[31] 📚 Batman（系列） 1966"
    volume = {"id": 126840, "name": "Batman", "name_cn": "Batman",
              "resource_type": "volume", "start_year": 1954, "count_of_issues": 1287}
    assert _format_result_display(volume) == "[126840] 📚 Batman（卷） 1954 1287期"
    # 无年份/期数时只显示类型标注
    bare = {"id": 1, "name": "X", "name_cn": "X", "resource_type": "volume"}
    assert _format_result_display(bare) == "[1] 📚 X（卷）"


def test_format_result_display_other_sources():
    """bangumi/manhuagui 结果（无 resource_type）保持原格式不受影响"""
    from gui.gui_dialogs import _format_result_display
    bangumi = {"id": 123, "name": "One Punch Man", "name_cn": "一拳超人"}
    assert _format_result_display(bangumi) == "[123] 一拳超人  (One Punch Man)"
    same = {"id": 7, "name": "进击的巨人", "name_cn": "进击的巨人"}
    assert _format_result_display(same) == "[7] 进击的巨人"


def test_format_result_display_platform_series():
    """bangumi 结果带 platform：series=True 标注「（漫画系列）/（小说系列）」"""
    from gui.gui_dialogs import _format_result_display
    manga_series = {"id": 37953, "name": "CLAMP学园侦探团",
                    "name_cn": "CLAMP学园侦探团", "platform": "漫画", "series": True}
    assert _format_result_display(manga_series) == "[37953] CLAMP学园侦探团（漫画系列）"
    novel_series = {"id": 378339, "name": "CLAMP学园侦探团",
                    "name_cn": "CLAMP学园侦探团", "platform": "小说", "series": True}
    assert _format_result_display(novel_series) == "[378339] CLAMP学园侦探团（小说系列）"


def test_format_result_display_platform_volume():
    """bangumi 结果带 platform：series=False 只标注「（漫画）」不加「系列」二字"""
    from gui.gui_dialogs import _format_result_display
    manga_volume = {"id": 30883, "name": "CLAMP学園探偵団 (1)",
                    "name_cn": "CLAMP学園探偵団 (1)", "platform": "漫画", "series": False}
    assert _format_result_display(manga_volume) == "[30883] CLAMP学園探偵団 (1)（漫画）"


def test_format_result_display_platform_with_orig_name():
    """platform 标注与原名格式共存：中文名（原名）（漫画系列）"""
    from gui.gui_dialogs import _format_result_display
    result = {"id": 123, "name": "One Punch Man", "name_cn": "一拳超人",
              "platform": "漫画", "series": True}
    assert _format_result_display(result) == "[123] 一拳超人  (One Punch Man)（漫画系列）"


def test_format_result_display_no_platform():
    """platform 缺失 → 不加标注，保持原格式"""
    from gui.gui_dialogs import _format_result_display
    result = {"id": 456, "name": "CLAMP学园侦探团", "name_cn": "CLAMP学园侦探团",
              "series": True}
    assert _format_result_display(result) == "[456] CLAMP学园侦探团"


class FakeLog:
    """伪造日志控件：记录 append 的文本行"""

    def __init__(self):
        self.lines = []

    def append(self, text):
        self.lines.append(text)


class FakeTemplateHandler:
    """伪造 XML 模板处理器：create_base_template 返回空模板"""

    def create_base_template(self, folder_info):
        return {}

    def create_local_template(self, folder_info):
        return {"Status": "local"}


class FakeComicVineFetcher:
    """伪造 ComicVineFetcher：记录 series/volume 详情调用"""

    def __init__(self):
        self.series_calls = []
        self.volume_calls = []

    def get_series_detail(self, sid):
        self.series_calls.append(sid)
        return {"Title": "Batman Series", "Series": "Batman", "Year": "1966"}

    def get_volume_detail(self, vid):
        self.volume_calls.append(vid)
        return {"Title": "Batman Vol", "Series": "Batman", "Year": "2016", "Count": "12"}


def test_scan_detail_branch_by_resource_type(monkeypatch):
    """扫描详情抓取按 resource_type 分支：series→get_series_detail，volume→get_volume_detail"""
    from gui import comicvine_scan

    mw = type("FakeMW", (), {"log_text": FakeLog()})()
    folder_info = {"series": "Batman", "author": "Tom King"}
    fetcher = FakeComicVineFetcher()
    template_handler = FakeTemplateHandler()

    monkeypatch.setattr(
        "processors.search_handler.search_manga",
        lambda keyword, folder_info=None, source="bangumi": [{"id": 31, "name": "Batman"}],
    )

    # series 选中 → get_series_detail
    monkeypatch.setattr(
        "gui.comicvine_scan.show_result_selection_dialog",
        lambda *a, **k: {"id": 31, "name": "Batman", "resource_type": "series"},
    )
    comic_info_base, selected = comicvine_scan._search_and_select_comicvine(
        mw, "C:/fakepath/Batman", folder_info, fetcher, template_handler)
    assert fetcher.series_calls == [31]
    assert fetcher.volume_calls == []
    assert comic_info_base["Series"] == "Batman"
    assert "series" in mw.log_text.lines[-1]

    # volume 选中 → get_volume_detail
    monkeypatch.setattr(
        "gui.comicvine_scan.show_result_selection_dialog",
        lambda *a, **k: {"id": 29996, "name": "Batman", "resource_type": "volume"},
    )
    comic_info_base, selected = comicvine_scan._search_and_select_comicvine(
        mw, "C:/fakepath/Batman", folder_info, fetcher, template_handler)
    assert fetcher.volume_calls == [29996]
    assert fetcher.series_calls == [31]
    assert comic_info_base["Count"] == "12"
    assert "volume" in mw.log_text.lines[-1]


def test_scan_short_story_restores_suffix(monkeypatch):
    """短篇文件夹：Title 补回「.短篇完结」，Series 保持裸系列名（回归 2026-08-23 反转）"""
    from gui import comicvine_scan
    from parsers.folder_parser_lenient import parse_folder_name_lenient

    mw = type("FakeMW", (), {"log_text": FakeLog()})()
    folder_info = parse_folder_name_lenient("[北条司] Parrot (V01全 短篇)")
    assert folder_info is not None

    class FakeParrotFetcher:
        """详情返回裸 Series（模拟 ComicVine volume/series 详情映射，无后缀）"""

        def get_series_detail(self, sid):
            return {"Title": "Parrot", "Series": "Parrot", "Year": "1985"}

        def get_volume_detail(self, vid):
            return {"Title": "Parrot", "Series": "Parrot", "Count": "1"}

    fetcher = FakeParrotFetcher()
    template_handler = FakeTemplateHandler()

    monkeypatch.setattr(
        "processors.search_handler.search_manga",
        lambda keyword, folder_info=None, source="bangumi": [{"id": 31, "name": "Parrot"}],
    )
    monkeypatch.setattr(
        "gui.comicvine_scan.show_result_selection_dialog",
        lambda *a, **k: {"id": 31, "name": "Parrot", "resource_type": "series"},
    )
    comic_info_base, selected = comicvine_scan._search_and_select_comicvine(
        mw, "C:/fakepath/Parrot", folder_info, fetcher, template_handler)
    assert selected is not None
    assert comic_info_base["Series"] == "Parrot"  # Series 保持裸系列名
    assert comic_info_base["Title"] == "Parrot.短篇完结"


def test_create_result_dict_comicvine_web(tmp_path):
    """comicvine 结果的 web 字段直接取 site_detail_url（source_url 机制）"""
    from processors.result_builder import create_result_dict
    comic_file = tmp_path / "Batman Vol 01.cbz"
    comic_file.write_bytes(b"PK\x03\x04")
    folder_info = {"series": "Batman", "author": "Tom King", "complete": True,
                   "total_volumes": 12, "vol_info": "V12全"}
    comic_info_base = {"Series": "Batman", "Count": "12", "Publisher": "DC Comics",
                       "Web": "https://comicvine.gamespot.com/batman/4050-29996/"}
    selected_result = {"id": 29996, "name": "Batman", "name_cn": "Batman",
                       "url": "https://comicvine.gamespot.com/batman/4050-29996/"}
    result = create_result_dict(str(tmp_path), folder_info, comic_info_base,
                                selected_result, skipped=False, process_status="已修改",
                                source="comicvine")
    assert result["source"] == "comicvine"
    assert result["web"] == "https://comicvine.gamespot.com/batman/4050-29996/"
    assert result["source_id"] == "29996"
    assert result["bangumi_id"] == ""
    assert result["publisher"] == "DC Comics"
    assert result["count"] == "12"


def test_source_combo_has_comicvine(app):
    """扫描页数据源下拉框：官方 → 镜像 → ComicVine → manhuagui（默认官方）"""
    from config import (SOURCE_BANGUMI_MIRROR_TEXT, SOURCE_BANGUMI_TEXT,
                        SOURCE_COMICVINE_TEXT, SOURCE_MANHUAGUI_TEXT)

    items = [app.source_combo.itemText(i) for i in range(app.source_combo.count())]
    assert items == [SOURCE_BANGUMI_TEXT, SOURCE_BANGUMI_MIRROR_TEXT,
                     SOURCE_COMICVINE_TEXT, SOURCE_MANHUAGUI_TEXT]
    assert app.selected_source == SOURCE_BANGUMI_TEXT
