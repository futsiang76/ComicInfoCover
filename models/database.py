import os
import sqlite3
from datetime import datetime


class LockDatabase:
    """锁定状态 SQLite 缓存"""

    DB_DIR = os.path.join(os.path.expanduser("~"), ".comicinfo_scratcher")
    DB_PATH = os.path.join(DB_DIR, "data.db")

    def __init__(self):
        os.makedirs(self.DB_DIR, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_locks (
                file_name     TEXT,
                file_size     INTEGER,
                series        TEXT,
                locked        INTEGER DEFAULT 0,
                updated_at    TEXT,
                PRIMARY KEY (file_name, file_size)
            )
        """)
        conn.commit()
        conn.close()

    def get_lock_state(self, file_name: str, file_size: int) -> bool:
        """查询锁定状态，返回 True/False，未找到返回 False"""
        conn = sqlite3.connect(self.DB_PATH)
        row = conn.execute(
            "SELECT locked FROM file_locks WHERE file_name=? AND file_size=?",
            (file_name, file_size)
        ).fetchone()
        conn.close()
        return bool(row[0]) if row else False

    def set_lock_state(self, file_name: str, file_size: int, series: str, locked: bool):
        """更新或插入锁定状态"""
        conn = sqlite3.connect(self.DB_PATH)
        conn.execute("""
            INSERT INTO file_locks (file_name, file_size, series, locked, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(file_name, file_size)
            DO UPDATE SET locked=excluded.locked, series=excluded.series, updated_at=excluded.updated_at
        """, (file_name, file_size, series, int(locked), datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def batch_get_lock_states(self, files: list) -> dict:
        """批量查询，files=[(file_name, file_size), ...]，返回 {(file_name, file_size): bool}"""
        if not files:
            return {}
        conn = sqlite3.connect(self.DB_PATH)
        placeholders = ",".join(["(?,?)"] * len(files))
        rows = conn.execute(
            f"SELECT file_name, file_size, locked FROM file_locks WHERE (file_name, file_size) IN ({placeholders})",
            [v for pair in files for v in pair]
        ).fetchall()
        conn.close()
        return {(r[0], r[1]): bool(r[2]) for r in rows}
