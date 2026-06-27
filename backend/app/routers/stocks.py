from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import StockDetail, StockMarketResponse
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
