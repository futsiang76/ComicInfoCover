# -*- coding: utf-8 -*-
"""路径写法兼容性测试"""
import os

# 用不同写法构造同一路径
base = "H:/Comics/日漫/未完结/A-C/[坂月さかな] 星旅少年"

paths = {
    "正斜杠": base,
    "反斜杠": base.replace("/", "\\"),
    "双反斜杠": base.replace("/", "\\\\"),
    "正斜杠+尾斜杠": base + "/",
    "反斜杠+尾斜杠": base.replace("/", "\\") + "\\",
    "双反斜杠+尾斜杠": base.replace("/", "\\\\") + "\\\\",
}

for name, p in paths.items():
    print(f"{name}: {p!r}")
    print(f"  exists={os.path.exists(p)}  isdir={os.path.isdir(p)}")
