from typing import Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import SyncRequest
from app.services.background_jobs import get_active_job, request_cancel_job, submit_all_stock_history_job, submit_sync_refresh_job

router = APIRouter(prefix="/api/sync", tags=["sync"])


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
    rows = conn.execute("SELECT * FROM sync_jobs ORDER BY started_at DESC LIMIT 50").fetchall()
    return ok([dict(row) for row in rows])


@router.get("/jobs/active", response_model=ApiResponse[dict[str, Any] | None])
def active_job(conn=Depends(get_db)) -> ApiResponse[dict[str, Any] | None]:
    active = get_active_job()
    if not active:
        return ok(None)
    row = conn.execute("SELECT * FROM sync_jobs WHERE id = ?", (active.get("job_id"),)).fetchone()
    return ok(dict(row) if row else active)


@router.post("/jobs/{job_id}/cancel", response_model=ApiResponse[dict[str, Any]])
def cancel_job(job_id: int) -> ApiResponse[dict[str, Any]]:
    result = request_cancel_job(job_id)
    return ok(result, result["message"])
