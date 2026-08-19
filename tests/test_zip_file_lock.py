#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zip 写盘文件级互斥锁测试（多实例安全）

覆盖范围：
- 同一 zip 两实例/线程抢锁：第一个持锁期间，第二个等待超时返回 False 且不写坏文件
- 不同 zip 两把锁互不阻塞
- 锁释放后第二个可正常获取（成功/失败路径都释放）
- 崩溃残留锁（持有者 PID 已死）自动清除、可正常获取
- 等待期间每 10s 打印 ⏳ 进度提示
- 同线程嵌套获取同一把锁（重入）不死锁
"""
import os
import threading
import time
import zipfile

import pytest

from processors import utils, zip_operations
from processors.utils import zip_lock


def _make_zip(path, xml: str = None) -> str:
    """生成含一张图片（可选含 ComicInfo.xml）的 zip 文件"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("000.png", b"fake-image-bytes")
        if xml is not None:
            zf.writestr("ComicInfo.xml", xml)
    return str(path)


@pytest.fixture
def fast_lock(monkeypatch):
    """锁冲突快速失败：1 轮尝试 + 极短等待，避免测试真等 120s"""
    monkeypatch.setattr(utils, "ZIP_LOCK_ATTEMPTS", 1)
    monkeypatch.setattr(utils, "ZIP_LOCK_WAIT_MS", 20)


def test_same_zip_second_writer_times_out(fast_lock, tmp_path, capsys):
    """同一 zip：第一个持锁期间，第二个写盘超时返回 False，且不写坏文件"""
    zip_path = _make_zip(
        tmp_path / "vol01.zip",
        xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    held = threading.Event()
    release = threading.Event()

    def holder():
        with zip_lock(zip_path):
            held.set()
            release.wait(10)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    try:
        assert held.wait(10), "持锁线程未就绪"
        ok = zip_operations._add_with_zipfile(
            zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
            "ComicInfo.xml", xml_exists=True)
        assert ok is False
        out = capsys.readouterr().out
        assert "文件被锁定超时" in out
        assert "vol01.zip" in out  # 提示带文件名（file_tag 格式）
        # 未写坏：XML 仍是旧内容，图片条目完整
        with zipfile.ZipFile(zip_path) as zf:
            assert "旧".encode("utf-8") in zf.read("ComicInfo.xml")
            assert "000.png" in zf.namelist()
    finally:
        release.set()
        t.join(10)


def test_different_zips_do_not_block(tmp_path):
    """不同 zip 两把锁互不阻塞：持锁 A 时写 B 正常完成"""
    zip_a = _make_zip(tmp_path / "a.zip",
                      xml="<ComicInfo><Title>A旧</Title></ComicInfo>")
    zip_b = _make_zip(tmp_path / "b.zip",
                      xml="<ComicInfo><Title>B旧</Title></ComicInfo>")
    with zip_lock(zip_a):
        ok = zip_operations._add_with_zipfile(
            zip_b, "<ComicInfo><Title>B新</Title></ComicInfo>",
            "ComicInfo.xml", xml_exists=True)
    assert ok is True
    with zipfile.ZipFile(zip_b) as zf:
        assert "B新".encode("utf-8") in zf.read("ComicInfo.xml")


def test_lock_released_then_reacquired(tmp_path):
    """锁释放后第二个可正常获取：连续两次写同一 zip 都成功，且锁文件已清除"""
    zip_path = _make_zip(tmp_path / "vol02.zip",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    ok1 = zip_operations._add_with_zipfile(
        zip_path, "<ComicInfo><Title>一</Title></ComicInfo>",
        "ComicInfo.xml", xml_exists=True)
    assert ok1 is True
    lock_path = utils._zip_lock_path(zip_path)
    assert not os.path.exists(lock_path)  # 成功后锁已释放（文件已删）
    ok2 = zip_operations._add_with_zipfile(
        zip_path, "<ComicInfo><Title>二</Title></ComicInfo>",
        "ComicInfo.xml", xml_exists=True)
    assert ok2 is True
    with zipfile.ZipFile(zip_path) as zf:
        assert "二".encode("utf-8") in zf.read("ComicInfo.xml")
    assert not os.path.exists(lock_path)


def test_lock_released_after_failed_write(monkeypatch, tmp_path):
    """写盘失败（os.replace 占用类错误重试后仍失败）也必须释放锁"""
    zip_path = _make_zip(tmp_path / "vol03.cbz",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    monkeypatch.setattr("time.sleep", lambda s: None)  # 不等真实时间

    def fake_replace(src, dst):
        raise OSError(13, "Permission denied", dst)

    monkeypatch.setattr(os, "replace", fake_replace)
    ok = zip_operations._add_with_zipfile(
        zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
        "ComicInfo.xml", xml_exists=True)
    assert ok is False
    assert not os.path.exists(utils._zip_lock_path(zip_path))  # 失败路径也释放锁
    # 释放后立即可重新获取
    with zip_lock(zip_path) as locked:
        assert locked is True


def test_stale_lock_auto_cleared(tmp_path):
    """崩溃残留锁（持有者 PID 已死）自动清除：可正常获取，不永久卡死"""
    zip_path = _make_zip(tmp_path / "vol04.zip",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    lock_path = utils._zip_lock_path(zip_path)
    # 模拟崩溃残留：写入一个不可能存活的 PID 的锁文件（Qt/自实现同格式：首行 PID）
    dead_pid = 2 ** 31 - 1
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f"{dead_pid}\nstale-host\n2026-01-01 00:00:00\n")
    with zip_lock(zip_path) as locked:
        assert locked is True
    assert not os.path.exists(lock_path)  # 残留锁已被清除


def test_stale_lock_live_pid_not_removed(fast_lock, tmp_path, capsys):
    """活锁（持有者 PID 存活）不被误删：另一线程持锁时第二个仍超时失败"""
    zip_path = _make_zip(tmp_path / "vol05.zip",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    held = threading.Event()
    release = threading.Event()

    def holder():
        with zip_lock(zip_path):
            held.set()
            release.wait(10)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    try:
        assert held.wait(10)
        ok = zip_operations._add_with_zipfile(
            zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
            "ComicInfo.xml", xml_exists=True)
        assert ok is False  # 持锁线程存活 → 锁不被判 stale → 超时失败
        assert "文件被锁定超时" in capsys.readouterr().out
    finally:
        release.set()
        t.join(10)


def test_wait_progress_printed_every_10s(monkeypatch, tmp_path, capsys):
    """等待期间每 10s 打印 ⏳ 进度提示（已等待 Ns），避免用户以为卡死"""
    zip_path = _make_zip(tmp_path / "vol06.zip",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    sleep_calls = []
    monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(utils, "ZIP_LOCK_ATTEMPTS", 6)
    monkeypatch.setattr(utils, "ZIP_LOCK_WAIT_MS", 2000)  # 2s×6 → 到 10s 处打一次提示
    held = threading.Event()
    release = threading.Event()

    def holder():
        with zip_lock(zip_path):
            held.set()
            release.wait(10)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    try:
        assert held.wait(10)
        ok = zip_operations._add_with_zipfile(
            zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
            "ComicInfo.xml", xml_exists=True)
        assert ok is False
        out = capsys.readouterr().out
        assert "⏳ 等待另一实例释放锁" in out
        assert "已等待 10s" in out
        assert "文件被锁定超时" in out
        assert len(sleep_calls) == 5  # 6 轮尝试，前 5 轮各等 2s
    finally:
        release.set()
        t.join(10)


def test_convert_container_same_source_second_fails(fast_lock, tmp_path, capsys):
    """转换类写盘（源+目标双锁）：同一源文件被持锁时第二个转换超时失败"""
    zip_path = _make_zip(tmp_path / "vol07.cbz",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    held = threading.Event()
    release = threading.Event()

    def holder():
        with zip_lock(zip_path):
            held.set()
            release.wait(10)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    try:
        assert held.wait(10)
        ok = zip_operations._convert_zip_container(
            zip_path, "<ComicInfo><Title>新</Title></ComicInfo>",
            "ComicInfo.xml", ".zip")
        assert ok is False
        assert "文件被锁定超时" in capsys.readouterr().out
        assert not os.path.exists(os.path.splitext(zip_path)[0] + ".zip")  # 未产出半成品
    finally:
        release.set()
        t.join(10)


def test_same_thread_nested_lock_reentrant(tmp_path):
    """同线程嵌套获取同一把锁（7z 路径 → 回退 → _add_with_zipfile 链）不死锁"""
    zip_path = _make_zip(tmp_path / "vol08.zip",
                         xml="<ComicInfo><Title>旧</Title></ComicInfo>")
    with zip_lock(zip_path) as outer:
        assert outer is True
        with zip_lock(zip_path) as inner:  # 重入：引用计数放行
            assert inner is True
    assert not os.path.exists(utils._zip_lock_path(zip_path))  # 最外层退出才删锁
