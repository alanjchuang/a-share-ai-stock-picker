from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import StrategyCreate, StrategyOut, StrategyUpdate
from app.services.strategy_service import StrategyService

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=ApiResponse[list[StrategyOut]])
def list_strategies(conn=Depends(get_db)) -> ApiResponse[list[StrategyOut]]:
    return ok(StrategyService(conn).list())


@router.post("", response_model=ApiResponse[StrategyOut])
def create_strategy(payload: StrategyCreate, conn=Depends(get_db)) -> ApiResponse[StrategyOut]:
    return ok(StrategyService(conn).create(payload), "策略已保存")


@router.put("/{strategy_id}", response_model=ApiResponse[StrategyOut])
def update_strategy(strategy_id: int, payload: StrategyUpdate, conn=Depends(get_db)) -> ApiResponse[StrategyOut]:
    return ok(StrategyService(conn).update(strategy_id, payload), "策略已更新")


@router.delete("/{strategy_id}", response_model=ApiResponse[dict[str, int]])
def delete_strategy(strategy_id: int, conn=Depends(get_db)) -> ApiResponse[dict[str, int]]:
    return ok(StrategyService(conn).delete(strategy_id), "策略已删除")
