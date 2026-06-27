from __future__ import annotations

import math
import re
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.core.config import load_settings
from app.models.schemas import SyncRequest
from app.services.tushare_service import INDEX_CODE_MAP


BOARD_INDEX_MAP = {
    "CONCEPT_AI": ("AI算力概念", "热门赛道", "concept", ["人工智能", "算力概念", "ChatGPT概念"]),
    "CONCEPT_SEMI": ("半导体国产替代", "热门赛道", "concept", ["半导体", "芯片概念", "国产芯片"]),
    "CONCEPT_STORAGE": ("储能新能源", "热门赛道", "concept", ["储能", "新能源车", "光伏设备"]),
    "CONCEPT_DEFENSE": ("军工安全", "热门赛道", "concept", ["军工", "航天航空"]),
    "CONCEPT_MEDICAL": ("创新医药", "热门赛道", "concept", ["创新药", "医药商业"]),
    "801080.SI": ("电子申万一级", "申万行业", "industry", ["电子元件", "半导体"]),
    "801120.SI": ("食品饮料申万一级", "申万行业", "industry", ["酿酒行业", "食品饮料"]),
    "801790.SI": ("非银金融申万一级", "申万行业", "industry", ["证券", "保险"]),
    "801780.SI": ("银行申万一级", "申万行业", "industry", ["银行"]),
}


class AkshareService:
    """AKShare公开数据同步。

    AKShare以网页公开数据封装为主，不同站点偶尔会调整字段名，因此这里统一做字段兜底：
    能取到的数据尽量落库，单个接口失败不会中断整次同步。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.settings = load_settings()
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("未安装akshare，请先安装backend/requirements.txt") from exc
        self.ak = ak

    def sync(self, request: SyncRequest, cancel_check: Callable[[], None] | None = None) -> dict[str, Any]:
        if not self.settings.akshare.enabled:
            raise RuntimeError("AKShare数据源已在配置中禁用")
        if cancel_check:
            cancel_check()

        start_date = request.start_date or self.settings.akshare.default_start_date
        end_date = request.end_date or self.settings.akshare.default_end_date or self._last_workday()
        trade_date = request.trade_date or end_date

        summary: dict[str, Any] = {
            "mode": "akshare",
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
            "tables": {},
            "warnings": [],
        }

        spot_df = self._safe_call("A股实时行情", self.ak.stock_zh_a_spot_em, summary=summary)
        if spot_df is None or spot_df.empty:
            raise RuntimeError("AKShare未返回A股实时行情")

        spot_df = self._normalize_spot(spot_df)
        summary["tables"]["stocks"] = self._sync_spot_stocks(spot_df)
        self.conn.commit()
        if cancel_check:
            cancel_check()
        summary["tables"]["daily_spot"] = self._sync_spot_daily_and_basic(spot_df, trade_date)
        self.conn.commit()
        if cancel_check:
            cancel_check()

        if request.sync_indices:
            summary["tables"]["indices"] = self._sync_indices(start_date, end_date, summary, cancel_check=cancel_check)
            summary["tables"]["boards"] = self._sync_boards(spot_df, trade_date, summary, cancel_check=cancel_check)
            if cancel_check:
                cancel_check()
        if request.sync_fundamentals:
            summary["tables"]["financial_indicators"] = self._sync_financial_indicators(
                spot_df, start_date[:4], trade_date, summary, cancel_check=cancel_check
            )
            if cancel_check:
                cancel_check()
        summary["tables"]["capital_flows"] = self._sync_capital_flows(spot_df, summary, cancel_check=cancel_check)
        if cancel_check:
            cancel_check()
        summary["tables"]["history"] = self._sync_history(spot_df, start_date, end_date, summary, cancel_check=cancel_check)
        if request.sync_news:
            if cancel_check:
                cancel_check()
            summary["tables"]["news"] = self._sync_news(spot_df, summary, cancel_check=cancel_check)

        self.conn.commit()
        return summary

    def sync_stock_history(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
        """按需补齐单只股票历史K线。

        全市场历史K线拉取会触发数千次网页请求，因此批量同步默认有限流上限。
        个股详情页需要更完整的K线时，走这个单股接口可以快速补齐，不影响其他页面读缓存。
        """
        if not self.settings.akshare.enabled:
            raise RuntimeError("AKShare数据源已在配置中禁用")

        symbol = self._symbol(ts_code)
        safe_start_date = start_date or self.settings.akshare.default_start_date
        safe_end_date = end_date or self.settings.akshare.default_end_date or self._last_workday()
        summary: dict[str, Any] = {
            "mode": "akshare",
            "task": "single_stock_history",
            "ts_code": self._ts_code(symbol),
            "start_date": safe_start_date,
            "end_date": safe_end_date,
            "warnings": [],
        }
        hist = self._safe_call(
            f"{symbol}历史行情",
            self.ak.stock_zh_a_hist,
            symbol=symbol,
            period="daily",
            start_date=safe_start_date,
            end_date=safe_end_date,
            adjust=self.settings.akshare.adjust,
            summary=summary,
        )
        if hist is None or hist.empty:
            raise RuntimeError(f"AKShare未返回 {self._ts_code(symbol)} 的历史K线")

        rows = self._insert_history(symbol, hist)
        self.conn.commit()
        summary["rows"] = rows
        return summary

    def sync_all_stock_history(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        min_rows: int | None = None,
        progress: Callable[[int, int, str, int, int], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """补齐全市场历史K线。

        选股技术因子依赖足够长的历史序列。这个任务直接遍历本地股票池，
        对K线深度不足的股票从AKShare拉取默认历史区间，已达标的股票跳过。
        """
        if not self.settings.akshare.enabled:
            raise RuntimeError("AKShare数据源已在配置中禁用")
        if cancel_check:
            cancel_check()

        safe_start_date = start_date or self.settings.akshare.default_start_date
        safe_end_date = end_date or self.settings.akshare.default_end_date or self._last_workday()
        safe_min_rows = max(int(min_rows or self.settings.akshare.history_min_rows or 120), 1)
        symbols = [
            str(row["symbol"])
            for row in self.conn.execute(
                """
                SELECT symbol
                FROM stocks
                WHERE COALESCE(symbol, '') != ''
                ORDER BY ts_code
                """
            ).fetchall()
        ]
        if not symbols:
            spot_df = self._safe_call("A股实时行情", self.ak.stock_zh_a_spot_em)
            if spot_df is None or spot_df.empty:
                raise RuntimeError("股票池为空，且AKShare未返回A股实时行情")
            spot_df = self._normalize_spot(spot_df)
            self._sync_spot_stocks(spot_df)
            self.conn.commit()
            symbols = spot_df["代码"].astype(str).tolist()

        dirty_symbols = self._dirty_history_symbols()
        symbols = sorted(
            list(dict.fromkeys([self._symbol(symbol) for symbol in symbols])),
            key=lambda symbol: (0 if self._ts_code(symbol) in dirty_symbols else 1, self._ts_code(symbol)),
        )

        total = len(symbols)
        fetched_symbols = 0
        skipped_symbols = 0
        failed_symbols = 0
        inserted_rows = 0
        warnings: list[str] = []

        for index, symbol in enumerate(symbols, start=1):
            if cancel_check:
                cancel_check()
            normalized = self._symbol(symbol)
            ts_code = self._ts_code(normalized)
            existing = self.conn.execute(
                "SELECT COUNT(*) AS rows_count, MAX(trade_date) AS latest_date FROM stock_daily WHERE ts_code = ?",
                (ts_code,),
            ).fetchone()
            existing_rows = int(existing["rows_count"] or 0) if existing else 0
            latest_date = str(existing["latest_date"] or "") if existing else ""
            if ts_code not in dirty_symbols and existing_rows >= safe_min_rows and latest_date >= safe_end_date:
                skipped_symbols += 1
                if progress and (index == total or index % 25 == 0):
                    progress(index, total, ts_code, inserted_rows, skipped_symbols)
                continue

            hist = self._safe_call(
                f"{normalized}历史行情",
                self.ak.stock_zh_a_hist,
                symbol=normalized,
                period="daily",
                start_date=safe_start_date,
                end_date=safe_end_date,
                adjust=self.settings.akshare.adjust,
            )
            if hist is None or hist.empty:
                failed_symbols += 1
                if len(warnings) < 50:
                    warnings.append(f"{ts_code} 历史K线为空")
                if progress and (index == total or index % 10 == 0):
                    progress(index, total, ts_code, inserted_rows, skipped_symbols)
                self._sleep()
                continue

            inserted_rows += self._insert_history(normalized, hist)
            fetched_symbols += 1
            self.conn.commit()
            if progress and (index == total or index % 10 == 0):
                progress(index, total, ts_code, inserted_rows, skipped_symbols)
            self._sleep()

        return {
            "mode": "akshare",
            "task": "all_stock_history",
            "start_date": safe_start_date,
            "end_date": safe_end_date,
            "min_rows": safe_min_rows,
            "total_symbols": total,
            "fetched_symbols": fetched_symbols,
            "skipped_symbols": skipped_symbols,
            "failed_symbols": failed_symbols,
            "rows": inserted_rows,
            "warnings": warnings,
        }

    def _dirty_history_symbols(self) -> set[str]:
        """找出价格口径断层的股票，优先重新拉历史K线修复。

        典型脏数据表现：上一日 close 是一套口径，下一日实时快照的 pre_close
        却指向另一套价格，例如 688981.SH 的 74.91 -> 148.76。
        """
        rows = self.conn.execute(
            """
            SELECT ts_code, trade_date, close, pre_close, pct_chg
            FROM stock_daily
            ORDER BY ts_code, trade_date
            """
        ).fetchall()
        dirty: set[str] = set()
        previous_ts_code = ""
        previous_close = 0.0
        for row in rows:
            ts_code = str(row["ts_code"])
            close = self._num(row["close"])
            pre_close = self._num(row["pre_close"])
            pct_chg = abs(self._num(row["pct_chg"]))
            if ts_code == previous_ts_code and previous_close > 0 and pre_close > 0 and pct_chg < 35:
                ratio = previous_close / pre_close
                if ratio > 1.35 or ratio < 0.65:
                    dirty.add(ts_code)
            previous_ts_code = ts_code
            previous_close = close
        return dirty

    def _sync_spot_stocks(self, df: pd.DataFrame) -> int:
        count = 0
        metadata = self._metadata_for_symbols(df["代码"].head(max(0, self.settings.akshare.max_metadata_symbols)).tolist())
        official_names = self._official_names()
        for item in df.to_dict(orient="records"):
            symbol = self._symbol(item["代码"])
            ts_code = self._ts_code(symbol)
            realtime_name = str(item.get("名称") or "")
            existing = self.conn.execute("SELECT name FROM stocks WHERE ts_code = ?", (ts_code,)).fetchone()
            existing_name = str(existing["name"] or "") if existing else ""
            name = official_names.get(symbol) or self._stable_stock_name(realtime_name, existing_name)
            meta = metadata.get(symbol, {})
            self.conn.execute(
                """
                INSERT OR REPLACE INTO stocks
                (ts_code, symbol, name, area, industry, market, exchange, list_date, is_hs, is_st, is_paused, updated_at)
                VALUES (
                    ?, ?, ?,
                    COALESCE(NULLIF(?, ''), (SELECT area FROM stocks WHERE ts_code = ?)),
                    COALESCE(NULLIF(?, ''), (SELECT industry FROM stocks WHERE ts_code = ?)),
                    COALESCE(NULLIF(?, ''), (SELECT market FROM stocks WHERE ts_code = ?)),
                    ?, COALESCE(NULLIF(?, ''), (SELECT list_date FROM stocks WHERE ts_code = ?)),
                    COALESCE((SELECT is_hs FROM stocks WHERE ts_code = ?), ''),
                    ?, ?, CURRENT_TIMESTAMP
                )
                """,
                (
                    ts_code,
                    symbol,
                    name,
                    str(meta.get("area") or ""),
                    ts_code,
                    str(meta.get("industry") or ""),
                    ts_code,
                    str(meta.get("market") or ""),
                    ts_code,
                    self._exchange(symbol),
                    str(meta.get("list_date") or ""),
                    ts_code,
                    ts_code,
                    1 if "ST" in name.upper() else 0,
                    1 if self._num(item.get("最新价")) <= 0 else 0,
                ),
            )
            count += 1
        return count

    def _official_names(self) -> dict[str, str]:
        df = self._safe_call("A股官方简称", self.ak.stock_info_a_code_name)
        if df is None or df.empty:
            return {}
        result: dict[str, str] = {}
        for item in df.to_dict(orient="records"):
            code = self._pick(item, ["code", "代码"], "")
            name = str(self._pick(item, ["name", "名称"], "") or "").strip()
            symbol = self._symbol(code)
            if symbol and name:
                result[symbol] = name
        return result

    @classmethod
    def _stable_stock_name(cls, realtime_name: str, existing_name: str) -> str:
        realtime = str(realtime_name or "").strip()
        existing = str(existing_name or "").strip()
        if cls._is_status_prefixed_name(realtime) and existing and not cls._is_status_prefixed_name(existing):
            return existing
        return cls._strip_realtime_prefix(realtime) or existing

    @staticmethod
    def _is_status_prefixed_name(value: str) -> bool:
        return bool(re.match(r"^(\*?ST|XD|XR|DR)", str(value or "").strip(), flags=re.I))

    @staticmethod
    def _strip_realtime_prefix(value: str) -> str:
        text = str(value or "").strip()
        return re.sub(r"^(\*?ST|XD|XR|DR)", "", text, flags=re.I).strip()

    def _sync_spot_daily_and_basic(self, df: pd.DataFrame, trade_date: str) -> int:
        count = 0
        for item in df.to_dict(orient="records"):
            symbol = self._symbol(item["代码"])
            ts_code = self._ts_code(symbol)
            close = self._num(item.get("最新价"))
            pre_close = self._num(item.get("昨收"))
            change = self._num(item.get("涨跌额"))
            pct_chg = self._num(item.get("涨跌幅"))
            self.conn.execute(
                """
                INSERT OR REPLACE INTO stock_daily
                (ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, turnover_rate, volume_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_code,
                    trade_date,
                    self._num(item.get("今开")),
                    self._num(item.get("最高")),
                    self._num(item.get("最低")),
                    close,
                    pre_close,
                    change if change else close - pre_close if pre_close else 0,
                    pct_chg,
                    self._num(item.get("成交量")),
                    self._num(item.get("成交额")),
                    self._num(item.get("换手率")),
                    self._num(item.get("量比")),
                ),
            )
            existing = self.conn.execute(
                "SELECT * FROM fundamentals WHERE ts_code = ? AND trade_date = ?",
                (ts_code, trade_date),
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
                    trade_date,
                    self._num(item.get("市盈率-动态")) or old.get("pe_ttm", 0),
                    self._num(item.get("市净率")) or old.get("pb", 0),
                    old.get("peg", 0),
                    old.get("roe", 0),
                    old.get("gross_margin", 0),
                    old.get("netprofit_margin", 0),
                    old.get("revenue_yoy", 0),
                    old.get("deduct_profit_yoy", 0),
                    old.get("debt_to_assets", 0),
                    old.get("ocf", 0),
                    old.get("dividend_yield", 0),
                    round(self._num(item.get("总市值")) / 100_000_000, 2),
                    round(self._num(item.get("流通市值")) / 100_000_000, 2),
                    old.get("goodwill_ratio", 0),
                ),
            )
            count += 1
        return count

    def _sync_history(
        self,
        df: pd.DataFrame,
        start_date: str,
        end_date: str,
        summary: dict[str, Any],
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        symbols = self._candidate_symbols(df, self.settings.akshare.max_history_symbols)
        count = 0
        for symbol in symbols:
            if cancel_check:
                cancel_check()
            hist = self._safe_call(
                f"{symbol}历史行情",
                self.ak.stock_zh_a_hist,
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=self.settings.akshare.adjust,
                summary=summary,
            )
            if hist is None or hist.empty:
                continue
            count += self._insert_history(symbol, hist)
            self.conn.commit()
            self._sleep()
        return count

    def _sync_financial_indicators(
        self,
        df: pd.DataFrame,
        start_year: str,
        trade_date: str,
        summary: dict[str, Any],
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        symbols = self._candidate_symbols(df, self.settings.akshare.max_financial_symbols)
        count = 0
        for symbol in symbols:
            if cancel_check:
                cancel_check()
            fin = self._safe_call(
                f"{symbol}财务指标",
                self.ak.stock_financial_analysis_indicator,
                symbol=symbol,
                start_year=start_year,
                summary=summary,
            )
            if fin is None or fin.empty:
                continue
            latest = fin.sort_values("日期").iloc[-1].to_dict()
            ts_code = self._ts_code(symbol)
            existing = self.conn.execute(
                "SELECT * FROM fundamentals WHERE ts_code = ? AND trade_date = ?",
                (ts_code, trade_date),
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
                    trade_date,
                    old.get("pe_ttm", 0),
                    old.get("pb", 0),
                    old.get("peg", 0),
                    self._pick_num(latest, ["净资产收益率(%)", "加权净资产收益率(%)"], old.get("roe", 0)),
                    self._pick_num(latest, ["销售毛利率(%)"], old.get("gross_margin", 0)),
                    self._pick_num(latest, ["销售净利率(%)"], old.get("netprofit_margin", 0)),
                    self._pick_num(latest, ["主营业务收入增长率(%)", "营业总收入同比增长率(%)"], old.get("revenue_yoy", 0)),
                    self._pick_num(latest, ["净利润增长率(%)", "扣非净利润同比增长率(%)"], old.get("deduct_profit_yoy", 0)),
                    self._pick_num(latest, ["资产负债率(%)"], old.get("debt_to_assets", 0)),
                    self._pick_num(latest, ["经营现金净流量与净利润的比率(%)", "每股经营性现金流(元)"], old.get("ocf", 0)),
                    self._pick_num(latest, ["股息发放率(%)"], old.get("dividend_yield", 0)),
                    old.get("total_mv", 0),
                    old.get("circ_mv", 0),
                    old.get("goodwill_ratio", 0),
                ),
            )
            count += 1
            self.conn.commit()
            self._sleep()
        return count

    def _sync_capital_flows(
        self,
        df: pd.DataFrame,
        summary: dict[str, Any],
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        symbols = self._candidate_symbols(df, self.settings.akshare.max_history_symbols)
        count = 0
        for symbol in symbols:
            if cancel_check:
                cancel_check()
            market = self._exchange(symbol).lower()
            if market == "bj":
                continue
            flow = self._safe_call(
                f"{symbol}资金流",
                self.ak.stock_individual_fund_flow,
                stock=symbol,
                market=market,
                summary=summary,
            )
            if flow is None or flow.empty:
                continue
            for item in flow.tail(60).to_dict(orient="records"):
                trade_date = self._date8(item.get("日期"))
                if not trade_date:
                    continue
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO capital_flows
                    (ts_code, trade_date, north_inflow, main_net_inflow, margin_balance_delta, institution_holding_ratio, top_list_score)
                    VALUES (?, ?, COALESCE((SELECT north_inflow FROM capital_flows WHERE ts_code=? AND trade_date=?), 0),
                            ?, COALESCE((SELECT margin_balance_delta FROM capital_flows WHERE ts_code=? AND trade_date=?), 0),
                            COALESCE((SELECT institution_holding_ratio FROM capital_flows WHERE ts_code=? AND trade_date=?), 0), ?)
                    """,
                    (
                        self._ts_code(symbol),
                        trade_date,
                        self._ts_code(symbol),
                        trade_date,
                        round(self._num(item.get("主力净流入-净额")) / 10_000, 2),
                        self._ts_code(symbol),
                        trade_date,
                        self._ts_code(symbol),
                        trade_date,
                        self._flow_score(item.get("主力净流入-净占比")),
                    ),
                )
                count += 1
            self.conn.commit()
            self._sleep()
        return count

    def _sync_news(self, df: pd.DataFrame, summary: dict[str, Any], cancel_check: Callable[[], None] | None = None) -> int:
        symbols = self._candidate_symbols(df, self.settings.akshare.max_news_symbols)
        count = 0
        for symbol in symbols:
            if cancel_check:
                cancel_check()
            news = self._safe_call(f"{symbol}新闻", self.ak.stock_news_em, symbol=symbol, summary=summary)
            if news is None or news.empty:
                continue
            for item in news.head(20).to_dict(orient="records"):
                title = str(self._pick(item, ["新闻标题", "标题", "title"], ""))
                content = str(self._pick(item, ["新闻内容", "内容", "摘要", "title"], title))
                if not title and not content:
                    continue
                publish_time = str(self._pick(item, ["发布时间", "时间", "datetime"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                self.conn.execute(
                    """
                    INSERT INTO stock_news(ts_code, title, content, source, publish_time, sentiment_score, sentiment_label, keywords)
                    VALUES (?, ?, ?, ?, ?, 50, '中性', ?)
                    """,
                    (
                        self._ts_code(symbol),
                        title[:160],
                        content[:2000],
                        str(self._pick(item, ["文章来源", "来源"], "akshare-news")),
                        publish_time,
                        str(self._pick(item, ["关键词"], "")),
                    ),
                )
                count += 1
            self.conn.commit()
            self._sleep()
        return count

    def _sync_indices(
        self,
        start_date: str,
        end_date: str,
        summary: dict[str, Any],
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        count = 0
        for index_code, name in INDEX_CODE_MAP.items():
            if cancel_check:
                cancel_check()
            symbol = index_code.split(".")[0]
            self.conn.execute("INSERT OR REPLACE INTO index_info(index_code, name, category) VALUES (?, ?, ?)", (index_code, name, "宽基"))
            hist = self._safe_call(
                f"{name}指数行情",
                self.ak.index_zh_a_hist,
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                summary=summary,
            )
            if hist is not None and not hist.empty:
                for item in hist.to_dict(orient="records"):
                    self.conn.execute(
                        "INSERT OR REPLACE INTO index_daily(index_code, trade_date, close, pct_chg, momentum_20) VALUES (?, ?, ?, ?, ?)",
                        (index_code, self._date8(item.get("日期")), self._num(item.get("收盘")), self._num(item.get("涨跌幅")), 0),
                    )
                    count += 1
            members = self._index_members(symbol, summary)
            for item in members:
                self.conn.execute(
                    "INSERT OR REPLACE INTO index_members(index_code, ts_code, weight, in_date, out_date) VALUES (?, ?, ?, ?, '')",
                    (index_code, self._ts_code(item["symbol"]), item.get("weight", 0), item.get("in_date") or start_date),
                )
                count += 1
            self.conn.commit()
            self._sleep()
        self._recalculate_index_momentum()
        self.conn.commit()
        return count

    def _sync_boards(
        self,
        spot_df: pd.DataFrame,
        trade_date: str,
        summary: dict[str, Any],
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        count = 0
        spot_lookup = {self._symbol(row["代码"]): row for row in spot_df.to_dict(orient="records")}
        for index_code, (name, category, kind, candidates) in BOARD_INDEX_MAP.items():
            if cancel_check:
                cancel_check()
            self.conn.execute("INSERT OR REPLACE INTO index_info(index_code, name, category) VALUES (?, ?, ?)", (index_code, name, category))
            members: list[str] = []
            for board_name in candidates:
                func = self.ak.stock_board_concept_cons_em if kind == "concept" else self.ak.stock_board_industry_cons_em
                board = self._safe_call(f"{board_name}板块成分", func, symbol=board_name, summary=summary)
                if board is not None and not board.empty:
                    members = [self._symbol(item) for item in board["代码"].astype(str).tolist()]
                    break
            for symbol in members:
                self.conn.execute(
                    "INSERT OR REPLACE INTO index_members(index_code, ts_code, weight, in_date, out_date) VALUES (?, ?, ?, ?, '')",
                    (index_code, self._ts_code(symbol), 0, trade_date),
                )
                count += 1
            board_closes = [self._num(spot_lookup.get(symbol, {}).get("最新价")) for symbol in members if symbol in spot_lookup]
            board_pct = [self._num(spot_lookup.get(symbol, {}).get("涨跌幅")) for symbol in members if symbol in spot_lookup]
            if board_closes:
                self.conn.execute(
                    "INSERT OR REPLACE INTO index_daily(index_code, trade_date, close, pct_chg, momentum_20) VALUES (?, ?, ?, ?, ?)",
                    (index_code, trade_date, round(sum(board_closes) / len(board_closes), 2), round(sum(board_pct) / max(1, len(board_pct)), 2), 0),
                )
                count += 1
            self.conn.execute(
                """
                INSERT OR REPLACE INTO index_valuation(index_code, trade_date, pe, pb, pe_percentile, pb_percentile)
                VALUES (?, ?, COALESCE((SELECT pe FROM index_valuation WHERE index_code=? ORDER BY trade_date DESC LIMIT 1), 0),
                        COALESCE((SELECT pb FROM index_valuation WHERE index_code=? ORDER BY trade_date DESC LIMIT 1), 0),
                        COALESCE((SELECT pe_percentile FROM index_valuation WHERE index_code=? ORDER BY trade_date DESC LIMIT 1), 50),
                        COALESCE((SELECT pb_percentile FROM index_valuation WHERE index_code=? ORDER BY trade_date DESC LIMIT 1), 50))
                """,
                (index_code, trade_date, index_code, index_code, index_code, index_code),
            )
            self.conn.commit()
            self._sleep()
        return count

    def _metadata_for_symbols(self, symbols: list[str]) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        for symbol in symbols:
            info = self._safe_call(f"{symbol}基础信息", self.ak.stock_individual_info_em, symbol=symbol)
            if info is None or info.empty:
                continue
            meta: dict[str, str] = {}
            for row in info.to_dict(orient="records"):
                key = str(self._pick(row, ["item", "项目", "指标"], ""))
                value = str(self._pick(row, ["value", "值", "信息"], ""))
                if "行业" in key:
                    meta["industry"] = value
                if "上市时间" in key or "上市日期" in key:
                    meta["list_date"] = self._date8(value)
                if "市场" in key:
                    meta["market"] = value
            result[symbol] = meta
            self._sleep()
        return result

    def _index_members(self, symbol: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
        funcs = [
            (self.ak.index_stock_cons, {"symbol": symbol}),
            (self.ak.index_stock_cons_csindex, {"symbol": symbol}),
            (self.ak.index_stock_cons_sina, {"symbol": symbol}),
        ]
        for func, kwargs in funcs:
            df = self._safe_call(f"{symbol}指数成分", func, summary=summary, **kwargs)
            if df is None or df.empty:
                continue
            rows: list[dict[str, Any]] = []
            for item in df.to_dict(orient="records"):
                code = str(self._pick(item, ["品种代码", "成分券代码", "证券代码", "code"], ""))
                if code:
                    rows.append(
                        {
                            "symbol": self._symbol(code),
                            "weight": self._pick_num(item, ["权重", "权重(%)"], 0),
                            "in_date": self._date8(self._pick(item, ["纳入日期", "日期"], "")),
                        }
                    )
            if rows:
                return rows
        return []

    def _insert_history(self, symbol: str, hist: pd.DataFrame) -> int:
        count = 0
        ts_code = self._ts_code(symbol)
        data = hist.sort_values("日期").to_dict(orient="records")
        previous_close = 0.0
        for item in data:
            trade_date = self._date8(item.get("日期"))
            close = self._num(item.get("收盘"))
            pre_close = previous_close or close - self._num(item.get("涨跌额"))
            self.conn.execute(
                """
                INSERT OR REPLACE INTO stock_daily
                (ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, turnover_rate, volume_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT volume_ratio FROM stock_daily WHERE ts_code=? AND trade_date=?), 0))
                """,
                (
                    ts_code,
                    trade_date,
                    self._num(item.get("开盘")),
                    self._num(item.get("最高")),
                    self._num(item.get("最低")),
                    close,
                    pre_close,
                    self._num(item.get("涨跌额")) or close - pre_close,
                    self._num(item.get("涨跌幅")),
                    self._num(item.get("成交量")),
                    self._num(item.get("成交额")),
                    self._num(item.get("换手率")),
                    ts_code,
                    trade_date,
                ),
            )
            previous_close = close
            count += 1
        return count

    def _candidate_symbols(self, df: pd.DataFrame, limit: int) -> list[str]:
        existing = [row["symbol"] for row in self.conn.execute("SELECT symbol FROM stocks ORDER BY ts_code").fetchall()]
        ordered = list(dict.fromkeys([self._symbol(symbol) for symbol in existing + df["代码"].astype(str).tolist()]))
        if limit <= 0:
            return ordered
        return ordered[:limit]

    def _safe_call(self, label: str, func: Any, summary: dict[str, Any] | None = None, **kwargs: Any) -> pd.DataFrame | None:
        try:
            value = func(**kwargs)
            if isinstance(value, pd.DataFrame):
                return value
            return pd.DataFrame(value)
        except Exception as exc:
            if summary is not None:
                warnings = summary.setdefault("warnings", [])
                if len(warnings) < 30:
                    warnings.append(f"{label}失败：{exc}")
            return None

    def _normalize_spot(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        data["代码"] = data["代码"].astype(str).str.zfill(6)
        data = data[data["代码"].str.match(r"^\d{6}$", na=False)]
        return data

    @staticmethod
    def _pick(row: dict[str, Any], keys: list[str], default: Any = None) -> Any:
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        return default

    def _pick_num(self, row: dict[str, Any], keys: list[str], default: float = 0.0) -> float:
        for key in keys:
            if key in row:
                value = self._num(row.get(key))
                if value:
                    return value
        return float(default or 0)

    @staticmethod
    def _num(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            number = float(value)
            if math.isnan(number) or math.isinf(number):
                return 0.0
            return number
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _symbol(value: Any) -> str:
        raw = str(value).strip().upper()
        if "." in raw:
            raw = raw.split(".")[0]
        return raw.zfill(6)

    @staticmethod
    def _exchange(symbol: str) -> str:
        if symbol.startswith(("8", "4", "920")):
            return "BJ"
        if symbol.startswith(("0", "2", "3")):
            return "SZ"
        return "SH"

    def _ts_code(self, symbol: str) -> str:
        return f"{self._symbol(symbol)}.{self._exchange(self._symbol(symbol))}"

    @staticmethod
    def _date8(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            return pd.to_datetime(text).strftime("%Y%m%d")
        except Exception:
            return text.replace("-", "")[:8]

    @staticmethod
    def _flow_score(value: Any) -> float:
        number = AkshareService._num(value)
        return round(max(0, min(100, 50 + number * 2)), 2)

    @staticmethod
    def _last_workday() -> str:
        day = datetime.now().date()
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        return day.strftime("%Y%m%d")

    def _sleep(self) -> None:
        time.sleep(max(0, self.settings.akshare.request_interval_seconds))

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
