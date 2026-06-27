from typing import Any

from fastapi import APIRouter

from app.core.response import ApiResponse, ok
from app.services.background_jobs import submit_factor_refresh_job

router = APIRouter(prefix="/api/factors", tags=["factors"])


@router.post("/calculate", response_model=ApiResponse[dict[str, Any]])
def calculate() -> ApiResponse[dict[str, Any]]:
    job = submit_factor_refresh_job(force=True)
    message = job["message"] if not job["accepted"] else "因子刷新已在后台启动"
    return ok(job, message)
