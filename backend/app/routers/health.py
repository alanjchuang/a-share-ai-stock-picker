from fastapi import APIRouter

from app.core.response import ApiResponse, ok

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=ApiResponse[dict[str, str]])
def health() -> ApiResponse[dict[str, str]]:
    return ok({"status": "ok"})
