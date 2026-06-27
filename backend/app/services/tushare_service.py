from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from typing import Any

import pandas as pd

from app.core.config import load_settings
from app.models.schemas import SyncRequest


INDEX_CODE_MAP = {
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "000016.SH": "上证50",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
    "899050.BJ": "北证50",
}


class TushareService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.settings = load_settings()

    def sync(self, request: SyncRequest) -> dict[str, Any]:
        if not self.settings.tushare.enabled or not self.settings.tushare.token:
            return {"mode": "demo", "message": "未配置Tushare token，已使用内置演示数据，可在系统配置中补充token后同步真实数据。"}

        try:
            import tushare as ts
        except ImportError as exc:
            raise RuntimeError("未安装tushare，请先安装backend/requirements.txt") from exc

        pro = ts.pro_api(self.settings.tushare.token)
        trade_date = request.trade_date or self.settings.tushare.default_trade_date or datetime.now().strftime("%Y%m%d")
        start_date = request.start_date or self.settings.tushare.default_start_date
        end_date = request.end_date or trade_date

        summary: dict[str, Any] = {"mode": "tushare", "trade_date": trade_date, "tables": {}}
        summary["tables"]["stocks"] = self._sync_stock_basic(pro)
        summary["tables"]["daily"] = self._sync_daily(pro, trade_date, start_date, end_date)
        if request.sync_fundamentals:
            summary["tables"]["fundamentals"] = self._sync_daily_basic(pro, trade_date)
        if request.sync_indices:
            summary["tables"]["indices"] = self._sync_indices(pro, start_date, end_date)
        if request.sync_news:
            summary["tables"]["news"] = self._sync_news(pro, start_date, end_date)
        self.conn.commit()
        return summary

    def _sleep(self) -> None:
        time.sleep(max(0, self.settings.tushare.request_interval_seconds))

    def _sync_stock_basic(self, pro: Any) -> int:
        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs",
        )
        count = 0
        for item in df.fillna("").to_dict(orient="records"):
            name = str(item["name"])
            self.conn.execute(
                """
                INSERT OR REPLACE INTO stocks
                (ts_code, symbol, name, area, industry, market, exchange, list_date, is_hs, is_st, is_paused, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT is_paused FROM stocks WHERE ts_code = ?), 0), CURRENT_TIMESTAMP)
                """,
                (
                    item["ts_code"],
                    item["symbol"],
                    item["name"],
                    item.get("area"),
                    item.get("industry"),
                    item.get("market"),
                    item.get("exchange"),
                    item.get("list_date"),
                    item.get("is_hs"),
                    1 if "ST" in name.upper() else 0,
                    item["ts_code"],
                ),
            )
            count += 1
        self._sleep()
        return count

    def _sync_daily(self, pro: Any, trade_date: str, start_date: str, end_date: str) -> int:
        try:
            df = pro.daily(trade_date=trade_date)
        except Exception:
            df = pro.daily(start_date=start_date, end_date=end_date)
        if df.empty:
            return 0
        count = 0
        for item in df.fillna(0).to_dict(orient="records"):
            self.conn.execute(
                """
                INSERT OR REPLACE INTO stock_daily
                (ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, turnover_rate, volume_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT turnover_rate FROM stock_daily WHERE ts_code=? AND trade_date=?), 0),
                        COALESCE((SELECT volume_ratio FROM stock_daily WHERE ts_code=? AND trade_date=?), 0))
                """,
                (
                    item["ts_code"],
                    item["trade_date"],
                    item.get("open"),
                    item.get("high"),
                    item.get("low"),
                    item.get("close"),
                    item.get("pre_close"),
                    item.get("change"),
                    item.get("pct_chg"),
                    item.get("vol"),
                    item.get("amount"),
                    item["ts_code"],
                    item["trade_date"],
                    item["ts_code"],
                    item["trade_date"],
                ),
            )
            count += 1
        self._sleep()
        return count

    def _sync_daily_basic(self, pro: Any, trade_date: str) -> int:
        df = pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,trade_date,turnover_rate,volume_ratio,pe_ttm,pb,total_mv,circ_mv,dv_ttm",
        )
        count = 0
        for item in df.fillna(0).to_dict(orient="records"):
            ts_code = item["ts_code"]
            self.conn.execute(
                """
                UPDATE stock_daily
                SET turnover_rate = ?, volume_ratio = ?
                WHERE ts_code = ? AND trade_date = ?
                """,
                (item.get("turnover_rate"), item.get("volume_ratio"), ts_code, item["trade_date"]),
            )
            existing = self.conn.execute(
                "SELECT * FROM fundamentals WHERE ts_code = ? AND trade_date = ?",
                (ts_code, item["trade_date"]),
            ).fetchone()
            old = dict(existing) if existing else {}
            self.conn.execute(
                """
                INSERT OR REPLACE INTO fundamentals
                (ts_code, trade_date, pe_ttm, pb, peg, roe, gross_margin, netprofit_margin, revenue_yoy,
                 deduct_profit_yoy, debt_to_assets, ocf, dividend_yield, total_mv, circ_mv, goodwill_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_code,
                    item["trade_date"],
                    item.get("pe_ttm") or old.get("pe_ttm", 0),
                    item.get("pb") or old.get("pb", 0),
                    old.get("peg", 0),
                    old.get("roe", 0),
                    old.get("gross_margin", 0),
                    old.get("netprofit_margin", 0),
                    old.get("revenue_yoy", 0),
                    old.get("deduct_profit_yoy", 0),
                    old.get("debt_to_assets", 0),
                    old.get("ocf", 0),
                    item.get("dv_ttm") or old.get("dividend_yield", 0),
                    round(float(item.get("total_mv") or 0) / 10000, 2),
                    round(float(item.get("circ_mv") or 0) / 10000, 2),
                    old.get("goodwill_ratio", 0),
                ),
            )
            count += 1
        self._sleep()
        return count

    def _sync_indices(self, pro: Any, start_date: str, end_date: str) -> int:
        count = 0
        for index_code, name in INDEX_CODE_MAP.items():
            self.conn.execute("INSERT OR REPLACE INTO index_info(index_code, name, category) VALUES (?, ?, ?)", (index_code, name, "宽基"))
            try:
                daily = pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
                for item in daily.fillna(0).to_dict(orient="records"):
                    self.conn.execute(
                        "INSERT OR REPLACE INTO index_daily(index_code, trade_date, close, pct_chg, momentum_20) VALUES (?, ?, ?, ?, ?)",
                        (index_code, item.get("trade_date"), item.get("close"), item.get("pct_chg"), 0),
                    )
                    count += 1
                self._sleep()
            except Exception:
                continue
            try:
                weight = pro.index_weight(index_code=index_code, start_date=start_date, end_date=end_date)
                for item in weight.fillna("").to_dict(orient="records"):
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO index_members(index_code, ts_code, weight, in_date, out_date)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            index_code,
                            item.get("con_code"),
                            item.get("weight") or 0,
                            item.get("trade_date") or start_date,
                            "",
                        ),
                    )
                    count += 1
                self._sleep()
            except Exception:
                continue
        self._recalculate_index_momentum()
        return count

    def _sync_news(self, pro: Any, start_date: str, end_date: str) -> int:
        try:
            df = pro.news(src="sina", start_date=start_date, end_date=end_date)
        except Exception:
            return 0
        if not isinstance(df, pd.DataFrame) or df.empty:
            return 0
        stocks = self.conn.execute("SELECT ts_code, name FROM stocks").fetchall()
        count = 0
        for item in df.fillna("").to_dict(orient="records"):
            title = str(item.get("title") or item.get("content") or "")[:120]
            content = str(item.get("content") or title)
            for stock in stocks:
                if stock["name"] and stock["name"] in title + content:
                    self.conn.execute(
                        """
                        INSERT INTO stock_news(ts_code, title, content, source, publish_time, sentiment_score, sentiment_label, keywords)
                        VALUES (?, ?, ?, ?, ?, 50, '中性', '')
                        """,
                        (
                            stock["ts_code"],
                            title,
                            content,
                            "tushare-news",
                            str(item.get("datetime") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        ),
                    )
                    count += 1
                    break
        self._sleep()
        return count

    def _recalculate_index_momentum(self) -> None:
        rows = self.conn.execute("SELECT DISTINCT index_code FROM index_daily").fetchall()
        for row in rows:
            df = pd.read_sql_query(
                "SELECT trade_date, close FROM index_daily WHERE index_code = ? ORDER BY trade_date ASC",
                self.conn,
                params=(row["index_code"],),
            )
            if df.empty:
                continue
            df["momentum_20"] = df["close"].pct_change(20).fillna(0) * 100
            for item in df.to_dict(orient="records"):
                self.conn.execute(
                    "UPDATE index_daily SET momentum_20 = ? WHERE index_code = ? AND trade_date = ?",
                    (round(float(item["momentum_20"]), 2), row["index_code"], item["trade_date"]),
                )
