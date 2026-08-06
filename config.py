#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件 - 所有常量、配置和正则表达式模式
"""

# ===================== 核心配置 =====================
try:
    from secrets import BANGUMI_ACCESS_TOKEN
except ImportError:
    BANGUMI_ACCESS_TOKEN = ""      # secrets.py 不存在时降级为空字符串
FUZZ_THRESHOLD = 85           # 作品名模糊匹配阈值
AUTHOR_MATCH_THRESHOLD = 70   # 作者名匹配阈值（任一作者≥70即匹配）
TIMEOUT = 15                  # 请求超时时间
MAX_RETRIES = 3               # 请求重试次数
CROP_MEMORY_ENABLED = True    # 封面裁剪定位记忆开关（默认开启）
SHOW_TOP_N = 10               # 手动选择时显示前N个结果
WAITING_TIME = 0             # 等待用户输入的时间（秒），0表示无限等待
MODE_SKIP_XMLEXIST = 0        # 跳过已有XML文件的模式：0=按现有全匹配策略修改，1=有XML就跳过，2=只处理已有XML的文件（修正模式）
AUTO_TURBO_MATCH = 0          # 无人值守快速模式：0=关闭，1=开启（仅当唯一匹配结果时自动处理）

# ===================== XML模板配置 =====================
COMICINFO_TEMPLATE = {
    "Title": "",           # 标题
    "Series": "",          # 系列名
    "Volume": "",          # 单本书卷数
    "Number": "",          # 单话编号（用于单话文件）
    "Count": "",           # 系列总卷数（已完结填写，连载中留空）
    "Summary": "",         # 简介
    "Notes": "",           # 备注
    "Year": "",            # 年份
    "Month": "",           # 月份
    "Writer": "",          # 编剧
    "Penciller": "",       # 画师
    "Inker": "",           # 墨线师
    "Colorist": "",        # 上色师
    "Letterer": "",        # 字母师
    "CoverArtist": "",     # 封面画师
    "Editor": "",          # 编辑
    "Publisher": "",       # 出版社
    "Genre": "",            # 类型
    "Web": "",             # 网址
    "PageCount": "",       # 页数
    "LanguageISO": "zh-CN", # 语言代码
    "Format": "Zip",       # 格式
    "BlackAndWhite": "",   # 是否黑白
    "Manga": "Yes",        # 是否漫画
    "AgeRating": "",       # 年龄分级
    "Tags": "",            # 标签
    "Status": "",          # 状态（Completed/Ongoing）
    "Rating": ""           # 评分
}

# 短篇特殊模板
SHORT_STORY_TEMPLATE = {
    **COMICINFO_TEMPLATE,
    "Count": "1",            # 短篇 = 一卷全
    "Volume": "",           # 短篇不显示单本书卷数
    "Summary": "短篇漫画",    # 短篇简介
    "Tags": "短篇",         # 短篇标签
    "Status": "Completed"    # 短篇默认已完成
}

# ===================== 正则表达式模式 =====================
# 匹配格式：[作者] 漫画名 (V05全) 或 [作者] 漫画名 (短篇全) 或 [作者] 漫画名 (V03全+设定集+番外) 或 [作者] 漫画名 第1部 (V03 C13)
# 兼容作者[]后没有空格的情况
FOLDER_PATTERN = r'^\[(?P<author>.+?)\]\s*(?P<series>.+?)(?:\s+第.+?)?\s*\((?P<vol_info>V\d+(?:\s+\w+)?|短篇)(?P<complete>全)?(?:[\s\+](?P<extras>.+?))?\)$'


# 文件名解析模式
VOL_PATTERN = r'(?:Vol\.?\s*(\d+)|V(\d+)|第\s*(\d+)\s*卷)'
CHAPTER_PATTERN = r'^(C(\d+)|第(\d+)话)'

# ===================== 额外内容关键词 =====================
EXTRA_KEYWORDS = ['设定集', '番外', '外传', '特典', '附录', '画集', '原画集']