#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zipfile 流式重写（统一 STORE）核心行为测试

覆盖范围：
- DEFLATE 压缩原卷 → STORE 重写：图片字节完整、条目统一未压缩、新 XML 写入
- 逐条目流式复制：读一条写一条交错，不整卷先载入内存（大卷不爆内存）
"""
import os
import zipfile

from processors import zip_operations


def _make_deflate_zip(path, entries):
    """用 DEFLATE 压缩生成 zip/cbz（模拟真实压缩原卷）"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return str(path)


def test_deflate_volume_rewrite_to_store(tmp_path):
    """DEFLATE 压缩原卷统一重写为 STORE：图片保留、新 XML 写入、条目均未压缩"""
    pics = {"001.jpg": os.urandom(2 * 1024 * 1024),
            "002.jpg": os.urandom(512 * 1024)}
    path = _make_deflate_zip(
        tmp_path / "deflate.cbz",
        {**pics, "ComicInfo.xml": "<ComicInfo><Title>旧</Title></ComicInfo>"})

    with zipfile.ZipFile(path) as zf:
        assert zf.getinfo("001.jpg").compress_type == zipfile.ZIP_DEFLATED

    ok = zip_operations.add_file_to_zip(
        path, "<ComicInfo><Title>新</Title></ComicInfo>",
        "ComicInfo.xml", target_ext=".cbz")

    assert ok is True
    with zipfile.ZipFile(path) as zf:
        assert zf.getinfo("001.jpg").compress_type == zipfile.ZIP_STORED
        assert zf.getinfo("ComicInfo.xml").compress_type == zipfile.ZIP_STORED
        assert zf.read("001.jpg") == pics["001.jpg"]   # 图片字节完整
        assert zf.read("002.jpg") == pics["002.jpg"]
        xml = zf.read("ComicInfo.xml").decode("utf-8")
        assert "新" in xml  # 新 XML 已写入
        assert "旧" not in xml


def test_add_with_zipfile_streams_one_entry_at_a_time(monkeypatch, tmp_path):
    """逐条目流式复制：读/写按条交错，非先整卷读入内存再全量写出（不爆内存）"""
    n = 8
    pics = {f"img{i:03d}.jpg": os.urandom(64 * 1024) for i in range(n)}
    path = _make_deflate_zip(tmp_path / "stream.cbz", pics)

    events = []
    real_read = zipfile.ZipFile.read
    real_writestr = zipfile.ZipFile.writestr

    def tracked_read(self, name, *a, **k):
        events.append(("read", name))
        return real_read(self, name, *a, **k)

    def tracked_writestr(self, name, *a, **k):
        events.append(("write", name))
        return real_writestr(self, name, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "read", tracked_read)
    monkeypatch.setattr(zipfile.ZipFile, "writestr", tracked_writestr)

    ok = zip_operations._add_with_zipfile(
        path, "<ComicInfo><Title>新</Title></ComicInfo>", "ComicInfo.xml")

    assert ok is True
    # 复制阶段：source 条目按序 读→写 成对交错（流式，非先全读再全写）
    first = events[:2 * n]
    assert all(first[i][0] == "read" and first[i + 1][0] == "write"
               for i in range(0, 2 * n, 2))
    assert [nm for k, nm in first if k == "read"] == [
        f"img{i:03d}.jpg" for i in range(n)]
    assert events[2 * n] == ("write", "ComicInfo.xml")  # 源 XML 从未读入，新 XML 末位写入
    assert all(k == "read" for k, _ in events[0::2][:n])  # 读操作各条目恰好一次


def test_add_with_zipfile_temp_in_drive_root_tmpdir(monkeypatch, tmp_path):
    """临时文件放目标盘根 .comicscratch_tmp：os.replace 同盘 move，不进手同步目录"""
    import os as _os

    path = _make_deflate_zip(
        tmp_path / "drive_root.zip",
        {"001.jpg": os.urandom(32 * 1024)})

    replaces = []
    real_replace = _os.replace

    def tracked_replace(src, dst):
        replaces.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(_os, "replace", tracked_replace)

    ok = zip_operations._add_with_zipfile(
        path, "<ComicInfo><Title>新</Title></ComicInfo>", "ComicInfo.xml")

    assert ok is True
    assert len(replaces) == 1
    src, dst = replaces[0]
    # 临时文件在目标盘根 .comicscratch_tmp 目录下（uuid.tmp，非目标同目录）
    drive, _ = _os.path.splitdrive(_os.path.abspath(dst))
    expected_dir = _os.path.join(drive + _os.sep, ".comicscratch_tmp")
    assert _os.path.dirname(src) == expected_dir
    assert _os.path.basename(src).endswith(".tmp")
    assert src != dst
    # 成功后目标目录不残留任何临时文件（只剩 zip 本身）
    remaining = [f for f in _os.listdir(tmp_path)]
    assert remaining == ["drive_root.zip"]
