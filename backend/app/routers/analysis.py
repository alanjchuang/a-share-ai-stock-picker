from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import DecisionDashboardResponse, PatternRadarResponse, StrategyDefinition, StrategyScanResponse
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/dashboard", response_model=ApiResponse[DecisionDashboardResponse])
def dashboard(limit: int = 8, conn=Depends(get_db)) -> ApiResponse[DecisionDashboardResponse]:
    return ok(AnalysisService(conn).dashboard(limit=limit))


@router.get("/strategies", response_model=ApiResponse[list[StrategyDefinition]])
def strategies(conn=Depends(get_db)) -> ApiResponse[list[StrategyDefinition]]:
    return ok(AnalysisService(conn).strategy_definitions())


@router.get("/strategies/{strategy_key}", response_model=ApiResponse[StrategyScanResponse])
def scan_strategy(
    strategy_key: str,
    limit: int = 80,
    holding_days: int = 10,
    conn=Depends(get_db),
) -> ApiResponse[StrategyScanResponse]:
    return ok(AnalysisService(conn).scan_strategy(strategy_key=strategy_key, limit=limit, holding_days=holding_days))


@router.get("/patterns", response_model=ApiResponse[PatternRadarResponse])
def patterns(
    limit: int = 120,
    signal: str | None = None,
    conn=Depends(get_db),
) -> ApiResponse[PatternRadarResponse]:
    return ok(AnalysisService(conn).pattern_radar(limit=limit, signal=signal))
