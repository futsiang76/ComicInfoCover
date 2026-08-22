"""clean_year / clean_month 公共清洗函数测试 — Year/Month 字段只保留纯数字

背景：Komga 读取 ComicInfo.xml 时 Year 是数字类型，「1999年」等带非数字字符的
值会导致整份 XML 反序列化失败（Jackson 报 ComicInfo["Year"]）、元数据全部丢弃。
manhuagui 源抓到的年代正是「1999年」，必须清成纯数字再写入 XML。
"""
import pytest

from processors.xml_generator import clean_month, clean_year


class TestCleanYear:
    @pytest.mark.parametrize("raw,expected", [
        ("1999年", "1999"),        # manhuagui 源：带「年」字
        ("1999年1月", "1999"),     # 带年月
        ("2024-07-15", "2024"),   # 完整日期
        ("2024", "2024"),         # 已是纯数字
        (2016, "2016"),           # 数字类型（ComicVine start_year 为 int）
        (1966, "1966"),
        ("19世纪末", "19"),       # 无 4 位年份时退而取连续数字段
    ])
    def test_extracts_digits(self, raw, expected):
        assert clean_year(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "未知", "   "])
    def test_empty_when_no_digits(self, raw):
        assert clean_year(raw) == ""


class TestCleanMonth:
    @pytest.mark.parametrize("raw,expected", [
        ("7", "7"),
        ("07", "07"),
        ("12", "12"),
        ("7月", "7"),
    ])
    def test_extracts_digits(self, raw, expected):
        assert clean_month(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "未知"])
    def test_empty_when_no_digits(self, raw):
        assert clean_month(raw) == ""


class TestWritePathsCleanYearMonth:
    """三条 Year/Month 写入路径都经过清洗"""

    def test_apply_result_fields_cleans_manhuagui_year(self):
        """_apply_result_fields（统一入口）：1999年 → 1999，1月 → 1"""
        from processors.xml_generator import _apply_result_fields

        info = {"Year": "x", "Month": "x"}
        _apply_result_fields(info, {"year": "1999年", "month": "1月", "series": "某系列"})
        assert info["Year"] == "1999"
        assert info["Month"] == "1"

    def test_locked_detail_year_cleaned(self):
        """build_file_comicinfo 锁住文件路径：detail 的 year 带「年」也被清成纯数字"""
        from processors.xml_generator import build_file_comicinfo

        info = build_file_comicinfo(
            {"series": "x", "year": "2020"},
            "Vol 01.zip",
            detail={"year": "1999年", "month": "7月", "summary": "单卷独立摘要"},
            is_locked=True,
        )
        assert info["Year"] == "1999"
        assert info["Month"] == "7"
        assert info["Summary"] == "单卷独立摘要"

    def test_extract_year_month_cleaned(self):
        """xml_template_handler._extract_year_month：日期串带「年」时 Year 只留数字"""
        from processors.xml_template_handler import XMLTemplateHandler

        ym = XMLTemplateHandler()._extract_year_month("1999年1月")
        assert ym == {"Year": "1999", "Month": ""}
        ym2 = XMLTemplateHandler()._extract_year_month("2024-07-15")
        assert ym2 == {"Year": "2024", "Month": "07"}

    def test_pure_digits_unchanged(self):
        """纯数字 Year/Month 输出不受影响（Bangumi/ComicVine 正常路径）"""
        from processors.xml_generator import build_file_comicinfo

        info = build_file_comicinfo(
            {"series": "x", "year": "2016", "month": "5"},
            "Vol 01.zip",
            detail={"year": "1966", "month": "12"},
            is_locked=True,
        )
        assert info["Year"] == "1966"
        assert info["Month"] == "12"
