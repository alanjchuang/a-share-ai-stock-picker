from __future__ import annotations

import json
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

from app.db.database import get_connection
from app.models.schemas import OneClickRecommendRequest, OneClickRecommendResponse
from app.services.recommendation_service import RecommendationService


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="recommendation-job")
_state_lock = Lock()
_active_future: Future[None] | None = None
_active_job_id: int | None = None
_STALE_JOB_MINUTES = 30
_STALE_JOB_MESSAGE = "一键荐股任务已中断或服务重启，请重新发起。"


def submit_one_click_recommendation_job(payload: OneClickRecommendRequest) -> dict[str, Any]:
    global _active_future, _active_job_id
    with _state_lock:
        if _active_future and not _active_future.done() and _active_job_id:
            return {
                "accepted": False,
                "job_id": _active_job_id,
                "job_type": "one_click_recommendation",
                "status": "running",
                "message": "已有一键荐股任务正在后台运行，请稍后查看结果。",
            }
        conn: sqlite3.Connection | None = None
        try:
            conn = get_connection()
            _ensure_table(conn)
            _expire_stale_jobs(conn)
            job_id = _insert_job(conn, payload)
        finally:
            if conn:
                conn.close()
        _active_job_id = job_id
        _active_future = _executor.submit(_run_job, job_id, payload)
        return {
            "accepted": True,
            "job_id": job_id,
            "job_type": "one_click_recommendation",
            "status": "queued",
            "message": "一键荐股已进入后台任务，完成后会自动展示结果。",
        }


def get_one_click_recommendation_job(job_id: int) -> dict[str, Any] | None:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        _ensure_table(conn)
        _expire_stale_jobs(conn)
        row = conn.execute("SELECT * FROM recommendation_jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_out(dict(row)) if row else None
    finally:
        if conn:
            conn.close()


def list_one_click_recommendation_jobs(limit: int = 20) -> list[dict[str, Any]]:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        _ensure_table(conn)
        _expire_stale_jobs(conn)
        safe_limit = min(max(int(limit or 20), 1), 100)
        rows = conn.execute(
            """
            SELECT *
            FROM recommendation_jobs
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return [_job_out(dict(row)) for row in rows]
    finally:
        if conn:
            conn.close()


def _run_job(job_id: int, payload: OneClickRecommendRequest) -> None:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        _ensure_table(conn)
        _update_job(conn, job_id, "running", "正在后台筛选候选股、检索资料并调用模型生成研究推荐。")
        result = RecommendationService(conn).one_click(payload)
        _update_job(
            conn,
            job_id,
            "success",
            f"一键荐股完成，生成 {len(result.recommendations)} 条研究候选。",
            result=result,
            finished=True,
        )
    except Exception as exc:
        if conn:
            conn.rollback()
            _update_job(conn, job_id, "failed", str(exc), finished=True)
    finally:
        if conn:
            conn.close()
        _clear_active(job_id)


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL DEFAULT 'one_click_recommendation',
            status TEXT NOT NULL,
            message TEXT DEFAULT '',
            request_json TEXT DEFAULT '',
            result_json TEXT DEFAULT '',
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recommendation_jobs_status_started ON recommendation_jobs(status, started_at)")
    conn.commit()


def _expire_stale_jobs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE recommendation_jobs
        SET status='failed',
            message=?,
            finished_at=CURRENT_TIMESTAMP
        WHERE status IN ('queued', 'running')
          AND finished_at IS NULL
          AND datetime(started_at) <= datetime('now', ?)
        """,
        (_STALE_JOB_MESSAGE, f"-{_STALE_JOB_MINUTES} minutes"),
    )
    conn.commit()


def _insert_job(conn: sqlite3.Connection, payload: OneClickRecommendRequest) -> int:
    cursor = conn.execute(
        """
        INSERT INTO recommendation_jobs(job_type, status, message, request_json)
        VALUES ('one_click_recommendation', 'queued', ?, ?)
        """,
        ("一键荐股已进入后台任务，完成后会自动展示结果。", payload.model_dump_json()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _update_job(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    message: str,
    *,
    result: OneClickRecommendResponse | None = None,
    finished: bool = False,
) -> None:
    result_json = result.model_dump_json() if result else None
    if finished:
        if result_json is None:
            conn.execute(
                "UPDATE recommendation_jobs SET status=?, message=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, message, job_id),
            )
        else:
            conn.execute(
                """
                UPDATE recommendation_jobs
                SET status=?, message=?, result_json=?, finished_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (status, message, result_json, job_id),
            )
    else:
        conn.execute("UPDATE recommendation_jobs SET status=?, message=? WHERE id=?", (status, message, job_id))
    conn.commit()


def _clear_active(job_id: int) -> None:
    global _active_job_id
    with _state_lock:
        if _active_job_id == job_id:
            _active_job_id = None


def _job_out(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] | None = None
    if row.get("result_json"):
        try:
            parsed = json.loads(str(row["result_json"]))
            if isinstance(parsed, dict):
                result = parsed
        except json.JSONDecodeError:
            result = None
    return {
        "id": int(row["id"]),
        "job_type": str(row.get("job_type") or "one_click_recommendation"),
        "status": str(row["status"]),
        "message": str(row.get("message") or ""),
        "started_at": str(row.get("started_at") or ""),
        "finished_at": row.get("finished_at"),
        "result": result,
    }
