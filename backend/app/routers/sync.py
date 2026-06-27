from typing import Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import SyncRequest
from app.services.factor_engine import FactorEngine
from app.services.market_data_service import MarketDataService
from app.services.sentiment_service import SentimentService

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/run", response_model=ApiResponse[dict[str, Any]])
def run_sync(payload: SyncRequest, conn=Depends(get_db)) -> ApiResponse[dict[str, Any]]:
    result = MarketDataService(conn).sync(payload)
    SentimentService(conn).batch_refresh_existing(limit=300)
    FactorEngine(conn).calculate_all(force=True)
    return ok(result, "数据同步与因子刷新完成")


@router.get("/jobs", response_model=ApiResponse[list[dict[str, Any]]])
def jobs(conn=Depends(get_db)) -> ApiResponse[list[dict[str, Any]]]:
    rows = conn.execute("SELECT * FROM sync_jobs ORDER BY started_at DESC LIMIT 50").fetchall()
    return ok([dict(row) for row in rows])
