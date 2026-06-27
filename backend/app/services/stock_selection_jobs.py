from __future__ import annotations

import json
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

from app.db.database import get_connection
from app.models.schemas import StockSelectionWorkflowResult, WorkflowRunRequest
from app.services.stock_selection_workflow import StockSelectionWorkflow


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stock-selection-workflow")
_state_lock = Lock()
_active_future: Future[None] | None = None
_active_job_id: int | None = None
_STALE_JOB_MINUTES = 30
_STALE_JOB_MESSAGE = "AI解析选股任务已中断或服务重启，请重新发起。"


def submit_stock_selection_workflow_job(payload: WorkflowRunRequest) -> dict[str, Any]:
    """提交AI选股Workflow后台任务。

    LLM、火山搜索和候选股复核都可能耗时较久；这里使用独立后台线程运行，
    避免前台请求触发全屏loading后阻塞用户继续操作页面。
    """

    global _active_future, _active_job_id
    with _state_lock:
        if _active_future and not _active_future.done() and _active_job_id:
            return {
                "accepted": False,
                "job_id": _active_job_id,
                "job_type": "stock_selection_workflow",
                "status": "running",
                "message": "已有AI解析选股任务正在后台运行，请稍后查看结果。",
            }

        conn: sqlite3.Connection | None = None
        try:
            conn = get_connection()
            _ensure_table(conn)
            _expire_stale_jobs(conn)
            blocked = _readiness_block(conn, payload)
            if blocked:
                return blocked
            job_id = _insert_job(conn, payload)
        finally:
            if conn:
                conn.close()

        _active_job_id = job_id
        _active_future = _executor.submit(_run_job, job_id, payload)
        return {
            "accepted": True,
            "job_id": job_id,
            "job_type": "stock_selection_workflow",
            "status": "queued",
            "message": "AI解析选股已进入后台任务，完成后会自动加载筛选结果。",
        }


def get_stock_selection_workflow_job(job_id: int) -> dict[str, Any] | None:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        _ensure_table(conn)
        _expire_stale_jobs(conn)
        row = conn.execute("SELECT * FROM stock_selection_workflow_jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_out(dict(row)) if row else None
    finally:
        if conn:
            conn.close()


def list_stock_selection_workflow_jobs(limit: int = 20) -> list[dict[str, Any]]:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        _ensure_table(conn)
        _expire_stale_jobs(conn)
        safe_limit = min(max(int(limit or 20), 1), 100)
        rows = conn.execute(
            """
            SELECT *
            FROM stock_selection_workflow_jobs
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return [_job_out(dict(row)) for row in rows]
    finally:
        if conn:
            conn.close()


def _run_job(job_id: int, payload: WorkflowRunRequest) -> None:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        _ensure_table(conn)
        _update_job(conn, job_id, "running", "正在后台调用Workflow解析条件、执行筛选并复核候选股。")
        result = StockSelectionWorkflow(conn).run(payload)
        _update_job(
            conn,
            job_id,
            "success",
            f"AI解析选股完成，命中 {result.screening_result.total if result.screening_result else 0} 只股票。",
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
        CREATE TABLE IF NOT EXISTS stock_selection_workflow_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL DEFAULT 'stock_selection_workflow',
            status TEXT NOT NULL,
            message TEXT DEFAULT '',
            request_json TEXT DEFAULT '',
            result_json TEXT DEFAULT '',
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_stock_selection_workflow_jobs_status_started "
        "ON stock_selection_workflow_jobs(status, started_at)"
    )
    conn.commit()


def _readiness_block(conn: sqlite3.Connection, payload: WorkflowRunRequest) -> dict[str, Any] | None:
    try:
        workflow = StockSelectionWorkflow(conn)
        if not workflow.settings.workflow.enabled:
            raise RuntimeError("Workflow 未启用，请在系统配置启用 Workflow")
        workflow_path = payload.workflow_path or workflow.settings.workflow.default_path or workflow._default_workflow_path()
        workflow._validate_ready(workflow._load_workflow_config(workflow_path))
        return None
    except Exception as exc:
        return {
            "accepted": False,
            "job_id": None,
            "job_type": "stock_selection_workflow",
            "status": "blocked",
            "message": "AI解析选股需要先完成配置：" + str(exc).replace("AI解析选股需要先完成配置：", ""),
        }


def _expire_stale_jobs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE stock_selection_workflow_jobs
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


def _insert_job(conn: sqlite3.Connection, payload: WorkflowRunRequest) -> int:
    cursor = conn.execute(
        """
        INSERT INTO stock_selection_workflow_jobs(job_type, status, message, request_json)
        VALUES ('stock_selection_workflow', 'queued', ?, ?)
        """,
        ("AI解析选股已进入后台任务，完成后会自动加载筛选结果。", payload.model_dump_json()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _update_job(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    message: str,
    *,
    result: StockSelectionWorkflowResult | None = None,
    finished: bool = False,
) -> None:
    result_json = result.model_dump_json() if result else None
    if finished:
        if result_json is None:
            conn.execute(
                "UPDATE stock_selection_workflow_jobs SET status=?, message=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, message, job_id),
            )
        else:
            conn.execute(
                """
                UPDATE stock_selection_workflow_jobs
                SET status=?, message=?, result_json=?, finished_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (status, message, result_json, job_id),
            )
    else:
        conn.execute("UPDATE stock_selection_workflow_jobs SET status=?, message=? WHERE id=?", (status, message, job_id))
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
        "job_type": str(row.get("job_type") or "stock_selection_workflow"),
        "status": str(row["status"]),
        "message": str(row.get("message") or ""),
        "started_at": str(row.get("started_at") or ""),
        "finished_at": row.get("finished_at"),
        "result": result,
    }
