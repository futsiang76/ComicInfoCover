"""结果页测试"""
from PySide6.QtWidgets import QPushButton, QWidget


def test_results_tab_exists(app):
    """结果标签页存在"""
    app.tab_widget.setCurrentIndex(1)
    assert app.tab_widget.currentIndex() == 1
    assert app.tab_widget.tabText(1) == "📊 结果"


def test_results_buttons_removed(app):
    """底部操作按钮已移除（编辑/保存/返回扫描由编辑弹窗+表头切换取代）"""
    assert not hasattr(app, 'save_btn')
    assert not hasattr(app, 'edit_btn')
    assert not hasattr(app, 'cancel_btn')


def _result_dict(series: str) -> dict:
    """构造最小可渲染的结果字典"""
    return {
        "folder_path": "/tmp/dummy",
        "folder_name": f"{series} Folder",
        "series": series,
        "file_titles": {},
        "file_details": {},
        "covers": {},
        "locked_files": set(),
        "count": "1",
        "writer": "", "penciller": "", "colorist": "", "web": "",
        "year": "", "month": "", "status": "Completed", "summary": "",
        "genre": "", "tags": "", "manga": "Yes", "process_status": "已修改",
    }


def _find_layout_containing(widget, layout):
    """递归查找包含 widget 的布局"""
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            return layout
        if item.layout():
            found = _find_layout_containing(widget, item.layout())
            if found:
                return found
    return None


def test_results_card_crop_label_and_centered_edit(app):
    """结果卡片：展开按钮上方有「裁剪封面」标签；编辑按钮被两侧 addStretch 水平居中"""
    from PySide6.QtWidgets import QLabel

    app.scan_results = [_result_dict("Series")]
    app.update_results_table()

    box = app.results_layout.itemAt(0).widget()
    labels = box.findChildren(QLabel)
    assert any(l.text() == "裁剪封面" for l in labels)

    edit_btns = [b for b in box.findChildren(QPushButton) if "编辑" in b.text()]
    assert len(edit_btns) == 1
    lay = _find_layout_containing(edit_btns[0], box.layout())
    assert lay is not None and lay.count() == 3
    assert lay.itemAt(1).widget() is edit_btns[0]
    assert lay.itemAt(0).spacerItem() is not None   # 左侧 addStretch
    assert lay.itemAt(2).spacerItem() is not None   # 右侧 addStretch


def test_volume_grid_no_center_alignment(app):
    """展开的卷封面网格不整体居中，保持默认对齐弹性铺满"""
    from PySide6.QtCore import Qt

    from gui.results_table import _VolumeGrid

    grid = _VolumeGrid([QWidget()])
    app_grid = grid._grid_layout
    assert not app_grid.alignment() & Qt.AlignmentFlag.AlignHCenter


def test_crop_label_tight_above_expand_btn(app):
    """「裁剪封面」与展开按钮同布局且间距 0，紧贴按钮上方"""
    from PySide6.QtWidgets import QLabel

    app.scan_results = [_result_dict("Series")]
    app.update_results_table()
    box = app.results_layout.itemAt(0).widget()

    expand_btn = next(b for b in box.findChildren(QPushButton) if "展开" in b.text())
    lay = _find_layout_containing(expand_btn, box.layout())
    assert lay is not None and lay.spacing() == 0  # cover_block 间距 0

    widgets = [lay.itemAt(i).widget() for i in range(lay.count())]
    crop_idx = next(i for i, w in enumerate(widgets)
                    if isinstance(w, QLabel) and w.text() == "裁剪封面")
    assert widgets[crop_idx + 1] is expand_btn  # 紧贴展开/收起按钮上方


def test_results_container_exists(app):
    assert isinstance(app.results_container, QWidget)
    assert app.results_layout is not None


def test_cancel_returns_to_scan(app):
    """cancel_to_scan 方法仍可用于表头切换"""
    app.tab_widget.setCurrentIndex(1)
    app.cancel_to_scan()
    assert app.tab_widget.currentIndex() == 0
