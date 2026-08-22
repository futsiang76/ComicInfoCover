"""manhuagui 按漫画 ID 查找补充方式 + comic_info_base 崩溃修复 测试

覆盖：
- BaseScanThread.run(): search_and_select 返回 (None, None)（无结果用户跳过）时
  跳过不崩溃（回归：comic_info_base["Manga"] 的 TypeError）
- _build_from_manhuagui_id：ID 有效抓详情 / ID 无效 / 详情为空回退本地
- show_no_result_dialog：id_search_kind 决定 action（manhuagui → mhg_id_search）
- _search_and_select_manhuagui 无结果分支：allow_id_search=True + manhuagui ID 查找接线
"""
import pytest

from gui.base_scan_thread import BaseScanThread


class _FakeLog:
    def __init__(self):
        self.items = []

    def append(self, s):
        self.items.append(s)


class _FakeTemplate:
    """模板处理器桩：create_base_template / create_local_template"""

    def __init__(self, folder_info):
        self.folder_info = folder_info

    def create_base_template(self, folder_info):
        return {"Title": "", "Series": folder_info.get("series", ""), "Manga": "Yes"}

    def create_local_template(self, folder_info):
        return {"Title": folder_info["series"], "Series": folder_info["series"]}


class _SkipThread(BaseScanThread):
    """search_and_select 恒返回 (None, None) 的最小扫描线程（模拟无结果跳过）"""

    source_name = "test"

    def search_and_select(self, folder_path, folder_info):
        return None, None

    def build_result(self, folder_path, folder_info, comic_info_base, selected_result):
        raise AssertionError("build_result 不应被调用（跳过路径）")


class TestBaseScanThreadSkipOnNoneResult:
    """回归：search_and_select 返回 (None, None) 时 run() 不得崩溃"""

    def test_run_skips_none_result(self, qtbot):
        thread = _SkipThread("C:/fake", None,
                             folders=[("/fake/a", {"series": "A"})])
        emitted = []

        def on_error(message):
            emitted.append(("error", message))

        def on_finished(processed, skipped):
            emitted.append(("finished", processed, skipped))

        thread.error_occurred.connect(on_error)
        thread.series_finished.connect(on_finished)

        thread.run()  # 同步执行 run() 主体；不得抛异常/触发 error_occurred

        assert not any(e[0] == "error" for e in emitted), \
            f"不应报错：{emitted}"
        assert ("finished", 0, 1) in emitted  # processed=0, skipped=1


class TestBuildFromManhuaguiId:
    def test_success(self):
        from gui import manhuagui_scan

        mw = type("MW", (), {"log_text": _FakeLog()})()
        folder_info = {"series": "原子小金刚"}

        class FakeFetcher:
            def get_manga_detail(self, url):
                assert url == "https://www.manhuagui.com/comic/20635/"
                return {"Title": "原子小金剛 地上最大機器人篇",
                        "Writer": "手塚治虫"}

        base, selected = manhuagui_scan._build_from_manhuagui_id(
            mw, "20635", folder_info, FakeFetcher(), _FakeTemplate(folder_info))

        assert base["Title"] == "原子小金剛 地上最大機器人篇"
        assert base["Writer"] == "手塚治虫"
        assert selected["url"] == "https://www.manhuagui.com/comic/20635/"
        assert selected["title"] == "原子小金剛 地上最大機器人篇"
        assert any("🎯 获取到: 原子小金剛 地上最大機器人篇" in item
                   for item in mw.log_text.items)

    def test_invalid_id_falls_back_to_local(self):
        from gui import manhuagui_scan

        mw = type("MW", (), {"log_text": _FakeLog()})()
        folder_info = {"series": "原子小金刚"}

        class FakeFetcher:
            def get_manga_detail(self, url):  # pragma: no cover - 不应被调用
                raise AssertionError("无效 ID 不应抓详情")

        base, selected = manhuagui_scan._build_from_manhuagui_id(
            mw, "abc", folder_info, FakeFetcher(), _FakeTemplate(folder_info))

        assert base["Title"] == "原子小金刚"  # 回退本地模板
        assert selected is None
        assert any("❌ 无效的 manhuagui ID" in item for item in mw.log_text.items)

    def test_detail_empty_falls_back_to_local(self):
        from gui import manhuagui_scan

        mw = type("MW", (), {"log_text": _FakeLog()})()
        folder_info = {"series": "原子小金刚"}

        class FakeFetcher:
            def get_manga_detail(self, url):
                return {}  # 详情为空

        base, selected = manhuagui_scan._build_from_manhuagui_id(
            mw, "99999", folder_info, FakeFetcher(), _FakeTemplate(folder_info))

        assert base["Title"] == "原子小金刚"
        assert selected is None
        assert any("❌ 未找到该 manhuagui ID 的作品" in item
                   for item in mw.log_text.items)


class TestNoResultDialogActionKind:
    """show_no_result_dialog 按 id_search_kind 转换 dict 结果 action"""

    @pytest.fixture
    def patch_dialog(self, monkeypatch):
        from gui import gui_dialogs

        calls = {}

        def fake_dialog(parent, results, folder_info, alt_keywords=None,
                        allow_id_search=True, id_search_kind="bangumi"):
            calls["allow_id_search"] = allow_id_search
            calls["id_search_kind"] = id_search_kind
            return {"id": "20635", "name": "原子小金剛"}

        monkeypatch.setattr(gui_dialogs, "show_result_selection_dialog", fake_dialog)
        return calls

    def test_manhuagui_returns_mhg_id_search(self, monkeypatch, patch_dialog):
        from gui import gui_dialogs

        got = gui_dialogs.show_no_result_dialog(
            None, {"series": "原子小金刚"}, id_search_kind="manhuagui")
        assert got == {"action": "mhg_id_search", "value": "20635"}
        assert patch_dialog["allow_id_search"] is True
        assert patch_dialog["id_search_kind"] == "manhuagui"

    def test_bangumi_default_returns_id_search(self, monkeypatch, patch_dialog):
        from gui import gui_dialogs

        got = gui_dialogs.show_no_result_dialog(
            None, {"series": "原子小金刚"})
        assert got == {"action": "id_search", "value": "20635"}
        assert patch_dialog["id_search_kind"] == "bangumi"


class TestSearchAndSelectMhgIdSearch:
    """无结果分支接线：no_result_dialog 返回 mhg_id_search → 按 ID 抓详情"""

    def test_no_result_wires_manhuagui_id_search(self, monkeypatch):
        from gui import manhuagui_scan
        from processors import search_handler

        monkeypatch.setattr(
            search_handler, "search_manga",
            lambda keyword, folder_info, source="manhuagui": [])
        captured = {}

        def fake_no_result(mw, folder_info, alt_keywords=None,
                           allow_id_search=True, id_search_kind="bangumi"):
            captured["allow_id_search"] = allow_id_search
            captured["id_search_kind"] = id_search_kind
            return {"action": "mhg_id_search", "value": "20635"}

        monkeypatch.setattr(manhuagui_scan, "show_no_result_dialog", fake_no_result)

        class FakeFetcher:
            def get_manga_detail(self, url):
                assert url == "https://www.manhuagui.com/comic/20635/"
                return {"Title": "原子小金剛 地上最大機器人篇"}

        mw = type("MW", (), {"log_text": _FakeLog()})()
        folder_info = {"series": "原子小金刚", "aliases": [], "author": ""}

        base, selected = manhuagui_scan._search_and_select_manhuagui(
            mw, "/fake/path", folder_info, FakeFetcher(),
            _FakeTemplate(folder_info))

        assert captured["allow_id_search"] is True
        assert captured["id_search_kind"] == "manhuagui"
        assert base["Title"] == "原子小金剛 地上最大機器人篇"
        assert selected["url"] == "https://www.manhuagui.com/comic/20635/"


class TestManhuaguiShortStorySuffix:
    """短篇文件夹：update(detail) 裸 Series/Title 覆盖后缀后统一补回（回归 2026-08-23）

    场景：[北条司] Parrot (V01全 短篇) → create_base_template 产出
    「Parrot.短篇完结」，但 manhuagui detail 的裸 Series/Title 覆盖了它。
    修复后 ensure_short_story_suffix 在 update(detail) 之后补回（幂等）。
    """

    @staticmethod
    def _folder_info(name):
        from parsers.folder_parser_lenient import parse_folder_name_lenient
        return parse_folder_name_lenient(name)

    @staticmethod
    def _real_template():
        from processors.xml_template_handler import create_xml_template_handler
        return create_xml_template_handler()

    def test_build_from_id_short_story_restores_suffix(self):
        from gui import manhuagui_scan

        mw = type("MW", (), {"log_text": _FakeLog()})()
        folder_info = self._folder_info("[北条司] Parrot (V01全 短篇)")
        assert folder_info is not None

        class FakeFetcher:
            def get_manga_detail(self, url):  # manhuagui 详情：裸标题无后缀
                return {"Title": "Parrot", "Series": "Parrot", "Writer": "北条司"}

        base, selected = manhuagui_scan._build_from_manhuagui_id(
            mw, "12345", folder_info, FakeFetcher(), self._real_template())

        assert base["Series"] == "Parrot.短篇完结"
        assert base["Title"] == "Parrot.短篇完结"
        # result 信号与 series 字段正确（保存链路 _apply_result_fields 兜底同步生效）
        from processors.result_builder import create_result_dict
        result = create_result_dict("/fake/Parrot", folder_info, base, selected,
                                    False, "已修改", source="manhuagui")
        assert result["short_story"] is True
        assert result["series"] == "Parrot.短篇完结"

    def test_build_from_id_short_story_idempotent(self):
        """detail 已带后缀 → 不重复追加"""
        from gui import manhuagui_scan

        mw = type("MW", (), {"log_text": _FakeLog()})()
        folder_info = self._folder_info("[北条司] Parrot (V01全 短篇)")

        class FakeFetcher:
            def get_manga_detail(self, url):
                return {"Title": "Parrot.短篇完结", "Series": "Parrot.短篇完结"}

        base, _ = manhuagui_scan._build_from_manhuagui_id(
            mw, "12345", folder_info, FakeFetcher(), self._real_template())
        assert base["Series"] == "Parrot.短篇完结"
        assert base["Title"] == "Parrot.短篇完结"

    def test_build_from_id_non_short_story_unchanged(self):
        """普通已完结卷 [北条司] 城市猎人 (V35全) → Series 不带后缀（回归）"""
        from gui import manhuagui_scan

        mw = type("MW", (), {"log_text": _FakeLog()})()
        folder_info = self._folder_info("[北条司] 城市猎人 (V35全)")
        assert folder_info is not None

        class FakeFetcher:
            def get_manga_detail(self, url):
                return {"Title": "城市猎人", "Series": "城市猎人"}

        base, _ = manhuagui_scan._build_from_manhuagui_id(
            mw, "99999", folder_info, FakeFetcher(), self._real_template())
        assert base["Series"] == "城市猎人"
        assert base["Title"] == "城市猎人"

    def test_search_and_select_short_story_restores_suffix(self, monkeypatch):
        """搜索 → 选择 → 详情路径同样补回后缀"""
        from gui import manhuagui_scan
        from processors import search_handler

        monkeypatch.setattr(
            search_handler, "search_manga",
            lambda keyword, folder_info=None, source="manhuagui": [{
                "id": 12345, "url": "https://www.manhuagui.com/comic/12345/",
                "title": "Parrot", "author": "北条司"}])
        captured = {}

        def fake_select(parent, results, folder_info, allow_id_search=False):
            captured["results"] = results
            return {"id": 12345, "url": "https://www.manhuagui.com/comic/12345/"}

        monkeypatch.setattr(manhuagui_scan, "show_result_selection_dialog", fake_select)

        class FakeFetcher:
            def get_manga_detail(self, url):
                return {"Title": "Parrot", "Series": "Parrot", "Writer": "北条司"}

        mw = type("MW", (), {"log_text": _FakeLog()})()
        folder_info = self._folder_info("[北条司] Parrot (V01全 短篇)")
        base, selected = manhuagui_scan._search_and_select_manhuagui(
            mw, "/fake/Parrot", folder_info, FakeFetcher(), self._real_template())

        assert captured["results"], "应走搜索结果选择分支而非无结果分支"
        assert selected is not None
        assert base["Series"] == "Parrot.短篇完结"
        assert base["Title"] == "Parrot.短篇完结"

    def test_ensure_short_story_suffix_helper(self):
        """公共 helper 单测：补后缀 / 幂等 / 非短篇不动 / 无键不动"""
        from processors.xml_template_handler import ensure_short_story_suffix

        folder_info = self._folder_info("[北条司] Parrot (V01全 短篇)")
        # 裸 Series/Title → 补后缀
        base = ensure_short_story_suffix({"Title": "Parrot", "Series": "Parrot"}, folder_info)
        assert base == {"Title": "Parrot.短篇完结", "Series": "Parrot.短篇完结"}
        # 幂等：已带后缀不重复追加
        base = ensure_short_story_suffix(
            {"Title": "Parrot.短篇完结", "Series": "Parrot.短篇完结"}, folder_info)
        assert base["Series"] == "Parrot.短篇完结"
        assert base["Title"] == "Parrot.短篇完结"
        # 非短篇文件夹 → 原样
        normal = self._folder_info("[北条司] 城市猎人 (V35全)")
        base = ensure_short_story_suffix({"Title": "城市猎人", "Series": "城市猎人"}, normal)
        assert base == {"Title": "城市猎人", "Series": "城市猎人"}
        # 空字典 / 无 Series/Title 键 → 原样返回
        assert ensure_short_story_suffix({}, folder_info) == {}
        assert ensure_short_story_suffix({"Summary": "x"}, folder_info) == {"Summary": "x"}