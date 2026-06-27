from __future__ import annotations

import sqlite3
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

    def sync(self, request: SyncRequest) -> dict[str, Any]:
        provider = request.provider or self.settings.market_data.provider
        provider = provider.lower()

        if self.settings.market_data.clear_factor_cache_on_sync:
            self.conn.execute("DELETE FROM computed_factors")

        if provider == "akshare":
            return AkshareService(self.conn).sync(request)
        if provider == "tushare":
            return TushareService(self.conn).sync(request)
        if provider == "demo":
            return self._demo()
        if provider == "auto":
            return self._auto(request)
        raise ValueError("未知数据源，请使用 auto/akshare/tushare/demo")

    def _auto(self, request: SyncRequest) -> dict[str, Any]:
        attempts: list[dict[str, str]] = []
        if self.settings.akshare.enabled:
            try:
                result = AkshareService(self.conn).sync(request)
                result["requested_provider"] = "auto"
                return result
            except Exception as exc:
                attempts.append({"provider": "akshare", "error": str(exc)})

        if self.settings.tushare.enabled and self.settings.tushare.token:
            try:
                result = TushareService(self.conn).sync(request)
                result["requested_provider"] = "auto"
                if attempts:
                    result["fallback_attempts"] = attempts
                return result
            except Exception as exc:
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
