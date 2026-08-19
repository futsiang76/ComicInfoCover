#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7-Zip 更新 XML 失败重试机制测试

覆盖范围：
- 7z a -si 更新因文件占用（7z.exe 退出延迟，句柄未及时释放）失败后重试成功
- 重试 3 次仍失败才回退 _fallback_write（语义不变）
- _add_with_zipfile 回退路径中复制原 zip 到临时文件失败后重试成功
"""
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


def test_seven_zip_retry_success(monkeypatch, tmp_path, capsys):
    """7z 更新因文件占用失败 2 次后第 3 次成功，不走到回退"""
    monkeypatch.setattr(config, "MODE_SKIP_XMLEXIST", 0)
    monkeypatch.setattr(zip_operations, "_check_seven_zip_available", lambda: "7z.exe")
    zip_path = _make_zip(tmp_path / "vol01.zip")
    sleep_calls = _patch_sleep(monkeypatch)

    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        if len(calls) <= 2:
            return subprocess.CompletedProcess(
                args=args[0], returncode=1, stdout="",
                stderr="System ERROR: 另一个程序正在使用此文件")
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ok = zip_operations.add_file_to_zip(
        zip_path, "<ComicInfo><Title>测试</Title></ComicInfo>",
        "ComicInfo.xml", target_ext=".zip")

    assert ok is True
    assert len(calls) == 3  # 共执行 3 次 7z 更新
    assert len(sleep_calls) == 2  # 前 2 次失败各等待一次
    out = capsys.readouterr().out
    assert "使用7-Zip成功添加文件" in out  # zip 无 XML → 「成功添加」分支
    assert "尝试通用归档格式处理" not in out  # 未走到回退


def test_seven_zip_all_fail_fallback(monkeypatch, tmp_path, capsys):
    """7z 更新 3 次全失败才回退 _fallback_write（语义不变）"""
    monkeypatch.setattr(config, "MODE_SKIP_XMLEXIST", 0)
    monkeypatch.setattr(zip_operations, "_check_seven_zip_available", lambda: "7z.exe")
    zip_path = _make_zip(tmp_path / "vol02.zip",
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
        "ComicInfo.xml", target_ext=".zip")

    assert ok is True  # 回退成功 → 整体成功
    assert len(calls) == 3  # 重试 3 次后才放弃 7z
    assert len(fallback_calls) == 1
    _, kwargs = fallback_calls[0]
    assert kwargs["target_ext"] == ".zip"
    out = capsys.readouterr().out
    assert "7-Zip命令执行失败(重试3次)" in out
    assert "尝试通用归档格式处理" in out


def test_add_with_zipfile_copy2_retry(monkeypatch, tmp_path, capsys):
    """回退方法里复制原 zip 到临时文件失败 2 次后重试成功"""
    zip_path = _make_zip(tmp_path / "vol03.cbz",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    sleep_calls = _patch_sleep(monkeypatch)

    real_copy2 = shutil.copy2
    copy_calls = []

    def fake_copy2(src, dst, **kwargs):
        copy_calls.append((src, dst))
        if len(copy_calls) <= 2:
            raise OSError(32, "另一个程序正在使用此文件", dst)
        return real_copy2(src, dst, **kwargs)

    monkeypatch.setattr(shutil, "copy2", fake_copy2)

    ok = zip_operations._add_with_zipfile(
        zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
        "ComicInfo.xml", xml_exists=True)

    assert ok is True
    assert len(sleep_calls) == 2  # 复制失败 2 次各等待一次
    assert len(copy_calls) == 4  # 复制到临时文件重试 3 次 + 校验通过后写回 1 次
    out = capsys.readouterr().out
    assert "使用zipfile成功更新文件" in out