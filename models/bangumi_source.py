#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bangumi 数据源直连模块 - 数据源标识与 API/网页域名映射（不做自动 failover）
"""

import requests

import config

# 网页请求浏览器 UA：Cloudflare 挡爬虫 UA（curl/默认 UA 403），必须用完整浏览器 UA
_WEB_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _web_mirror_from_api(api_base: str) -> str:
    """API 镜像域名 → 网页镜像域名

    映射规则：去 api 前缀（api.bangumi.lol → bangumi.lol）；anibt 特殊
    （bgmapi.anibt.net → bgmmi.anibt.net）。官方 api.bgm.tv → bgm.tv。
    """
    host = api_base.split("://", 1)[-1].rstrip("/")
    if host.startswith("bgmapi."):
        host = "bgmmi." + host[len("bgmapi."):]
    elif host.startswith("api."):
        host = host[len("api."):]
    return f"https://{host}"


# ---- 数据源直连：按当前源选域名，不做自动 failover ----
_ACTIVE_SOURCE = config.BANGUMI_SOURCE_OFFICIAL


def set_active_bangumi_source(source: str) -> None:
    """设置模块级当前 Bangumi 数据源（后续新建 fetcher 的默认直连目标）

    由 gui 在数据源切换/扫描启动时调用；非 Bangumi 源标识按官方处理。

    Args:
        source: 数据源标识（config.BANGUMI_SOURCE_OFFICIAL / _MIRROR）
    """
    global _ACTIVE_SOURCE
    if source not in (config.BANGUMI_SOURCE_OFFICIAL, config.BANGUMI_SOURCE_MIRROR):
        source = config.BANGUMI_SOURCE_OFFICIAL
    _ACTIVE_SOURCE = source


def get_active_bangumi_source() -> str:
    """返回模块级当前 Bangumi 数据源标识

    fetcher 需动态读取（from import 会绑定旧值，见 set_active_bangumi_source）。
    """
    return _ACTIVE_SOURCE


def _api_base_for_source(source: str) -> str:
    """数据源标识 → API 基础域名（从 config.BANGUMI_MIRRORS 可用域名表选取）

    官方源优先 api.bgm.tv，镜像源优先 api.bangumi.lol；用户配置里缺对应
    域名时回退：镜像取列表次项，官方取首项。不自动切换、不做 failover。

    Args:
        source: 数据源标识

    Returns:
        str: 该数据源对应的 API 基础域名

    Raises:
        requests.exceptions.RequestException: BANGUMI_MIRRORS 为空
    """
    mirrors = list(config.BANGUMI_MIRRORS or [])
    if not mirrors:
        raise requests.exceptions.RequestException("BANGUMI_MIRRORS 为空")
    marker = "api.bangumi.lol" if source == config.BANGUMI_SOURCE_MIRROR else "api.bgm.tv"
    for base in mirrors:
        if marker in base:
            return base
    if source == config.BANGUMI_SOURCE_MIRROR and len(mirrors) > 1:
        return mirrors[1]
    return mirrors[0]
