#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描阶段 process_comic_files 写失败处理测试

覆盖范围：
- add_file_to_zip 返回 False（写入失败）时：success_files 不含失败文件、
  失败文件不重试（每文件只调一次 add_file_to_zip）
- add_file_to_zip 抛异常（如 os.replace WinError 5 重试后仍失败）时：
  只标记该文件失败，不中断整个文件夹的扫描
- 内容一致跳过（None）仍计入 success_files（跳过=成功处理）
"""
import os

from unittest.mock import Mock

from processors.zip_handler import FileHandler


def _make_folder(tmp_path, names):
    """在 tmp_path 下创建空的伪漫画文件（不依赖真实 zip 内容，add_file_to_zip 被 mock）"""
    for n in names:
        (tmp_path / n).write_bytes(b"fake")
    return str(tmp_path)


def _make_handler():
    handler = FileHandler()
    handler.xml_generator = Mock(generate_for_file=Mock(return_value="<ComicInfo/>"))
    return handler


def test_failed_file_not_counted_and_not_retried(monkeypatch, tmp_path, capsys):
    """add_file_to_zip 返回 False：失败文件不计入 success_files，且不再重试"""
    folder = _make_folder(tmp_path, ["vol01.zip", "vol02.zip", "vol03.zip"])

    calls = []
    def fake_add(zip_path, xml_content):
        calls.append(os.path.basename(zip_path))
        return os.path.basename(zip_path) != "vol01.zip"  # vol01 失败，其余成功

    monkeypatch.setattr("processors.zip_handler.add_file_to_zip", fake_add)
    handler = _make_handler()

    total, success = handler.process_comic_files(
        folder, {"Series": "测试"}, {"series": "测试"}, manga_value="Yes"
    )

    assert total == 3
    assert success == 2  # vol02/vol03 成功，vol01 失败不计入
    assert calls == ["vol01.zip", "vol02.zip", "vol03.zip"]  # 每文件恰好一次，失败不重试

    out = capsys.readouterr().out
    assert "❌ 写入失败: vol01.zip" in out
    assert "本次扫描不再重试" in out
    assert "写入失败 1 个文件" in out


def test_exception_marks_failed_and_continues_folder(monkeypatch, tmp_path, capsys):
    """add_file_to_zip 抛异常（os.replace WinError 5 重试后仍失败）：标记失败并继续处理其它文件"""
    folder = _make_folder(tmp_path, ["vol01.zip", "vol02.zip", "vol03.zip"])

    calls = []
    def fake_add(zip_path, xml_content):
        calls.append(os.path.basename(zip_path))
        if os.path.basename(zip_path) == "vol01.zip":
            raise OSError(13, "Permission denied", "vol01.zip", 5)  # WinError 5
        return True

    monkeypatch.setattr("processors.zip_handler.add_file_to_zip", fake_add)
    handler = _make_handler()

    total, success = handler.process_comic_files(
        folder, {"Series": "测试"}, {"series": "测试"}, manga_value="Yes"
    )

    assert total == 3
    assert success == 2  # vol01 异常失败不计入，vol02/vol03 正常处理
    assert calls == ["vol01.zip", "vol02.zip", "vol03.zip"]  # 失败不重试，且不中断扫描

    out = capsys.readouterr().out
    assert "❌ 写入失败: vol01.zip（本次扫描不再重试）" in out
    assert "写入失败 1 个文件" in out


def test_skip_content_consistent_counts_as_success(monkeypatch, tmp_path, capsys):
    """add_file_to_zip 返回非 True/False（内容一致跳过）：计入 success_files"""
    folder = _make_folder(tmp_path, ["vol01.zip", "vol02.zip"])

    def fake_add(zip_path, xml_content):
        return None  # 跳过（内容一致）语义

    monkeypatch.setattr("processors.zip_handler.add_file_to_zip", fake_add)
    handler = _make_handler()

    total, success = handler.process_comic_files(
        folder, {"Series": "测试"}, {"series": "测试"}, manga_value="Yes"
    )

    assert total == 2
    assert success == 2  # 跳过也算成功处理
    out = capsys.readouterr().out
    assert out.count("⏭️  跳过文件（内容一致）") == 2
