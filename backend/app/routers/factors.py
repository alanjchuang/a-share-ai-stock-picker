from typing import Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.services.factor_engine import FactorEngine

router = APIRouter(prefix="/api/factors", tags=["factors"])


@router.post("/calculate", response_model=ApiResponse[dict[str, Any]])
def calculate(conn=Depends(get_db)) -> ApiResponse[dict[str, Any]]:
    rows = FactorEngine(conn).calculate_all(force=True)
    return ok({"count": len(rows)}, "因子批量计算完成")
