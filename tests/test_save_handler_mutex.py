"""save_handler 保存互斥测试 — 已有保存线程在跑时拦截第二次 save_changes

背景：save_changes 每次调用都 new 一个 SaveThread 并 start()，用户连点「保存」
会启动多个线程并发写同一批 zip（互相锁文件 → WinError 5 + 多份相同 tmp）。
本测试验证互斥：线程在跑时第二次调用被拦下，运行中保存线程数始终 ≤1；
扫描进行中的逐系列保存（_scan_running 为 True）不受互斥约束。
"""
from gui import save_handler


class _FakeSignal:
    """极简 Signal 替身：只记录 connect，不真正跨线程派发"""

    def connect(self, slot):
        self.slot = slot


class _FakeSaveThread:
    """伪保存线程：start 只记录不真写盘；isRunning 由 _running 控制"""

    def __init__(self, modified_results, mw):
        self.modified_results = modified_results
        self._running = True
        self.save_finished = _FakeSignal()

    def isRunning(self):
        return self._running

    def start(self):
        self.started = True


def _make_result():
    return {
        "folder_path": "C:/fake/Series",
        "series": "FakeSeries",
        "process_status": "已修改",
        "file_titles": {},
        "file_details": {},
        "locked_files": set(),
    }


def _patch_ui(monkeypatch):
    """离屏测试下弹窗会阻塞 → 全部 mock 掉；SaveThread 换伪实现不真写盘"""
    monkeypatch.setattr(save_handler.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(save_handler.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(save_handler, "SaveThread", _FakeSaveThread)


def test_save_changes_blocks_second_concurrent_save(app, monkeypatch):
    """连续调两次 save_changes：第二次被互斥拦截，不启动第二个保存线程"""
    window = app
    window.scan_results = [_make_result()]
    _patch_ui(monkeypatch)

    save_handler.save_changes(window)   # 第一次：启动保存线程
    save_handler.save_changes(window)   # 第二次：应被拦截

    running = [t for t in window._save_threads if t.isRunning()]
    assert len(running) == 1          # 运行中线程数始终 ≤1
    assert running[0].started is True
    assert window._save_count == 1    # 写盘计数只 +1，收尾不会被二次扣减搞乱

    # 线程结束后再次保存应放行
    running[0]._running = False
    save_handler.save_changes(window)
    assert len([t for t in window._save_threads if t.isRunning()]) == 1
    assert window._save_count == 2


def test_save_changes_skips_mutex_while_scan_running(app, monkeypatch):
    """扫描进行中的逐系列保存不受互斥约束（扫描流程负责其收尾）"""
    window = app
    window.scan_results = [_make_result()]

    class _FakeScanThread:
        def isRunning(self):
            return True

    window.scan_thread = _FakeScanThread()
    _patch_ui(monkeypatch)

    save_handler.save_changes(window)
    save_handler.save_changes(window)  # 扫描中：跳过互斥，不拦截

    assert len([t for t in window._save_threads if t.isRunning()]) == 2
