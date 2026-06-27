from typing import Any

from fastapi import APIRouter

from app.core.config import load_settings, update_settings
from app.core.response import ApiResponse, ok

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ApiResponse[dict[str, Any]])
def get_config() -> ApiResponse[dict[str, Any]]:
    return ok(load_settings().__dict__)


@router.put("", response_model=ApiResponse[dict[str, Any]])
def put_config(payload: dict[str, Any]) -> ApiResponse[dict[str, Any]]:
    settings = update_settings(payload)
    return ok(settings.__dict__, "配置已保存，重启后调度器配置完全生效")
