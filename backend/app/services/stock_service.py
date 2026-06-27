from __future__ import annotations

import sqlite3
from typing import Any

from app.models.schemas import KLinePoint, StockDetail, StockMarketItem, StockMarketResponse, StockNewsItem
from app.core.config import load_settings
from app.services.data_repository import DataRepository
from app.services.factor_engine import FactorEngine
from app.services.screener_service import ScreenerService
from app.utils.indicators import add_technical_indicators


class StockService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = DataRepository(conn)
        self.factor_engine = FactorEngine(conn)

    def list_market(
        self,
        q: str = "",
        industry: str | None = None,
        rating: str | None = None,
        include_st: bool = False,
        include_paused: bool = False,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "ai_score",
        sort_order: str = "desc",
    ) -> StockMarketResponse:
        """读取本地因子缓存形成全市场行情表，不触发同步写库，避免浏览页面造成锁竞争。"""

        rows = self.factor_engine.factor_rows()
        industries = sorted({str(row.get("industry") or "未分类") for row in rows})
        keyword = q.strip().lower()
        filtered = [
            row
            for row in rows
            if self._market_row_matches(
                row,
                keyword=keyword,
                industry=industry,
                rating=rating,
                include_st=include_st,
                include_paused=include_paused,
            )
        ]

        sort_field = sort_by if sort_by in self._sortable_fields() else "ai_score"
        reverse = sort_order.lower() != "asc"
        filtered.sort(key=lambda row: self._sort_value(row, sort_field), reverse=reverse)

        safe_page_size = min(max(int(page_size or 50), 10), 200)
        safe_page = max(int(page or 1), 1)
        start = (safe_page - 1) * safe_page_size
        page_rows = filtered[start : start + safe_page_size]
        return StockMarketResponse(
            total=len(filtered),
            page=safe_page,
            page_size=safe_page_size,
            rows=[self._to_market_item(row) for row in page_rows],
            latest_trade_date=self.repo.latest_trade_date(),
            industries=industries,
            factor_universe_count=len(rows),
        )

    def detail(self, ts_code: str) -> StockDetail:
        rows = self.factor_engine.factor_rows()
        row = next((item for item in rows if item["ts_code"] == ts_code), None)
        if not row:
            raise ValueError("股票不存在或尚未计算因子")
        base = ScreenerService._to_stock_score(row)

        daily, data_warnings = self.repo.stock_daily_quality(ts_code, limit=120)
        tech = add_technical_indicators(daily)
        kline = [
            KLinePoint(
                trade_date=str(item["trade_date"]),
                open=float(item["open"]),
                close=float(item["close"]),
                low=float(item["low"]),
                high=float(item["high"]),
                volume=float(item["vol"]),
                ma5=self._optional_float(item.get("ma5")),
                ma10=self._optional_float(item.get("ma10")),
                ma20=self._optional_float(item.get("ma20")),
                ma60=self._optional_float(item.get("ma60")),
            )
            for item in tech.to_dict(orient="records")
        ]

        news_rows = self.repo.recent_news(ts_code, 30)
        news = [
            StockNewsItem(
                id=int(item["id"]),
                title=item["title"],
                content=item["content"],
                source=item.get("source"),
                publish_time=item["publish_time"],
                sentiment_score=float(item.get("sentiment_score") or 50),
                sentiment_label=item.get("sentiment_label") or "中性",
                keywords=[keyword for keyword in str(item.get("keywords") or "").split(",") if keyword],
            )
            for item in news_rows
        ]
        radar = {
            "价值": base.fundamental_score,
            "成长": float(row.get("revenue_yoy") or 0),
            "资金": base.capital_score,
            "舆情": base.sentiment_factor_score,
        }
        settings = load_settings()
        source = f"本地SQLite缓存 / {settings.market_data.provider}"
        if settings.market_data.fallback_to_demo:
            source += " / 允许DEMO兜底"
        if not kline:
            data_warnings.append("当前个股缺少可用K线，请在数据中心触发真实行情同步。")
        elif len(kline) < 30:
            data_warnings.append(f"当前仅有 {len(kline)} 条可信K线，部分均线和回测信号会偏弱；请在数据中心同步更多历史行情。")
        return StockDetail(base=base, kline=kline, news=news, radar=radar, rating=base.rating, data_source=source, data_warnings=data_warnings)

    @staticmethod
    def _market_row_matches(
        row: dict[str, Any],
        keyword: str,
        industry: str | None,
        rating: str | None,
        include_st: bool,
        include_paused: bool,
    ) -> bool:
        if keyword:
            haystack = " ".join(
                [
                    str(row.get("ts_code") or ""),
                    str(row.get("symbol") or ""),
                    str(row.get("name") or ""),
                    str(row.get("industry") or ""),
                ]
            ).lower()
            if keyword not in haystack:
                return False
        if industry and industry != "全部" and str(row.get("industry") or "未分类") != industry:
            return False
        if rating and rating != "全部" and str(row.get("rating") or "") != rating:
            return False
        if not include_st and int(row.get("is_st") or 0):
            return False
        if not include_paused and int(row.get("is_paused") or 0):
            return False
        return True

    @staticmethod
    def _sortable_fields() -> set[str]:
        return {
            "ai_score",
            "pct_chg",
            "pct_chg_20",
            "pct_chg_60",
            "close",
            "turnover_rate",
            "volume_ratio",
            "pe_ttm",
            "pb",
            "roe",
            "total_mv",
            "circ_mv",
            "main_net_inflow_sum",
            "sentiment_score",
        }

    @classmethod
    def _sort_value(cls, row: dict[str, Any], field: str) -> float:
        value = row.get(field)
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _to_market_item(cls, row: dict[str, Any]) -> StockMarketItem:
        base = ScreenerService._to_stock_score(row)
        return StockMarketItem(
            **base.model_dump(),
            trade_date=str(row.get("trade_date") or "") or None,
            total_mv=cls._optional_float(row.get("total_mv")),
            turnover_rate=cls._optional_float(row.get("turnover_rate")),
            volume_ratio=cls._optional_float(row.get("volume_ratio")),
            pct_chg_20=cls._optional_float(row.get("pct_chg_20")),
            pct_chg_60=cls._optional_float(row.get("pct_chg_60")),
            is_st=bool(row.get("is_st")),
            is_paused=bool(row.get("is_paused")),
        )

    @staticmethod
    def _optional_float(value: object) -> float | None:
        try:
            return None if value is None else round(float(value), 2)
        except (TypeError, ValueError):
            return None
