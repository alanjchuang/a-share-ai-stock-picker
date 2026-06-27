from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import StockDetail, StockLlmAnalysisResponse, StockMarketResponse
from app.services.background_jobs import submit_stock_history_job
from app.services.stock_service import StockService

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("", response_model=ApiResponse[StockMarketResponse])
def list_market(
    q: str = "",
    industry: str | None = None,
    rating: str | None = None,
    include_st: bool = False,
    include_paused: bool = False,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "ai_score",
    sort_order: str = "desc",
    conn=Depends(get_db),
) -> ApiResponse[StockMarketResponse]:
    return ok(
        StockService(conn).list_market(
            q=q,
            industry=industry,
            rating=rating,
            include_st=include_st,
            include_paused=include_paused,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    )


@router.get("/{ts_code}", response_model=ApiResponse[StockDetail])
def detail(ts_code: str, conn=Depends(get_db)) -> ApiResponse[StockDetail]:
    return ok(StockService(conn).detail(ts_code))


@router.post("/{ts_code}/llm-analysis", response_model=ApiResponse[StockLlmAnalysisResponse])
def llm_analysis(ts_code: str, conn=Depends(get_db)) -> ApiResponse[StockLlmAnalysisResponse]:
    return ok(StockService(conn).llm_analysis(ts_code), "个股LLM解析完成")


@router.post("/{ts_code}/history/sync", response_model=ApiResponse[dict])
def sync_stock_history(ts_code: str) -> ApiResponse[dict]:
    job = submit_stock_history_job(ts_code)
    message = job["message"] if not job["accepted"] else "历史K线补齐已在后台启动"
    return ok(job, message)
