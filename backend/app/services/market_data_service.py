from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

from app.core.config import load_settings
from app.db.seed import ensure_demo_data
from app.models.schemas import SyncRequest
from app.services.akshare_service import AkshareService
from app.services.tushare_service import TushareService


class MarketDataService:
    """统一行情财务数据源入口：AKShare/Tushare/Demo按配置路由。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.settings = load_settings()

    def sync(self, request: SyncRequest, cancel_check: Callable[[], None] | None = None) -> dict[str, Any]:
        provider = request.provider or self.settings.market_data.provider
        provider = provider.lower()
        if cancel_check:
            cancel_check()

        # 同步行情时保留旧因子缓存，前台查询就能继续读取上一版结果；
        # 后台任务会在同步结束后用INSERT OR REPLACE覆盖新因子，避免同步期间出现空缓存或长时间锁表。
        if provider == "akshare":
            result = AkshareService(self.conn).sync(request, cancel_check=cancel_check)
            result["factor_cache_preserved_during_sync"] = True
            return result
        if provider == "tushare":
            result = TushareService(self.conn).sync(request, cancel_check=cancel_check)
            result["factor_cache_preserved_during_sync"] = True
            return result
        if provider == "demo":
            return self._demo()
        if provider == "auto":
            result = self._auto(request, cancel_check=cancel_check)
            result["factor_cache_preserved_during_sync"] = True
            return result
        raise ValueError("未知数据源，请使用 auto/akshare/tushare/demo")

    def _auto(self, request: SyncRequest, cancel_check: Callable[[], None] | None = None) -> dict[str, Any]:
        attempts: list[dict[str, str]] = []
        if self.settings.akshare.enabled:
            try:
                if cancel_check:
                    cancel_check()
                result = AkshareService(self.conn).sync(request, cancel_check=cancel_check)
                result["requested_provider"] = "auto"
                return result
            except Exception as exc:
                if exc.__class__.__name__ == "JobCancelled":
                    raise
                attempts.append({"provider": "akshare", "error": str(exc)})

        if self.settings.tushare.enabled and self.settings.tushare.token:
            try:
                if cancel_check:
                    cancel_check()
                result = TushareService(self.conn).sync(request, cancel_check=cancel_check)
                result["requested_provider"] = "auto"
                if attempts:
                    result["fallback_attempts"] = attempts
                return result
            except Exception as exc:
                if exc.__class__.__name__ == "JobCancelled":
                    raise
                attempts.append({"provider": "tushare", "error": str(exc)})

        if self.settings.market_data.fallback_to_demo:
            result = self._demo()
            result["requested_provider"] = "auto"
            result["fallback_attempts"] = attempts
            return result
        raise RuntimeError(f"auto数据源同步失败：{attempts}")

    def _demo(self) -> dict[str, Any]:
        ensure_demo_data(self.conn)
        self.conn.commit()
        return {"mode": "demo", "message": "已使用本地演示数据", "tables": {}}
