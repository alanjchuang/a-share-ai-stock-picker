from __future__ import annotations

import math
import sqlite3
import time
from collections.abc import Callable
from typing import Any

import pandas as pd

from app.core.config import load_settings
from app.models.schemas import EtfDailyPoint, EtfDetail, EtfMarketItem, EtfMarketResponse


class EtfService:
    """ETF独立行情服务。

    ETF没有个股财报和ROE这类基本面字段，因此单独维护ETF资产池和ETF日线，
    避免混入股票多因子选股后造成口径污染。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.settings = load_settings()
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("未安装akshare，请先安装backend/requirements.txt") from exc
        self.ak = ak

    def sync(
        self,
        history_limit: int = 0,
        progress: Callable[[int, int, str, int], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.akshare.enabled:
            raise RuntimeError("AKShare数据源已在配置中禁用")
        if cancel_check:
            cancel_check()

        spot = self._safe_call("ETF实时行情", self.ak.fund_etf_spot_em)
        if spot is None or spot.empty:
            raise RuntimeError("AKShare未返回ETF实时行情")

        spot = self._normalize_spot(spot)
        spot_count = self._sync_spot(spot)
        self.conn.commit()

        fund_type_count = self._sync_fund_types()
        self.conn.commit()

        symbols = self._history_symbols(spot, history_limit)
        inserted_rows = 0
        failed_symbols = 0
        total = len(symbols)
        start_date = self.settings.akshare.default_start_date
        end_date = self.settings.akshare.default_end_date or self._latest_trade_date_from_spot(spot)
        for index, symbol in enumerate(symbols, start=1):
            if cancel_check:
                cancel_check()
            hist = self._safe_call(
                f"{symbol} ETF历史行情",
                self.ak.fund_etf_hist_em,
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=self.settings.akshare.adjust,
            )
            if hist is None or hist.empty:
                failed_symbols += 1
                if progress and (index == total or index % 10 == 0):
                    progress(index, total, self._etf_code(symbol), inserted_rows)
                self._sleep()
                continue
            inserted_rows += self._insert_history(symbol, hist)
            self.conn.commit()
            if progress and (index == total or index % 10 == 0):
                progress(index, total, self._etf_code(symbol), inserted_rows)
            self._sleep()

        return {
            "mode": "akshare",
            "task": "etf_sync",
            "spot_count": spot_count,
            "fund_type_count": fund_type_count,
            "history_symbols": total,
            "failed_symbols": failed_symbols,
            "rows": inserted_rows,
            "history_limit": history_limit,
        }

    def list_market(
        self,
        q: str = "",
        category: str | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "amount",
        sort_order: str = "desc",
    ) -> EtfMarketResponse:
        rows = self._market_rows()
        keyword = q.strip().lower()
        filtered = [
            row
            for row in rows
            if self._matches(row, keyword=keyword, category=category)
        ]

        sort_field = sort_by if sort_by in self._sortable_fields() else "amount"
        reverse = sort_order.lower() != "asc"
        filtered.sort(key=lambda row: self._sort_value(row, sort_field), reverse=reverse)

        safe_page_size = min(max(int(page_size or 50), 10), 200)
        safe_page = max(int(page or 1), 1)
        start = (safe_page - 1) * safe_page_size
        page_rows = filtered[start : start + safe_page_size]
        categories = sorted({str(row.get("category") or "其他") for row in rows})
        return EtfMarketResponse(
            total=len(filtered),
            page=safe_page,
            page_size=safe_page_size,
            rows=[self._to_item(row) for row in page_rows],
            latest_trade_date=self._latest_trade_date(),
            categories=categories,
        )

    def detail(self, etf_code: str) -> EtfDetail:
        normalized = self._etf_code(etf_code)
        rows = self._market_rows()
        row = next((item for item in rows if item["etf_code"] == normalized), None)
        if not row:
            raise ValueError("ETF不存在或尚未同步")
        daily = self._daily_frame(normalized, limit=180)
        tech = self._add_mas(daily)
        kline = [
            EtfDailyPoint(
                trade_date=str(item["trade_date"]),
                open=float(item["open"] or 0),
                close=float(item["close"] or 0),
                low=float(item["low"] or 0),
                high=float(item["high"] or 0),
                volume=float(item["vol"] or 0),
                amount=float(item["amount"] or 0),
                ma5=self._optional_float(item.get("ma5")),
                ma20=self._optional_float(item.get("ma20")),
                ma60=self._optional_float(item.get("ma60")),
            )
            for item in tech.to_dict(orient="records")
        ]
        warnings: list[str] = []
        if not kline:
            warnings.append("当前ETF缺少K线，请在ETF中心触发同步。")
        elif len(kline) < 60:
            warnings.append(f"当前仅有 {len(kline)} 条ETF K线，波动率和回撤指标会偏弱。")
        return EtfDetail(base=self._to_item(row), kline=kline, data_warnings=warnings)

    def _sync_spot(self, df: pd.DataFrame) -> int:
        count = 0
        for item in df.to_dict(orient="records"):
            symbol = self._symbol(item.get("代码"))
            etf_code = self._etf_code(symbol)
            trade_date = self._date8(item.get("数据日期")) or self.settings.akshare.default_end_date or ""
            name = str(item.get("名称") or "").strip()
            close = self._num(item.get("最新价"))
            pre_close = self._num(item.get("昨收"))
            self.conn.execute(
                """
                INSERT OR REPLACE INTO etfs
                (etf_code, symbol, name, category, fund_type, exchange, latest_price, iopv, discount_rate,
                 latest_share, flow_mv, total_mv, data_date, updated_at)
                VALUES (?, ?, ?, ?, COALESCE((SELECT fund_type FROM etfs WHERE etf_code=?), ''),
                        ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    etf_code,
                    symbol,
                    name,
                    self._category(name),
                    etf_code,
                    self._exchange(symbol),
                    close,
                    self._num(item.get("IOPV实时估值")),
                    self._num(item.get("基金折价率")),
                    self._num(item.get("最新份额")),
                    round(self._num(item.get("流通市值")) / 100_000_000, 2),
                    round(self._num(item.get("总市值")) / 100_000_000, 2),
                    trade_date,
                ),
            )
            if trade_date:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO etf_daily
                    (etf_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, amplitude, turnover_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        etf_code,
                        trade_date,
                        self._num(item.get("开盘价")),
                        self._num(item.get("最高价")),
                        self._num(item.get("最低价")),
                        close,
                        pre_close,
                        self._num(item.get("涨跌额")) or close - pre_close if pre_close else 0,
                        self._num(item.get("涨跌幅")),
                        self._num(item.get("成交量")),
                        self._num(item.get("成交额")),
                        self._num(item.get("振幅")),
                        self._num(item.get("换手率")),
                    ),
                )
            count += 1
        return count

    def _sync_fund_types(self) -> int:
        df = self._safe_call("ETF基金净值类型", self.ak.fund_etf_fund_daily_em)
        if df is None or df.empty:
            return 0
        count = 0
        for item in df.to_dict(orient="records"):
            symbol = self._symbol(item.get("基金代码"))
            if not symbol:
                continue
            etf_code = self._etf_code(symbol)
            fund_type = str(item.get("类型") or "")
            name = str(item.get("基金简称") or "")
            self.conn.execute(
                """
                UPDATE etfs
                SET fund_type = COALESCE(NULLIF(?, ''), fund_type),
                    category = COALESCE(NULLIF(?, ''), category)
                WHERE etf_code = ?
                """,
                (fund_type, self._category(name or fund_type), etf_code),
            )
            count += 1
        return count

    def _insert_history(self, symbol: str, hist: pd.DataFrame) -> int:
        etf_code = self._etf_code(symbol)
        count = 0
        previous_close = 0.0
        for item in hist.sort_values("日期").to_dict(orient="records"):
            trade_date = self._date8(item.get("日期"))
            if not trade_date:
                continue
            close = self._num(item.get("收盘"))
            change = self._num(item.get("涨跌额"))
            pre_close = previous_close or close - change
            self.conn.execute(
                """
                INSERT OR REPLACE INTO etf_daily
                (etf_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, amplitude, turnover_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    etf_code,
                    trade_date,
                    self._num(item.get("开盘")),
                    self._num(item.get("最高")),
                    self._num(item.get("最低")),
                    close,
                    pre_close,
                    change or close - pre_close,
                    self._num(item.get("涨跌幅")),
                    self._num(item.get("成交量")),
                    self._num(item.get("成交额")),
                    self._num(item.get("振幅")),
                    self._num(item.get("换手率")),
                ),
            )
            previous_close = close
            count += 1
        return count

    def _market_rows(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT e.*, d.trade_date, d.close, d.pct_chg, d.amount, d.turnover_rate
            FROM etfs e
            LEFT JOIN (
                SELECT d1.*
                FROM etf_daily d1
                JOIN (
                    SELECT etf_code, MAX(trade_date) AS trade_date
                    FROM etf_daily
                    GROUP BY etf_code
                ) latest ON latest.etf_code = d1.etf_code AND latest.trade_date = d1.trade_date
            ) d ON d.etf_code = e.etf_code
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data.update(self._history_metrics(str(data["etf_code"])))
            result.append(data)
        return result

    def _history_metrics(self, etf_code: str) -> dict[str, float | None]:
        daily = self._daily_frame(etf_code, limit=160)
        if daily.empty:
            return {"pct_chg_20": None, "pct_chg_60": None, "pct_chg_120": None, "volatility_60": None, "max_drawdown_120": None}
        close = pd.to_numeric(daily["close"], errors="coerce").dropna()
        if close.empty:
            return {"pct_chg_20": None, "pct_chg_60": None, "pct_chg_120": None, "volatility_60": None, "max_drawdown_120": None}
        returns = close.pct_change().dropna()
        tail_120 = close.tail(120)
        running_max = tail_120.cummax()
        drawdowns = (tail_120 / running_max - 1) * 100 if not tail_120.empty else pd.Series(dtype=float)
        return {
            "pct_chg_20": self._window_return(close, 20),
            "pct_chg_60": self._window_return(close, 60),
            "pct_chg_120": self._window_return(close, 120),
            "volatility_60": round(float(returns.tail(60).std() * math.sqrt(252) * 100), 2) if len(returns) >= 2 else None,
            "max_drawdown_120": round(float(drawdowns.min()), 2) if not drawdowns.empty else None,
        }

    def _daily_frame(self, etf_code: str, limit: int | None = None) -> pd.DataFrame:
        rows = self.conn.execute(
            "SELECT * FROM etf_daily WHERE etf_code = ? ORDER BY trade_date ASC",
            (self._etf_code(etf_code),),
        ).fetchall()
        frame = pd.DataFrame([dict(row) for row in rows])
        if limit and not frame.empty:
            frame = frame.tail(limit)
        return frame.reset_index(drop=True)

    @staticmethod
    def _add_mas(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        data = df.copy()
        data["close"] = pd.to_numeric(data["close"], errors="coerce")
        for window in [5, 20, 60]:
            data[f"ma{window}"] = data["close"].rolling(window, min_periods=1).mean().round(4)
        return data

    @staticmethod
    def _window_return(close: pd.Series, days: int) -> float | None:
        if len(close) <= days:
            return None
        base = float(close.iloc[-days - 1])
        latest = float(close.iloc[-1])
        return round((latest - base) / base * 100, 2) if base else None

    def _history_symbols(self, spot: pd.DataFrame, history_limit: int) -> list[str]:
        data = spot.copy()
        data["成交额"] = pd.to_numeric(data.get("成交额"), errors="coerce").fillna(0)
        data = data.sort_values("成交额", ascending=False)
        symbols = [self._symbol(value) for value in data["代码"].astype(str).tolist()]
        if history_limit <= 0:
            return symbols
        return symbols[:history_limit]

    @staticmethod
    def _matches(row: dict[str, Any], keyword: str, category: str | None) -> bool:
        if category and category != "全部" and str(row.get("category") or "其他") != category:
            return False
        if not keyword:
            return True
        haystack = " ".join(str(row.get(key) or "") for key in ["etf_code", "symbol", "name", "category", "fund_type"]).lower()
        return keyword in haystack

    @staticmethod
    def _sortable_fields() -> set[str]:
        return {"amount", "pct_chg", "pct_chg_20", "pct_chg_60", "pct_chg_120", "turnover_rate", "total_mv", "discount_rate", "volatility_60", "max_drawdown_120"}

    @staticmethod
    def _sort_value(row: dict[str, Any], key: str) -> float:
        value = row.get(key)
        return float(value) if isinstance(value, (int, float)) and math.isfinite(float(value)) else -1e18

    @classmethod
    def _to_item(cls, row: dict[str, Any]) -> EtfMarketItem:
        return EtfMarketItem(
            etf_code=str(row["etf_code"]),
            symbol=str(row["symbol"]),
            name=str(row["name"]),
            category=str(row.get("category") or "其他"),
            fund_type=str(row.get("fund_type") or ""),
            exchange=str(row.get("exchange") or ""),
            trade_date=row.get("trade_date"),
            close=cls._optional_float(row.get("close") or row.get("latest_price")),
            pct_chg=cls._optional_float(row.get("pct_chg")),
            amount=cls._optional_float(row.get("amount")),
            turnover_rate=cls._optional_float(row.get("turnover_rate")),
            iopv=cls._optional_float(row.get("iopv")),
            discount_rate=cls._optional_float(row.get("discount_rate")),
            flow_mv=cls._optional_float(row.get("flow_mv")),
            total_mv=cls._optional_float(row.get("total_mv")),
            pct_chg_20=cls._optional_float(row.get("pct_chg_20")),
            pct_chg_60=cls._optional_float(row.get("pct_chg_60")),
            pct_chg_120=cls._optional_float(row.get("pct_chg_120")),
            volatility_60=cls._optional_float(row.get("volatility_60")),
            max_drawdown_120=cls._optional_float(row.get("max_drawdown_120")),
        )

    @staticmethod
    def _category(text: str) -> str:
        value = str(text or "")
        if any(word in value for word in ["货币", "现金", "添利", "日利", "保证金", "收益快线"]):
            return "货币"
        if any(word in value for word in ["债", "国开", "政金", "可转", "城投", "信用"]):
            return "债券"
        if any(word in value for word in ["黄金", "商品", "豆粕", "能源", "石油", "有色", "稀有金属"]):
            return "商品"
        if any(word in value for word in ["港", "恒生", "H股", "纳指", "标普", "日经", "德国", "法国", "QDII"]):
            return "跨境"
        if any(word in value for word in ["半导体", "芯片", "医药", "新能源", "军工", "AI", "机器人", "消费", "证券", "银行", "酒", "传媒", "通信", "科创芯片", "创新药"]):
            return "行业主题"
        return "宽基指数"

    def _normalize_spot(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        data["代码"] = data["代码"].astype(str).str.zfill(6)
        data = data[data["代码"].str.match(r"^\d{6}$", na=False)]
        return data

    def _latest_trade_date_from_spot(self, df: pd.DataFrame) -> str:
        if "数据日期" not in df or df.empty:
            return self.settings.akshare.default_end_date or ""
        return self._date8(df["数据日期"].dropna().astype(str).iloc[0])

    def _latest_trade_date(self) -> str | None:
        row = self.conn.execute("SELECT MAX(trade_date) AS trade_date FROM etf_daily").fetchone()
        return row["trade_date"] if row and row["trade_date"] else None

    @staticmethod
    def _safe_call(label: str, func: Any, **kwargs: Any) -> pd.DataFrame | None:
        try:
            value = func(**kwargs)
            return value if isinstance(value, pd.DataFrame) else pd.DataFrame(value)
        except Exception:
            return None

    @staticmethod
    def _num(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            text = str(value).replace("%", "").strip()
            if text in {"", "-", "--", "nan"}:
                return 0.0
            number = float(text)
            if math.isnan(number) or math.isinf(number):
                return 0.0
            return number
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _optional_float(cls, value: Any) -> float | None:
        number = cls._num(value)
        return number if number or str(value).strip() in {"0", "0.0", "0.00"} else None

    @staticmethod
    def _symbol(value: Any) -> str:
        raw = str(value or "").strip().upper()
        if "." in raw:
            raw = raw.split(".")[0]
        return raw.zfill(6) if raw else ""

    @classmethod
    def _etf_code(cls, value: Any) -> str:
        symbol = cls._symbol(value)
        exchange = cls._exchange(symbol)
        return f"{symbol}.{exchange}"

    @staticmethod
    def _exchange(symbol: str) -> str:
        if symbol.startswith(("15", "16", "18")):
            return "SZ"
        return "SH"

    @staticmethod
    def _date8(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            return pd.to_datetime(text).strftime("%Y%m%d")
        except Exception:
            return text.replace("-", "")[:8]

    def _sleep(self) -> None:
        interval = max(float(self.settings.akshare.request_interval_seconds or 0), 0)
        if interval:
            time.sleep(interval)
