#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描模式与数据源联动逻辑 - 数据源切换时的模式约束与 Bangumi 源同步

受限源（manhuagui/ComicVine）固定全匹配模式并隐藏受限控件；Bangumi 官方
与大陆镜像为非受限源。数据源切换同时同步 BangumiFetcher 的直连域名。
"""

from config import (BANGUMI_SOURCE_MIRROR, BANGUMI_SOURCE_OFFICIAL,
                    SOURCE_BANGUMI_MIRROR_TEXT, SOURCE_BANGUMI_TEXT,
                    SOURCE_COMICVINE_TEXT, SOURCE_MANHUAGUI_TEXT)
from models.bangumi_fetcher import set_active_bangumi_source


# 受限源（固定全匹配 + 隐藏补漏/修正/无人值守）：manhuagui 排最后
MODE_CONSTRAINED_SOURCES = (SOURCE_MANHUAGUI_TEXT, SOURCE_COMICVINE_TEXT)

MODE_DESCRIPTIONS = {
    0: "逐文件夹匹配 Bangumi，匹配失败时弹出选择窗口。速度最慢但结果最准确。",
    1: "跳过已有 XML 的文件夹，只处理没有 XML 的新文件夹，补齐缺失的 XML 信息。",
    2: "只处理已有 XML 的文件夹，修正错误数据。不处理没有 XML 的新文件夹。",
    3: "人工到 Bangumi 查询编号，输入 Bangumi ID 后扫描。适合需要人工确认匹配的系列，可处理多个系列。",
}

# 数据源下拉显示名 → Bangumi fetcher 源标识（官方/镜像；其他源不影响 fetcher）
BANGUMI_SOURCE_TEXT_TO_ID = {
    SOURCE_BANGUMI_TEXT: BANGUMI_SOURCE_OFFICIAL,
    SOURCE_BANGUMI_MIRROR_TEXT: BANGUMI_SOURCE_MIRROR,
}


def bangumi_source_id(text: str) -> str:
    """数据源下拉显示名 → Bangumi fetcher 源标识（非 Bangumi 源按官方处理）

    Args:
        text: 数据源下拉显示名

    Returns:
        str: config.BANGUMI_SOURCE_OFFICIAL / BANGUMI_SOURCE_MIRROR
    """
    return BANGUMI_SOURCE_TEXT_TO_ID.get(text, BANGUMI_SOURCE_OFFICIAL)


def _on_source_changed(mw, text: str) -> None:
    """数据源下拉框变化：记录选中源、同步 fetcher 直连源并联动模式控件显隐"""
    mw.selected_source = text
    set_active_bangumi_source(bangumi_source_id(text))
    apply_source_mode_constraint(mw, text)


def apply_source_mode_constraint(mw, source: str) -> None:
    """数据源联动：受限源固定全匹配模式并隐藏受限控件；Bangumi 恢复

    作为数据源切换与扫描结束解锁的共用入口（scan_controller 恢复时也调用），
    保证受限源下非全匹配模式控件始终不可见/不可用。
    """
    constrained = source in MODE_CONSTRAINED_SOURCES
    if constrained:
        mw._mode_radios[0].setChecked(True)  # 固定全匹配模式
        mw.mode_description_label.setText(MODE_DESCRIPTIONS[0])
    for val, radio in mw._mode_radios.items():
        hidden = constrained and val != 0
        radio.setVisible(not hidden)
        radio.setEnabled(not hidden)
    if constrained:
        # 无人值守与受限模式互斥，切源时强制复位
        mw.auto_turbo_check.setChecked(False)
        mw.auto_turbo_check.hide()
        mw.auto_turbo_desc.hide()
    else:
        # 非受限：无人值守显隐跟随当前模式（对齐 _on_mode_changed）
        show_auto_turbo = mw.mode_group.checkedId() == 0
        mw.auto_turbo_check.setVisible(show_auto_turbo)
        mw.auto_turbo_desc.setVisible(show_auto_turbo)
