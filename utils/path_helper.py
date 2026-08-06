#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径助手模块 - 获取用户输入的漫画根目录路径
"""

import os

def get_manga_root_path():
    """获取用户输入的漫画根目录路径"""
    while True:
        print("\n" + "="*60)
        print("📁 请输入漫画根目录路径 (例如: F:\\Comics 或 /home/user/comics)")
        print("💡 提示：路径中可以使用正斜杠(/)或反斜杠(\\)")
        print("="*60)
        
        path = input("漫画根目录路径: ").strip()
        
        if not path:
            print("❌ 路径不能为空，请重新输入")
            continue
            
        # 统一路径分隔符
        path = os.path.normpath(path)
        
        # 检查路径是否存在
        if not os.path.exists(path):
            print(f"❌ 路径不存在: {path}")
            print("💡 请检查路径是否正确，或先创建该目录")
            continue
            
        # 检查是否为目录
        if not os.path.isdir(path):
            print(f"❌ 路径不是目录: {path}")
            continue
            
        # 检查是否有读取权限
        try:
            os.listdir(path)
        except PermissionError:
            print(f"❌ 没有读取权限: {path}")
            continue
        except Exception as e:
            print(f"❌ 无法访问路径: {str(e)}")
            continue
            
        print(f"✅ 已设置漫画根目录: {path}")
        return path