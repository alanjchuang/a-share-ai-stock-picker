from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import EtfDetail, EtfMarketResponse
from app.services.background_jobs import submit_etf_sync_job
from app.services.etf_service import EtfService

router = APIRouter(prefix="/api/etfs", tags=["etfs"])


@router.post("/sync", response_model=ApiResponse[dict])
def sync_etfs(history_limit: int = 0) -> ApiResponse[dict]:
    job = submit_etf_sync_job(history_limit=history_limit)
    message = job["message"] if not job["accepted"] else "ETF数据同步已在后台启动"
    return ok(job, message)


@router.get("", response_model=ApiResponse[EtfMarketResponse])
def list_etfs(
    q: str = "",
    category: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "amount",
    sort_order: str = "desc",
    conn=Depends(get_db),
) -> ApiResponse[EtfMarketResponse]:
    return ok(
        EtfService(conn).list_market(
            q=q,
            category=category,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    )


@router.get("/{etf_code}", response_model=ApiResponse[EtfDetail])
def detail(etf_code: str, conn=Depends(get_db)) -> ApiResponse[EtfDetail]:
    return ok(EtfService(conn).detail(etf_code))
