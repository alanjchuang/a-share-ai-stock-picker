from __future__ import annotations

import sqlite3

from app.models.schemas import KLinePoint, StockDetail, StockNewsItem
from app.services.data_repository import DataRepository
from app.services.factor_engine import FactorEngine
from app.services.screener_service import ScreenerService
from app.utils.indicators import add_technical_indicators


class StockService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = DataRepository(conn)
        self.factor_engine = FactorEngine(conn)

    def detail(self, ts_code: str) -> StockDetail:
        rows = self.factor_engine.factor_rows()
        row = next((item for item in rows if item["ts_code"] == ts_code), None)
        if not row:
            raise ValueError("股票不存在或尚未计算因子")
        base = ScreenerService._to_stock_score(row)

        daily = self.repo.stock_daily_frame(ts_code, limit=120)
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
        return StockDetail(base=base, kline=kline, news=news, radar=radar, rating=base.rating)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        try:
            return None if value is None else round(float(value), 2)
        except (TypeError, ValueError):
            return None
