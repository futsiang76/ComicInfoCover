#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享工具函数
"""


def _trim_compare_dicts(old_dict: dict, new_dict: dict) -> bool:
    """递归比较两个字典，对所有字符串值做strip后比较，返回True表示有差异"""
    all_keys = set(old_dict.keys()) | set(new_dict.keys())
    for k in all_keys:
        old_v = old_dict.get(k)
        new_v = new_dict.get(k)
        if isinstance(old_v, dict) and isinstance(new_v, dict):
            if _trim_compare_dicts(old_v, new_v):
                return True
        elif isinstance(old_v, dict) or isinstance(new_v, dict):
            return True
        else:
            if str(old_v).strip() != str(new_v).strip():
                return True
    return False
