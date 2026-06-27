from typing import Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.services.data_repository import DataRepository

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/indices", response_model=ApiResponse[list[dict[str, Any]]])
def indices(conn=Depends(get_db)) -> ApiResponse[list[dict[str, Any]]]:
    return ok(DataRepository(conn).list_indices())


@router.get("/stocks", response_model=ApiResponse[list[dict[str, Any]]])
def stocks(conn=Depends(get_db)) -> ApiResponse[list[dict[str, Any]]]:
    return ok(DataRepository(conn).list_stocks())
