from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import StockDetail
from app.services.stock_service import StockService

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/{ts_code}", response_model=ApiResponse[StockDetail])
def detail(ts_code: str, conn=Depends(get_db)) -> ApiResponse[StockDetail]:
    return ok(StockService(conn).detail(ts_code))
