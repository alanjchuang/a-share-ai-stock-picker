from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from threading import Lock

from app.core.config import load_settings

_wal_lock = Lock()
_wal_ready_paths: set[Path] = set()


def _ensure_wal_mode(db_path: Path) -> None:
    """WAL只需要按数据库文件设置一次，避免每个请求连接都尝试切换日志模式造成锁竞争。"""
    resolved = db_path.resolve()
    if resolved in _wal_ready_paths:
        return
    with _wal_lock:
        if resolved in _wal_ready_paths:
            return
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
        _wal_ready_paths.add(resolved)


def get_connection() -> sqlite3.Connection:
    settings = load_settings()
    db_path = settings.db_path
    _ensure_wal_mode(db_path)
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    conn = get_connection()
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
