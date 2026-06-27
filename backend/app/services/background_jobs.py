from __future__ import annotations

import sqlite3
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

from app.db.database import get_connection
from app.models.schemas import SyncRequest
from app.services.akshare_service import AkshareService
from app.services.factor_engine import FactorEngine
from app.services.data_quality_service import DataQualityService
from app.services.market_data_service import MarketDataService
from app.services.sentiment_service import SentimentService


JobTask = Callable[[sqlite3.Connection], dict[str, Any]]
SuccessMessage = Callable[[dict[str, Any]], str]

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stock-background-job")
_state_lock = Lock()
_writer_lock = Lock()
_active_future: Future[None] | None = None
_active_job: dict[str, Any] | None = None


def _busy_response(job_type: str) -> dict[str, Any]:
    active = _active_job or {}
    return {
        "accepted": False,
        "job_id": active.get("job_id"),
        "job_type": active.get("job_type") or job_type,
        "status": "running",
        "message": "已有后台数据任务正在运行，本次请求已跳过；前台会继续使用现有缓存。",
    }


def _insert_job(conn: sqlite3.Connection, job_type: str, status: str, message: str) -> int:
    cursor = conn.execute(
        "INSERT INTO sync_jobs(job_type, status, message) VALUES (?, ?, ?)",
        (job_type, status, message),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _update_job(conn: sqlite3.Connection, job_id: int, status: str, message: str, finished: bool = False) -> None:
    if finished:
        conn.execute(
            "UPDATE sync_jobs SET status=?, message=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, message, job_id),
        )
    else:
        conn.execute("UPDATE sync_jobs SET status=?, message=? WHERE id=?", (status, message, job_id))
    conn.commit()


def mark_interrupted_jobs(conn: sqlite3.Connection) -> int:
    """服务重启后清理遗留任务状态。

    后台任务只存在于当前进程内；如果服务在任务执行中被重启，SQLite里的 running/queued
    记录不会自动完成。启动时把这些记录标记为 failed，避免数据中心误以为旧任务仍在执行。
    """
    cursor = conn.execute(
        """
        UPDATE sync_jobs
        SET status='failed',
            message=message || '（服务已重启，任务已中断，请重新触发。）',
            finished_at=CURRENT_TIMESTAMP
        WHERE status IN ('queued', 'running') AND finished_at IS NULL
        """
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def _clear_active(job_id: int) -> None:
    global _active_job
    with _state_lock:
        if _active_job and _active_job.get("job_id") == job_id:
            _active_job = None


def _run_with_acquired_lock(
    job_id: int,
    job_type: str,
    running_message: str,
    task: JobTask,
    success_message: SuccessMessage,
) -> None:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        _update_job(conn, job_id, "running", running_message)
        result = task(conn)
        _update_job(conn, job_id, "success", success_message(result), finished=True)
    except Exception as exc:
        if conn:
            conn.rollback()
            _update_job(conn, job_id, "failed", str(exc), finished=True)
    finally:
        if conn:
            conn.close()
        _writer_lock.release()
        _clear_active(job_id)


def submit_exclusive_db_job(
    job_type: str,
    queued_message: str,
    running_message: str,
    task: JobTask,
    success_message: SuccessMessage,
) -> dict[str, Any]:
    """提交单写者后台任务。

    SQLite同一时间只能有一个写者。这里把行情同步、因子重算这类重任务串行化，
    让页面点击继续读旧缓存，避免把锁等待暴露给用户。
    """
    global _active_future, _active_job
    with _state_lock:
        if _active_future and not _active_future.done():
            return _busy_response(job_type)
        if not _writer_lock.acquire(blocking=False):
            return _busy_response(job_type)
        conn: sqlite3.Connection | None = None
        try:
            conn = get_connection()
            job_id = _insert_job(conn, job_type, "queued", queued_message)
        except Exception:
            _writer_lock.release()
            raise
        finally:
            if conn:
                conn.close()
        _active_job = {"job_id": job_id, "job_type": job_type}
        _active_future = _executor.submit(_run_with_acquired_lock, job_id, job_type, running_message, task, success_message)
        return {
            "accepted": True,
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "message": queued_message,
        }


def run_exclusive_db_job_now(
    job_type: str,
    running_message: str,
    task: JobTask,
    success_message: SuccessMessage,
) -> dict[str, Any]:
    if not _writer_lock.acquire(blocking=False):
        return _busy_response(job_type)
    conn: sqlite3.Connection | None = None
    job_id: int | None = None
    try:
        conn = get_connection()
        job_id = _insert_job(conn, job_type, "running", running_message)
        result = task(conn)
        message = success_message(result)
        _update_job(conn, job_id, "success", message, finished=True)
        return {"accepted": True, "job_id": job_id, "job_type": job_type, "status": "success", "message": message}
    except Exception as exc:
        if conn:
            conn.rollback()
            if job_id:
                _update_job(conn, job_id, "failed", str(exc), finished=True)
        return {"accepted": False, "job_id": job_id, "job_type": job_type, "status": "failed", "message": str(exc)}
    finally:
        if conn:
            conn.close()
        _writer_lock.release()


def _sync_task(payload: SyncRequest) -> JobTask:
    def task(conn: sqlite3.Connection) -> dict[str, Any]:
        sync_result = MarketDataService(conn).sync(payload)
        quality_result = DataQualityService(conn).clean_mixed_demo_rows()
        sentiment_count = SentimentService(conn).batch_refresh_existing(limit=300)
        factor_rows = FactorEngine(conn).calculate_all(force=True)
        return {"sync": sync_result, "quality": quality_result, "sentiment_count": sentiment_count, "factor_count": len(factor_rows)}

    return task


def _factor_task(force: bool) -> JobTask:
    def task(conn: sqlite3.Connection) -> dict[str, Any]:
        rows = FactorEngine(conn).calculate_all(force=force)
        return {"factor_count": len(rows)}

    return task


def _stock_history_task(ts_code: str) -> JobTask:
    def task(conn: sqlite3.Connection) -> dict[str, Any]:
        sync_result = AkshareService(conn).sync_stock_history(ts_code)
        quality_result = DataQualityService(conn).clean_mixed_demo_rows()
        factor_rows = FactorEngine(conn).calculate_all(force=True)
        return {"sync": sync_result, "quality": quality_result, "factor_count": len(factor_rows)}

    return task


def submit_sync_refresh_job(payload: SyncRequest) -> dict[str, Any]:
    return submit_exclusive_db_job(
        "manual_sync",
        "数据同步与因子刷新已进入后台队列，前台继续使用现有缓存。",
        "正在后台同步行情、舆情并刷新因子缓存。",
        _sync_task(payload),
        lambda result: f"同步完成，因子缓存覆盖 {result.get('factor_count', 0)} 只股票。",
    )


def submit_factor_refresh_job(force: bool = True, job_type: str = "manual_factor_refresh") -> dict[str, Any]:
    return submit_exclusive_db_job(
        job_type,
        "因子缓存刷新已进入后台队列，前台继续使用现有缓存。",
        "正在后台刷新因子缓存。",
        _factor_task(force),
        lambda result: f"因子缓存已刷新：{result.get('factor_count', 0)} 只股票。",
    )


def submit_stock_history_job(ts_code: str) -> dict[str, Any]:
    return submit_exclusive_db_job(
        "stock_history_sync",
        f"{ts_code} 历史K线补齐已进入后台队列，前台继续使用现有缓存。",
        f"正在后台补齐 {ts_code} 历史K线并刷新因子缓存。",
        _stock_history_task(ts_code),
        lambda result: (
            f"{ts_code} 历史K线补齐完成，新增/覆盖 "
            f"{result.get('sync', {}).get('rows', 0)} 条K线，因子缓存覆盖 {result.get('factor_count', 0)} 只股票。"
        ),
    )


def run_scheduled_sync_job() -> dict[str, Any]:
    return run_exclusive_db_job_now(
        "daily_sync",
        "正在执行每日后台同步。",
        _sync_task(SyncRequest()),
        lambda result: f"每日同步完成，因子缓存覆盖 {result.get('factor_count', 0)} 只股票。",
    )


def run_scheduled_factor_cache_job() -> dict[str, Any]:
    return run_exclusive_db_job_now(
        "factor_cache_warmup",
        "正在预热因子缓存。",
        _factor_task(force=False),
        lambda result: f"因子缓存预热完成：{result.get('factor_count', 0)} 只股票。",
    )
