#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZIP 流式重写更新 XML 行为测试

覆盖范围：
- zip/cbz 原地写改走 zipfile 流式重写（不再 7z a -si）：不调用 7z/subprocess
- .cb7 等非 zip 容器原地写仍走 7z 更新失败重试 → 回退（语义不变）
- _add_with_zipfile 原子替换失败（os.replace 抛错）时返回 False 并清理临时文件
"""
import os
import shutil
import subprocess
import zipfile

import config
from processors import zip_operations


def _make_zip(path, xml: str = None) -> str:
    """生成含一张图片（可选含 ComicInfo.xml）的 zip 文件"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("000.png", b"fake-image-bytes")
        if xml is not None:
            zf.writestr("ComicInfo.xml", xml)
    return str(path)


def _patch_sleep(monkeypatch):
    """把 time.sleep 替换为不真等的记录器，避免拖慢测试"""
    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))
    return sleep_calls


def test_zip_inplace_uses_zipfile_stream(monkeypatch, tmp_path, capsys):
    """.zip 原地写改走 zipfile 流式重写（不再 7z a -si）：不调用 subprocess/7z，成功更新"""
    monkeypatch.setattr(config, "MODE_SKIP_XMLEXIST", 0)
    monkeypatch.setattr(zip_operations, "_check_seven_zip_available",
                        lambda: "7z.exe")
    zip_path = _make_zip(tmp_path / "vol01.zip",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")

    calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: calls.append(a)
        or subprocess.CompletedProcess(args=[], returncode=0))

    ok = zip_operations.add_file_to_zip(
        zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
        "ComicInfo.xml", target_ext=".zip")

    assert ok is True
    assert calls == []  # 不再调用 7z/subprocess
    with zipfile.ZipFile(zip_path) as zf:
        assert b"<Title>" in zf.read("ComicInfo.xml")  # 新 XML 已写入
        assert "000.png" in zf.namelist()  # 图片保留
    out = capsys.readouterr().out
    assert "使用zipfile成功更新文件" in out


def test_cb7_seven_zip_all_fail_fallback(monkeypatch, tmp_path, capsys):
    """.cb7 等非 zip 容器原地写仍走 7z，3 次全失败才回退 _fallback_write（语义不变）"""
    monkeypatch.setattr(config, "MODE_SKIP_XMLEXIST", 0)
    monkeypatch.setattr(zip_operations, "_check_seven_zip_available", lambda: "7z.exe")
    zip_path = _make_zip(tmp_path / "vol02.cb7",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    _patch_sleep(monkeypatch)

    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout="",
            stderr="System ERROR: 另一个程序正在使用此文件")

    monkeypatch.setattr(subprocess, "run", fake_run)

    fallback_calls = []

    def fake_fallback(*args, **kwargs):
        fallback_calls.append((args, kwargs))
        return True

    monkeypatch.setattr(zip_operations, "_fallback_write", fake_fallback)

    ok = zip_operations.add_file_to_zip(
        zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
        "ComicInfo.xml", target_ext=".cb7")

    assert ok is True  # 回退成功 → 整体成功
    assert len(calls) == 3  # 重试 3 次后才放弃 7z
    assert len(fallback_calls) == 1
    _, kwargs = fallback_calls[0]
    assert kwargs["target_ext"] == ".cb7"
    out = capsys.readouterr().out
    assert "7-Zip命令执行失败(重试3次)" in out
    assert "尝试通用归档格式处理" in out


def test_add_with_zipfile_replace_fail_cleanup(monkeypatch, tmp_path, capsys):
    """原子替换失败（占用类错误重试 3 次后仍失败）时返回 False 并清理临时文件"""
    zip_path = _make_zip(tmp_path / "vol03.cbz",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    sleep_calls = _patch_sleep(monkeypatch)
    seen_src = []

    def fake_replace(src, dst):
        seen_src.append(src)
        raise OSError(13, "Permission denied", dst)

    monkeypatch.setattr(os, "replace", fake_replace)

    ok = zip_operations._add_with_zipfile(
        zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
        "ComicInfo.xml", xml_exists=True)

    assert ok is False
    assert len(seen_src) == 3  # 占用类错误递增重试 3 次
    assert sleep_calls == [0.5, 1.0]  # sleep 0.5 / 1.0
    assert not os.path.exists(seen_src[0])  # 失败后临时文件已清理
    out = capsys.readouterr().out
    assert "回退方法失败" in out
    assert "vol03.cbz" in out  # 错误消息带文件名，可定位失败文件


def test_add_with_zipfile_replace_retry_then_success(monkeypatch, tmp_path):
    """os.replace 前两次 WinError 32(文件被占用)，第 3 次成功 → 重试恢复并返回 True"""
    zip_path = _make_zip(tmp_path / "vol04.cbz",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    sleep_calls = _patch_sleep(monkeypatch)
    seen_src = []
    real_replace = os.replace

    def flaky_replace(src, dst):
        seen_src.append(src)
        if len(seen_src) < 3:
            e = OSError(13, "另一个程序正在使用此文件", dst)
            e.winerror = 32
            raise e
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)

    ok = zip_operations._add_with_zipfile(
        zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
        "ComicInfo.xml", xml_exists=True)

    assert ok is True
    assert len(seen_src) == 3  # 前两次占用失败，第 3 次成功
    assert sleep_calls == [0.5, 1.0]
    with zipfile.ZipFile(zip_path) as zf:
        assert b"<Title>" in zf.read("ComicInfo.xml")  # 重试后替换成功


def test_add_with_zipfile_replace_no_retry_on_cross_device(monkeypatch, tmp_path, capsys):
    """非占用类错误（WinError 17 跨盘）不重试，直接失败返回 False"""
    zip_path = _make_zip(tmp_path / "vol05.cbz",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    sleep_calls = _patch_sleep(monkeypatch)
    seen_src = []

    def fake_replace(src, dst):
        seen_src.append(src)
        e = OSError(18, "系统无法将文件移到不同的驱动器", dst)
        e.winerror = 17
        raise e

    monkeypatch.setattr(os, "replace", fake_replace)

    ok = zip_operations._add_with_zipfile(
        zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
        "ComicInfo.xml", xml_exists=True)

    assert ok is False
    assert len(seen_src) == 1  # 非占用类错误不重试
    assert sleep_calls == []
    assert not os.path.exists(seen_src[0])
    out = capsys.readouterr().out
    assert "vol05.cbz" in out  # 错误消息带文件名
