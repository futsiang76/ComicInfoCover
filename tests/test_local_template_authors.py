# -*- coding: utf-8 -*-
"""测试 create_local_template 的多作者拆分逻辑。

回归基线：多作者(×/&// 等)拆分后必须同时填充 Writer/Penciller，
单作者保持原 author 不变。复用 models.author_utils._split_authors。
"""
import pytest

from processors.xml_template_handler import XMLTemplateHandler


def _folder(**over):
    base = {
        "series": "测试系列",
        "author": "测试作者",
        "complete": True,
        "total_volumes": 3,
        "vol_type": "",
        "vol_info": "",
        "tags": [],
    }
    base.update(over)
    return base


@pytest.fixture
def handler():
    return XMLTemplateHandler()


def test_multi_author_with_x_split(handler):
    """含 × 的多作者拆分成多作者，Writer/Penciller 都用分隔后的全名列表"""
    folder = _folder(author="小明×小红")
    tpl = handler.create_local_template(folder)
    assert tpl["Writer"] == "小明, 小红"
    assert tpl["Penciller"] == "小明, 小红"


def test_multi_author_with_amp_split(handler):
    """含 & 的多作者拆分成多作者"""
    folder = _folder(author="Mark Gatiss & Steven Moffat")
    tpl = handler.create_local_template(folder)
    assert tpl["Writer"] == "Mark Gatiss, Steven Moffat"
    assert tpl["Penciller"] == "Mark Gatiss, Steven Moffat"


def test_multi_author_with_slash_split(handler):
    """含 / 的多作者拆分（覆盖 _split_authors 其它分隔符）"""
    folder = _folder(author="作者A/作者B")
    tpl = handler.create_local_template(folder)
    assert tpl["Writer"] == "作者A, 作者B"
    assert tpl["Penciller"] == "作者A, 作者B"


def test_single_author_unchanged(handler):
    """单作者保持不变，Writer/Penciller 等于原 author"""
    folder = _folder(author="测试作者")
    tpl = handler.create_local_template(folder)
    assert tpl["Writer"] == "测试作者"
    assert tpl["Penciller"] == "测试作者"
