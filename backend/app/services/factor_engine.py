from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd

from app.core.config import WeightConfig, load_settings
from app.services.data_repository import DataRepository
from app.utils.indicators import add_technical_indicators, clamp, normalize_series, safe_float


class FactorEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = DataRepository(conn)

    def calculate_all(self, force: bool = False) -> list[dict[str, Any]]:
        latest_trade_date = self.repo.latest_trade_date()
        cached_count = self.conn.execute("SELECT COUNT(*) FROM computed_factors").fetchone()[0]
        stock_count = self.conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        if not force and cached_count >= stock_count and cached_count > 0:
            return self.repo.read_factor_rows()

        base_rows: list[dict[str, Any]] = []
        for stock in self.repo.list_stocks():
            payload = self._calculate_single(stock)
            payload["ts_code"] = stock["ts_code"]
            payload["symbol"] = stock["symbol"]
            payload["name"] = stock["name"]
            payload["industry"] = stock.get("industry")
            payload["index_names"] = [item for item in (stock.get("index_names") or "").split(",") if item]
            base_rows.append(payload)

        scored = self._score_rows(base_rows, load_settings().weights)
        for row in scored:
            ts_code = str(row["ts_code"])
            trade_date = str(row.get("trade_date") or latest_trade_date or "")
            payload = {key: value for key, value in row.items() if key not in {"ts_code", "symbol", "name", "industry", "index_names"}}
            self.repo.save_factor_payload(ts_code, trade_date, payload)
        self.conn.commit()
        return self.repo.read_factor_rows()

    def factor_rows(self) -> list[dict[str, Any]]:
        rows = self.repo.read_factor_rows()
        stock_count = self.conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        if len(rows) < stock_count:
            rows = self.calculate_all(force=True)
        return rows

    def _calculate_single(self, stock: dict[str, Any]) -> dict[str, Any]:
        ts_code = stock["ts_code"]
        daily = self.repo.stock_daily_frame(ts_code)
        tech = add_technical_indicators(daily)
        latest = tech.iloc[-1].to_dict() if not tech.empty else {}
        previous = tech.iloc[-2].to_dict() if len(tech) > 1 else latest
        fundamental = self.repo.latest_fundamental(ts_code)
        capital = self.repo.latest_capital(ts_code)
        capital_window = self.repo.capital_window(ts_code, 20)
        news = self.repo.recent_news(ts_code, 15)

        avg_sentiment_7 = self._avg_sentiment([item for item in news if self._within_days(item["publish_time"], 7)])
        avg_sentiment_15 = self._avg_sentiment(news)
        negative_count = sum(1 for item in news if float(item.get("sentiment_score") or 50) < 40)
        negative_ratio = negative_count / len(news) if news else 0
        label = self._sentiment_label(avg_sentiment_7)

        # 筹码获利比例用“最新收盘高于近60日收盘价的比例”近似，适合本地轻量分析。
        close = safe_float(latest.get("close"))
        profit_ratio = 50.0
        if not tech.empty and close:
            recent_closes = tech.tail(60)["close"].astype(float)
            profit_ratio = float((recent_closes < close).mean() * 100)

        limit_up_days_60 = int(tech.tail(60)["limit_up"].sum()) if not tech.empty and "limit_up" in tech else 0

        return {
            "trade_date": str(latest.get("trade_date") or ""),
            "close": safe_float(latest.get("close")),
            "pct_chg": safe_float(latest.get("pct_chg")),
            "ma5": safe_float(latest.get("ma5")),
            "ma10": safe_float(latest.get("ma10")),
            "ma20": safe_float(latest.get("ma20")),
            "ma60": safe_float(latest.get("ma60")),
            "ma120": safe_float(latest.get("ma120")),
            "macd": safe_float(latest.get("macd")),
            "macd_dif": safe_float(latest.get("macd_dif")),
            "macd_dea": safe_float(latest.get("macd_dea")),
            "macd_cross": str(latest.get("macd_cross") or ""),
            "kdj_k": safe_float(latest.get("kdj_k")),
            "kdj_d": safe_float(latest.get("kdj_d")),
            "kdj_j": safe_float(latest.get("kdj_j")),
            "kdj_cross": str(latest.get("kdj_cross") or ""),
            "rsi": safe_float(latest.get("rsi"), 50),
            "boll_upper": safe_float(latest.get("boll_upper")),
            "boll_mid": safe_float(latest.get("boll_mid")),
            "boll_lower": safe_float(latest.get("boll_lower")),
            "atr": safe_float(latest.get("atr")),
            "turnover_rate": safe_float(latest.get("turnover_rate")),
            "volume_ratio": safe_float(latest.get("volume_ratio") or latest.get("volume_ratio_calc")),
            "amplitude": safe_float(latest.get("amplitude")),
            "pct_chg_5": safe_float(latest.get("pct_chg_5")),
            "pct_chg_20": safe_float(latest.get("pct_chg_20")),
            "pct_chg_60": safe_float(latest.get("pct_chg_60")),
            "pct_chg_120": safe_float(latest.get("pct_chg_120")),
            "chip_profit_ratio": profit_ratio,
            "limit_up_days_60": limit_up_days_60,
            "breakout_20": bool(latest.get("breakout_20")),
            "pe_ttm": safe_float(fundamental.get("pe_ttm"), 0),
            "pb": safe_float(fundamental.get("pb"), 0),
            "peg": safe_float(fundamental.get("peg"), 0),
            "roe": safe_float(fundamental.get("roe"), 0),
            "gross_margin": safe_float(fundamental.get("gross_margin"), 0),
            "netprofit_margin": safe_float(fundamental.get("netprofit_margin"), 0),
            "revenue_yoy": safe_float(fundamental.get("revenue_yoy"), 0),
            "deduct_profit_yoy": safe_float(fundamental.get("deduct_profit_yoy"), 0),
            "debt_to_assets": safe_float(fundamental.get("debt_to_assets"), 0),
            "ocf": safe_float(fundamental.get("ocf"), 0),
            "dividend_yield": safe_float(fundamental.get("dividend_yield"), 0),
            "total_mv": safe_float(fundamental.get("total_mv"), 0),
            "circ_mv": safe_float(fundamental.get("circ_mv"), 0),
            "goodwill_ratio": safe_float(fundamental.get("goodwill_ratio"), 0),
            "north_inflow": safe_float(capital.get("north_inflow"), 0),
            "main_net_inflow": safe_float(capital.get("main_net_inflow"), 0),
            "margin_balance_delta": safe_float(capital.get("margin_balance_delta"), 0),
            "institution_holding_ratio": safe_float(capital.get("institution_holding_ratio"), 0),
            "top_list_score": safe_float(capital.get("top_list_score"), 0),
            **capital_window,
            "sentiment_score": avg_sentiment_7,
            "sentiment_score_15": avg_sentiment_15,
            "sentiment_label": label,
            "negative_news_ratio": negative_ratio,
            "recent_news_text": " ".join(f"{item['title']} {item['content']} {item.get('keywords') or ''}" for item in news),
            "prev_macd_dif": safe_float(previous.get("macd_dif")),
            "prev_macd_dea": safe_float(previous.get("macd_dea")),
        }

    @staticmethod
    def _within_days(publish_time: str, days: int) -> bool:
        try:
            dt = pd.to_datetime(publish_time)
            return (pd.Timestamp.now() - dt).days <= days
        except Exception:
            return True

    @staticmethod
    def _avg_sentiment(news: list[dict[str, Any]]) -> float:
        if not news:
            return 50.0
        return round(sum(float(item.get("sentiment_score") or 50) for item in news) / len(news), 2)

    @staticmethod
    def _sentiment_label(score: float) -> str:
        if score >= 80:
            return "重大利好"
        if score >= 60:
            return "普通利好"
        if score >= 40:
            return "中性"
        if score >= 20:
            return "普通利空"
        return "重大利空"

    @staticmethod
    def _score_rows(rows: list[dict[str, Any]], weights: WeightConfig) -> list[dict[str, Any]]:
        if not rows:
            return []
        df = pd.DataFrame(rows)
        score_columns: dict[str, pd.Series] = {}

        score_columns["pe_score"] = normalize_series(df["pe_ttm"], inverse=True)
        score_columns["pb_score"] = normalize_series(df["pb"], inverse=True)
        score_columns["peg_score"] = normalize_series(df["peg"], inverse=True)
        score_columns["roe_score"] = normalize_series(df["roe"])
        score_columns["margin_score"] = (normalize_series(df["gross_margin"]) * 0.5 + normalize_series(df["netprofit_margin"]) * 0.5)
        score_columns["growth_score"] = (normalize_series(df["revenue_yoy"]) * 0.45 + normalize_series(df["deduct_profit_yoy"]) * 0.55)
        score_columns["debt_score"] = normalize_series(df["debt_to_assets"], inverse=True)
        score_columns["cash_dividend_score"] = normalize_series(df["ocf"]) * 0.65 + normalize_series(df["dividend_yield"]) * 0.35
        score_columns["goodwill_score"] = normalize_series(df["goodwill_ratio"], inverse=True)

        df["fundamental_score"] = (
            score_columns["pe_score"] * 0.14
            + score_columns["pb_score"] * 0.10
            + score_columns["peg_score"] * 0.08
            + score_columns["roe_score"] * 0.18
            + score_columns["margin_score"] * 0.14
            + score_columns["growth_score"] * 0.16
            + score_columns["debt_score"] * 0.08
            + score_columns["cash_dividend_score"] * 0.08
            + score_columns["goodwill_score"] * 0.04
        )

        ma_strength = (
            (df["close"] > df["ma5"]).astype(float)
            + (df["close"] > df["ma10"]).astype(float)
            + (df["close"] > df["ma20"]).astype(float)
            + (df["close"] > df["ma60"]).astype(float)
            + (df["close"] > df["ma120"]).astype(float)
        ) / 5 * 100
        rsi_health = 100 - (pd.to_numeric(df["rsi"], errors="coerce") - 55).abs().clip(0, 55) / 55 * 100
        df["technical_score"] = (
            ma_strength * 0.22
            + normalize_series(df["pct_chg_20"]) * 0.18
            + normalize_series(df["pct_chg_60"]) * 0.16
            + normalize_series(df["macd"]) * 0.12
            + rsi_health.fillna(50) * 0.12
            + normalize_series(df["turnover_rate"]) * 0.08
            + normalize_series(df["volume_ratio"]) * 0.06
            + normalize_series(df["chip_profit_ratio"]) * 0.04
            + normalize_series(df["limit_up_days_60"]) * 0.02
        )

        df["capital_score"] = (
            normalize_series(df["north_inflow_sum"]) * 0.25
            + normalize_series(df["main_net_inflow_sum"]) * 0.35
            + normalize_series(df["margin_balance_delta_sum"]) * 0.15
            + normalize_series(df["institution_holding_ratio"]) * 0.15
            + normalize_series(df["top_list_score"]) * 0.10
        )
        df["sentiment_factor_score"] = pd.to_numeric(df["sentiment_score"], errors="coerce").fillna(50).clip(0, 100)

        total_weight = max(1.0, weights.fundamental + weights.technical + weights.capital + weights.sentiment)
        df["ai_score"] = (
            df["fundamental_score"] * weights.fundamental
            + df["technical_score"] * weights.technical
            + df["capital_score"] * weights.capital
            + df["sentiment_factor_score"] * weights.sentiment
        ) / total_weight

        df["rating"] = pd.cut(
            df["ai_score"],
            bins=[-1, 45, 65, 80, 101],
            labels=["D", "C", "B", "A"],
        ).astype(str)

        numeric_score_fields = ["fundamental_score", "technical_score", "capital_score", "sentiment_factor_score", "ai_score"]
        for field in numeric_score_fields:
            df[field] = df[field].apply(lambda value: round(clamp(value), 2))

        return df.to_dict(orient="records")
