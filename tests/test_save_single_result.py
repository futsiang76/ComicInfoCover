"""save_single_result 逐系列保存测试 — 全匹配模式每确认一个系列只写当前这一个 result

背景：_on_full_match_series_saved 原实现调 save_changes，后者收集 scan_results 里
【所有】"已修改"结果 → 系列 B 确认时把已写盘的 A 再写一遍，C 确认时 A+B 再写一遍，
多个 SaveThread 并发写同一批 zip（互相锁文件 WinError 5 + 多份相同 tmp）。

save_single_result 只保存当前 result；已有保存线程在跑时结果入 FIFO 等待队列，
前一个完成后自动续写——任意时刻保存线程数 ≤1，每个已确认系列都保证落盘，
且不会把前面的系列重复写入。
"""
from gui import save_handler
from gui.scan_controller import _on_full_match_series_saved


class _FakeSignal:
    """极简 Signal 替身：只记录 connect，不真正跨线程派发"""

    def connect(self, slot):
        self.slot = slot


class _FakeSaveThread:
    """伪保存线程：start 只记录不真写盘；isRunning 由 _running 控制"""

    def __init__(self, modified_results, mw):
        self.modified_results = modified_results
        self._running = True
        self.started = False
        self.save_finished = _FakeSignal()

    def isRunning(self):
        return self._running

    def start(self):
        self.started = True


def _make_result(series: str) -> dict:
    return {
        "folder_path": f"C:/fake/{series}",
        "series": series,
        "process_status": "已修改",
        "file_titles": {},
        "file_details": {},
        "locked_files": set(),
    }


def _running_threads(window) -> list:
    return [t for t in getattr(window, "_save_threads", []) if t.isRunning()]


def _finish(thread, window) -> None:
    """模拟保存线程完成：置 isRunning=False 并派发 save_finished 信号（驱动队列续写）"""
    thread._running = False
    thread.save_finished.slot(1, 1, [])  # (total_files, success_files, error_messages)


def _patch_ui(window, monkeypatch):
    """离屏测试下弹窗/表格刷新会阻塞或依赖真实控件 → 全部 mock 掉；SaveThread 换伪实现"""
    monkeypatch.setattr(save_handler.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(save_handler.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(save_handler, "SaveThread", _FakeSaveThread)
    monkeypatch.setattr(window, "update_results_table", lambda: None)


def test_series_saved_saves_only_current_result(app, monkeypatch):
    """连续确认 3 个系列（前一个已写完才确认下一个）：每个线程只含自己的 result"""
    window = app
    _patch_ui(window, monkeypatch)

    _on_full_match_series_saved(window, _make_result("A"))
    t1 = _running_threads(window)[0]
    assert [r["series"] for r in t1.modified_results] == ["A"]
    assert len(_running_threads(window)) == 1

    _finish(t1, window)
    _on_full_match_series_saved(window, _make_result("B"))
    t2 = _running_threads(window)[0]
    assert [r["series"] for r in t2.modified_results] == ["B"]  # 只含 B，不含 A
    assert len(_running_threads(window)) == 1

    _finish(t2, window)
    _on_full_match_series_saved(window, _make_result("C"))
    t3 = _running_threads(window)[0]
    assert [r["series"] for r in t3.modified_results] == ["C"]  # 只含 C，不含 A/B
    assert len(_running_threads(window)) == 1

    _finish(t3, window)
    assert [r["series"] for r in window.scan_results] == ["A", "B", "C"]
    assert all(r["process_status"] == "已保存" for r in window.scan_results)


def test_series_saved_queues_while_save_running(app, monkeypatch):
    """保存线程在跑时再确认系列：入队等待，前一个完成后才续写——任意时刻 ≤1 个线程"""
    window = app
    _patch_ui(window, monkeypatch)

    _on_full_match_series_saved(window, _make_result("A"))
    _on_full_match_series_saved(window, _make_result("B"))  # t1 在跑 → B 入队
    _on_full_match_series_saved(window, _make_result("C"))  # 仍在跑 → C 入队

    running = _running_threads(window)
    assert len(running) == 1
    assert [r["series"] for r in running[0].modified_results] == ["A"]
    assert window._save_count == 1  # 只 +1，没有被叠加
    assert [r["series"] for r, _ in window._save_pending] == ["B", "C"]

    # t1 完成 → B 自动续写
    _finish(running[0], window)
    running = _running_threads(window)
    assert len(running) == 1
    assert [r["series"] for r in running[0].modified_results] == ["B"]
    assert [r["series"] for r, _ in window._save_pending] == ["C"]

    # t2 完成 → C 自动续写
    _finish(running[0], window)
    running = _running_threads(window)
    assert len(running) == 1
    assert [r["series"] for r in running[0].modified_results] == ["C"]
    assert window._save_pending == []

    # 全部完成
    _finish(running[0], window)
    assert _running_threads(window) == []
    assert all(r["process_status"] == "已保存" for r in window.scan_results)


def test_no_result_accumulation_across_series(app, monkeypatch):
    """核心回归：后一次保存绝不包含前面已确认系列的 result（旧实现会 A → A+B → A+B+C 叠加）"""
    window = app
    _patch_ui(window, monkeypatch)

    _on_full_match_series_saved(window, _make_result("A"))
    _on_full_match_series_saved(window, _make_result("B"))
    _on_full_match_series_saved(window, _make_result("C"))

    # 三个确认全部到达时只启动了 1 个线程，且只写 A
    running = _running_threads(window)
    assert len(running) == 1
    assert [r["series"] for r in running[0].modified_results] == ["A"]

    # 依次完成后，每个系列恰好被写一次
    written = []
    while _running_threads(window):
        t = _running_threads(window)[0]
        written.append(t.modified_results[0]["series"])
        _finish(t, window)
    assert written == ["A", "B", "C"]


def test_pending_skips_result_already_written(app, monkeypatch):
    """队列续写时跳过已被其它路径（如手动保存）写盘的 result，避免重复写"""
    window = app
    _patch_ui(window, monkeypatch)

    _on_full_match_series_saved(window, _make_result("A"))
    _on_full_match_series_saved(window, _make_result("B"))  # t1 在跑 → B 入队

    # 模拟手动保存把 B 写盘了
    window.scan_results[1]["process_status"] = "已保存"

    _finish(_running_threads(window)[0], window)  # A 完成 → 续写队列
    assert _running_threads(window) == []  # B 已写盘 → 跳过，不再启动线程
    assert window._save_pending == []
