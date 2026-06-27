from fastapi import APIRouter, Depends

from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import (
    WatchlistAskRequest,
    WatchlistAskResponse,
    WatchlistGroupCreate,
    WatchlistGroupOut,
    WatchlistGroupUpdate,
    WatchlistItemCreate,
    WatchlistItemOut,
    WatchlistItemUpdate,
    WatchlistNoteCreate,
    WatchlistNoteOut,
)
from app.services.watchlist_service import WatchlistService

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


@router.get("/groups", response_model=ApiResponse[list[WatchlistGroupOut]])
def list_groups(conn=Depends(get_db)) -> ApiResponse[list[WatchlistGroupOut]]:
    return ok(WatchlistService(conn).list_groups())


@router.post("/groups", response_model=ApiResponse[WatchlistGroupOut])
def create_group(payload: WatchlistGroupCreate, conn=Depends(get_db)) -> ApiResponse[WatchlistGroupOut]:
    return ok(WatchlistService(conn).create_group(payload), "自选分组已创建")


@router.put("/groups/{group_id}", response_model=ApiResponse[WatchlistGroupOut])
def update_group(group_id: int, payload: WatchlistGroupUpdate, conn=Depends(get_db)) -> ApiResponse[WatchlistGroupOut]:
    return ok(WatchlistService(conn).update_group(group_id, payload), "自选分组已更新")


@router.get("/items", response_model=ApiResponse[list[WatchlistItemOut]])
def list_items(group_id: int | None = None, status: str | None = None, conn=Depends(get_db)) -> ApiResponse[list[WatchlistItemOut]]:
    return ok(WatchlistService(conn).list_items(group_id=group_id, status=status))


@router.post("/items", response_model=ApiResponse[WatchlistItemOut])
def create_item(payload: WatchlistItemCreate, conn=Depends(get_db)) -> ApiResponse[WatchlistItemOut]:
    return ok(WatchlistService(conn).create_item(payload), "已加入自选股")


@router.put("/items/{item_id}", response_model=ApiResponse[WatchlistItemOut])
def update_item(item_id: int, payload: WatchlistItemUpdate, conn=Depends(get_db)) -> ApiResponse[WatchlistItemOut]:
    return ok(WatchlistService(conn).update_item(item_id, payload), "自选股已更新")


@router.delete("/items/{item_id}", response_model=ApiResponse[dict[str, int]])
def delete_item(item_id: int, conn=Depends(get_db)) -> ApiResponse[dict[str, int]]:
    return ok(WatchlistService(conn).delete_item(item_id), "自选股已移除")


@router.get("/notes", response_model=ApiResponse[list[WatchlistNoteOut]])
def list_notes(item_id: int | None = None, conn=Depends(get_db)) -> ApiResponse[list[WatchlistNoteOut]]:
    return ok(WatchlistService(conn).list_notes(item_id=item_id))


@router.post("/notes", response_model=ApiResponse[WatchlistNoteOut])
def create_note(payload: WatchlistNoteCreate, conn=Depends(get_db)) -> ApiResponse[WatchlistNoteOut]:
    return ok(WatchlistService(conn).create_note(payload), "复盘记录已保存")


@router.post("/ask", response_model=ApiResponse[WatchlistAskResponse])
def ask(payload: WatchlistAskRequest, conn=Depends(get_db)) -> ApiResponse[WatchlistAskResponse]:
    return ok(WatchlistService(conn).ask(payload), "自选股复盘完成")
