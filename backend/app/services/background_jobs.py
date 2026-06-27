from __future__ import annotations

import sqlite3
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock
from typing import Any

from app.db.database import get_connection
from app.models.schemas import SyncRequest
from app.services.akshare_service import AkshareService
from app.services.etf_service import EtfService
from app.services.factor_engine import FactorEngine
from app.services.data_quality_service import DataQualityService
from app.services.market_data_service import MarketDataService
from app.services.sentiment_service import SentimentService


JobTask = Callable[[sqlite3.Connection, int], dict[str, Any]]
SuccessMessage = Callable[[dict[str, Any]], str]

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stock-background-job")
_state_lock = Lock()
_writer_lock = Lock()
_active_future: Future[None] | None = None
_active_job: dict[str, Any] | None = None
_cancel_events: dict[int, Event] = {}


class JobCancelled(RuntimeError):
    """后台任务收到用户取消请求。

    Python线程不能安全强杀，所以所有长任务都通过这个异常做协作式停止。
    """


def _busy_response(job_type: str) -> dict[str, Any]:
    active = _active_job or {}
    return {
        "accepted": False,
        "job_id": active.get("job_id"),
        "job_type": active.get("job_type") or job_type,
        "status": "running",
        "message": "已有后台数据任务正在运行，本次请求已跳过；前台会继续使用现有缓存。",
    }


def _register_cancel_event(job_id: int) -> Event:
    event = Event()
    _cancel_events[job_id] = event
    return event


def _cancel_event(job_id: int) -> Event | None:
    return _cancel_events.get(job_id)


def _cancel_checker(conn: sqlite3.Connection, job_id: int) -> Callable[[], None]:
    def check() -> None:
        event = _cancel_event(job_id)
        if event and event.is_set():
            raise JobCancelled("任务已按用户请求取消，已保留取消前成功写入的缓存。")

    return check


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
        WHERE status IN ('queued', 'running', 'cancel_requested') AND finished_at IS NULL
        """
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def _clear_active(job_id: int) -> None:
    global _active_job
    with _state_lock:
        if _active_job and _active_job.get("job_id") == job_id:
            _active_job = None
        _cancel_events.pop(job_id, None)


def get_active_job() -> dict[str, Any] | None:
    with _state_lock:
        return dict(_active_job) if _active_job else None


def request_cancel_job(job_id: int) -> dict[str, Any]:
    with _state_lock:
        event = _cancel_events.get(job_id)
        active = dict(_active_job) if _active_job else {}
        if event and int(active.get("job_id") or 0) == job_id:
            event.set()
            job_type = str(active.get("job_type") or "")
            conn: sqlite3.Connection | None = None
            try:
                conn = get_connection()
                conn.execute("PRAGMA busy_timeout=300")
                _update_job(conn, job_id, "cancel_requested", "已收到取消请求，后台会在当前数据批次结束后停止。")
            except sqlite3.OperationalError:
                # 数据库正被长写事务占用时，也要先让取消按钮即时生效；任务线程会稍后写入cancelled状态。
                pass
            finally:
                if conn:
                    conn.close()
            return {
                "accepted": True,
                "job_id": job_id,
                "job_type": job_type,
                "status": "cancel_requested",
                "message": "已请求取消后台任务。",
            }

    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        row = conn.execute("SELECT * FROM sync_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return {"accepted": False, "job_id": job_id, "job_type": "", "status": "not_found", "message": "任务不存在。"}
        status = str(row["status"])
        job_type = str(row["job_type"])
        if status not in {"queued", "running", "cancel_requested"}:
            return {
                "accepted": False,
                "job_id": job_id,
                "job_type": job_type,
                "status": status,
                "message": f"任务当前状态为 {status}，无需取消。",
            }
        _update_job(conn, job_id, "cancelled", "任务不在当前进程运行，已标记为取消。", finished=True)
        return {
            "accepted": True,
            "job_id": job_id,
            "job_type": job_type,
            "status": "cancelled",
            "message": "任务不在当前进程运行，已标记为取消。",
        }
    finally:
        if conn:
            conn.close()


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
        _cancel_checker(conn, job_id)()
        result = task(conn, job_id)
        if (_cancel_event(job_id) and _cancel_event(job_id).is_set()):
            _update_job(conn, job_id, "cancelled", "任务已取消，已保留取消前成功写入的缓存。", finished=True)
        else:
            _update_job(conn, job_id, "success", success_message(result), finished=True)
    except JobCancelled as exc:
        if conn:
            conn.rollback()
            _update_job(conn, job_id, "cancelled", str(exc), finished=True)
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
            _register_cancel_event(job_id)
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
    global _active_job
    if not _writer_lock.acquire(blocking=False):
        return _busy_response(job_type)
    conn: sqlite3.Connection | None = None
    job_id: int | None = None
    try:
        conn = get_connection()
        job_id = _insert_job(conn, job_type, "running", running_message)
        with _state_lock:
            _active_job = {"job_id": job_id, "job_type": job_type}  # type: ignore[assignment]
            _register_cancel_event(job_id)
        _cancel_checker(conn, job_id)()
        result = task(conn, job_id)
        message = success_message(result)
        if (_cancel_event(job_id) and _cancel_event(job_id).is_set()):
            message = "任务已取消，已保留取消前成功写入的缓存。"
            _update_job(conn, job_id, "cancelled", message, finished=True)
            return {"accepted": True, "job_id": job_id, "job_type": job_type, "status": "cancelled", "message": message}
        _update_job(conn, job_id, "success", message, finished=True)
        return {"accepted": True, "job_id": job_id, "job_type": job_type, "status": "success", "message": message}
    except JobCancelled as exc:
        if conn:
            conn.rollback()
            if job_id:
                _update_job(conn, job_id, "cancelled", str(exc), finished=True)
        return {"accepted": True, "job_id": job_id, "job_type": job_type, "status": "cancelled", "message": str(exc)}
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
        if job_id:
            _clear_active(job_id)


def _sync_task(payload: SyncRequest) -> JobTask:
    def task(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
        check_cancel = _cancel_checker(conn, job_id)
        sync_result = MarketDataService(conn).sync(payload, cancel_check=check_cancel)
        check_cancel()
        quality_result = DataQualityService(conn).clean_mixed_demo_rows()
        check_cancel()
        sentiment_count = SentimentService(conn).batch_refresh_existing(limit=300, cancel_check=check_cancel)
        check_cancel()
        factor_rows = FactorEngine(conn).calculate_all(force=True, cancel_check=check_cancel)
        return {"sync": sync_result, "quality": quality_result, "sentiment_count": sentiment_count, "factor_count": len(factor_rows)}

    return task


def _factor_task(force: bool) -> JobTask:
    def task(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
        rows = FactorEngine(conn).calculate_all(force=force, cancel_check=_cancel_checker(conn, job_id))
        return {"factor_count": len(rows)}

    return task


def _stock_history_task(ts_code: str) -> JobTask:
    def task(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
        check_cancel = _cancel_checker(conn, job_id)
        check_cancel()
        sync_result = AkshareService(conn).sync_stock_history(ts_code)
        check_cancel()
        quality_result = DataQualityService(conn).clean_mixed_demo_rows()
        check_cancel()
        factor_rows = FactorEngine(conn).calculate_all(force=True, cancel_check=check_cancel)
        return {"sync": sync_result, "quality": quality_result, "factor_count": len(factor_rows)}

    return task


def _all_stock_history_task() -> JobTask:
    def task(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
        check_cancel = _cancel_checker(conn, job_id)

        def progress(done: int, total: int, ts_code: str, rows: int, skipped: int) -> None:
            check_cancel()
            percent = round(done / max(total, 1) * 100, 1)
            _update_job(
                conn,
                job_id,
                "running",
                f"正在全市场补齐历史K线：{done}/{total}（{percent}%），当前 {ts_code}，已写入 {rows} 条，跳过 {skipped} 只。",
            )

        sync_result = AkshareService(conn).sync_all_stock_history(progress=progress, cancel_check=check_cancel)
        check_cancel()
        quality_result = DataQualityService(conn).clean_mixed_demo_rows()
        check_cancel()
        factor_rows = FactorEngine(conn).calculate_all(force=True, cancel_check=check_cancel)
        return {"sync": sync_result, "quality": quality_result, "factor_count": len(factor_rows)}

    return task


def _etf_sync_task(history_limit: int) -> JobTask:
    def task(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
        cancel_check = _cancel_checker(conn, job_id)

        def progress(done: int, total: int, etf_code: str, rows: int) -> None:
            percent = round(done / max(total, 1) * 100, 1)
            _update_job(
                conn,
                job_id,
                "running",
                f"正在同步ETF历史行情：{done}/{total}（{percent}%），当前 {etf_code}，已写入 {rows} 条K线。",
            )

        return EtfService(conn).sync(history_limit=history_limit, progress=progress, cancel_check=cancel_check)

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


def submit_all_stock_history_job() -> dict[str, Any]:
    return submit_exclusive_db_job(
        "all_stock_history_sync",
        "全市场历史K线补齐已进入后台队列，选股会继续读取上一版因子缓存。",
        "正在全市场补齐历史K线，完成后会自动重算因子缓存。",
        _all_stock_history_task(),
        lambda result: (
            "全市场历史K线补齐完成："
            f"拉取 {result.get('sync', {}).get('fetched_symbols', 0)} 只，"
            f"跳过 {result.get('sync', {}).get('skipped_symbols', 0)} 只，"
            f"失败 {result.get('sync', {}).get('failed_symbols', 0)} 只，"
            f"写入/覆盖 {result.get('sync', {}).get('rows', 0)} 条K线，"
            f"因子缓存覆盖 {result.get('factor_count', 0)} 只股票。"
        ),
    )


def submit_etf_sync_job(history_limit: int = 0) -> dict[str, Any]:
    return submit_exclusive_db_job(
        "etf_sync",
        "ETF行情与历史K线同步已进入后台队列。",
        "正在后台同步ETF行情、净值类型和历史K线。",
        _etf_sync_task(history_limit),
        lambda result: (
            "ETF同步完成："
            f"实时行情 {result.get('spot_count', 0)} 只，"
            f"历史覆盖 {result.get('history_symbols', 0)} 只，"
            f"写入/覆盖 {result.get('rows', 0)} 条K线。"
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
