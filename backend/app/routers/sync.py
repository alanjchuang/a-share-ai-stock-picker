from typing import Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import SyncRequest
from app.services.background_jobs import get_active_job, request_cancel_job, submit_all_stock_history_job, submit_sync_refresh_job

router = APIRouter(prefix="/api/sync", tags=["sync"])


def _reconcile_orphaned_jobs(conn) -> dict[str, Any] | None:
    active = get_active_job()
    active_job_id = int(active.get("job_id") or 0) if active else 0
    if active_job_id:
        conn.execute(
            """
            UPDATE sync_jobs
            SET status='failed',
                message=message || '（任务不在当前进程运行，已自动标记为中断。）',
                finished_at=CURRENT_TIMESTAMP
            WHERE status IN ('queued', 'running', 'cancel_requested')
              AND finished_at IS NULL
              AND id != ?
            """,
            (active_job_id,),
        )
    else:
        conn.execute(
            """
            UPDATE sync_jobs
            SET status='failed',
                message=message || '（任务不在当前进程运行，已自动标记为中断。）',
                finished_at=CURRENT_TIMESTAMP
            WHERE status IN ('queued', 'running', 'cancel_requested')
              AND finished_at IS NULL
            """
        )
    conn.commit()
    return active


@router.post("/run", response_model=ApiResponse[dict[str, Any]])
def run_sync(payload: SyncRequest) -> ApiResponse[dict[str, Any]]:
    job = submit_sync_refresh_job(payload)
    message = job["message"] if not job["accepted"] else "数据同步与因子刷新已在后台启动"
    return ok(job, message)


@router.post("/history/all", response_model=ApiResponse[dict[str, Any]])
def run_all_history_sync() -> ApiResponse[dict[str, Any]]:
    job = submit_all_stock_history_job()
    message = job["message"] if not job["accepted"] else "全市场历史K线补齐已在后台启动"
    return ok(job, message)


@router.get("/jobs", response_model=ApiResponse[list[dict[str, Any]]])
def jobs(conn=Depends(get_db)) -> ApiResponse[list[dict[str, Any]]]:
    _reconcile_orphaned_jobs(conn)
    rows = conn.execute("SELECT * FROM sync_jobs ORDER BY started_at DESC LIMIT 50").fetchall()
    return ok([dict(row) for row in rows])


@router.get("/jobs/active", response_model=ApiResponse[dict[str, Any] | None])
def active_job(conn=Depends(get_db)) -> ApiResponse[dict[str, Any] | None]:
    active = _reconcile_orphaned_jobs(conn)
    if not active:
        return ok(None)
    row = conn.execute("SELECT * FROM sync_jobs WHERE id = ?", (active.get("job_id"),)).fetchone()
    return ok(dict(row) if row else active)


@router.get("/jobs/{job_id}", response_model=ApiResponse[dict[str, Any]])
def job_detail(job_id: int, conn=Depends(get_db)) -> ApiResponse[dict[str, Any]]:
    row = conn.execute("SELECT * FROM sync_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise ValueError("后台任务不存在")
    return ok(dict(row))


@router.post("/jobs/{job_id}/cancel", response_model=ApiResponse[dict[str, Any]])
def cancel_job(job_id: int) -> ApiResponse[dict[str, Any]]:
    result = request_cancel_job(job_id)
    return ok(result, result["message"])
