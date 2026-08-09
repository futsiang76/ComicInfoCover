#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户设置持久化测试 — user_config.json 读写

conftest._isolate_user_config 已把 USER_CONFIG_PATH 指向临时文件并重置
config 模块属性为默认值，故本文件不会污染项目根的真实 user_config.json。
"""
import json

import config


def test_load_settings_defaults_when_missing():
    """user_config.json 不存在时，缺失字段返回默认值"""
    settings = config.load_settings()
    assert settings["fuzz_threshold"] == config.DEFAULT_SETTINGS["fuzz_threshold"]
    assert settings["save_format"] == "keep"
    assert settings["delete_after_convert"] is True
    assert settings["crop_memory_enabled"] is True


def test_save_settings_writes_file_and_applies():
    """save_settings 写入 user_config.json 并同步到 config 模块属性"""
    config.save_settings({
        "bangumi_access_token": "tok_123",
        "comicvine_api_key": "ckey_456",
        "fuzz_threshold": 77,
        "save_format": "cbz",
        "delete_after_convert": False,
    })

    with open(config.USER_CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert data["bangumi_access_token"] == "tok_123"
    assert data["comicvine_api_key"] == "ckey_456"
    assert data["fuzz_threshold"] == 77
    assert data["save_format"] == "cbz"
    assert data["delete_after_convert"] is False

    # config 模块属性立即生效（保存后无需重启）
    assert config.BANGUMI_ACCESS_TOKEN == "tok_123"
    assert config.COMICVINE_API_KEY == "ckey_456"
    assert config.FUZZ_THRESHOLD == 77
    assert config.SAVE_FORMAT == "cbz"
    assert config.DELETE_AFTER_CONVERT is False


def test_load_settings_reads_written_values():
    """写入后再 load_settings 能读回；未写字段补默认值"""
    config.save_settings({"timeout": 25, "max_retries": 5})

    settings = config.load_settings()
    assert settings["timeout"] == 25
    assert settings["max_retries"] == 5
    # 未写入的字段保持默认
    assert settings["save_format"] == "keep"
    assert settings["crop_memory_enabled"] is True


def test_save_settings_ignores_unknown_keys():
    """未知键被忽略，不写入文件"""
    config.save_settings({"bogus": 1, "fuzz_threshold": 55})

    settings = config.load_settings()
    assert "bogus" not in settings
    assert settings["fuzz_threshold"] == 55


def test_save_settings_merges_existing_fields():
    """部分保存会保留文件里已有的其它字段"""
    config.save_settings({"fuzz_threshold": 60})
    config.save_settings({"author_match_threshold": 66})

    settings = config.load_settings()
    assert settings["fuzz_threshold"] == 60
    assert settings["author_match_threshold"] == 66


def test_corrupt_config_returns_defaults(tmp_path):
    """user_config.json 内容损坏时 load_settings 回退默认值"""
    from pathlib import Path
    config.USER_CONFIG_PATH = str(tmp_path / "user_config.json")
    Path(config.USER_CONFIG_PATH).write_text("{ not valid json", encoding="utf-8")

    settings = config.load_settings()
    assert settings["fuzz_threshold"] == config.DEFAULT_SETTINGS["fuzz_threshold"]
