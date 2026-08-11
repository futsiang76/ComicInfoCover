#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理器模块 - 兼容 re-export 中转站

CLI 已移除（2026-08-11），batch_process 已删除。
保留 process_normal_folder / process_short_story_folder 的 re-export，
供历史 import 路径兼容（真身在 scan_processors / utils）。
"""

from .utils import process_short_story_folder
from .scan_processors import process_normal_folder
