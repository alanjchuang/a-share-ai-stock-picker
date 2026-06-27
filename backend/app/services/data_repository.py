from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

import pandas as pd


class DataRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def latest_trade_date(self) -> str | None:
        row = self.conn.execute("SELECT MAX(trade_date) AS trade_date FROM stock_daily").fetchone()
        return row["trade_date"] if row and row["trade_date"] else None

    def list_indices(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT i.index_code, i.name, i.category, COUNT(m.ts_code) AS member_count,
                   v.pe, v.pb, v.pe_percentile, v.pb_percentile
            FROM index_info i
            LEFT JOIN index_members m ON i.index_code = m.index_code
            LEFT JOIN (
                SELECT v1.*
                FROM index_valuation v1
                JOIN (
                    SELECT index_code, MAX(trade_date) AS trade_date
                    FROM index_valuation
                    GROUP BY index_code
                ) latest ON latest.index_code = v1.index_code AND latest.trade_date = v1.trade_date
            ) v ON v.index_code = i.index_code
            GROUP BY i.index_code, i.name, i.category
            ORDER BY i.category, i.index_code
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_stocks(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT s.*, GROUP_CONCAT(ii.name) AS index_names
            FROM stocks s
            LEFT JOIN index_members im ON im.ts_code = s.ts_code
            LEFT JOIN index_info ii ON ii.index_code = im.index_code
            GROUP BY s.ts_code
            ORDER BY s.ts_code
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def read_factor_rows(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT s.ts_code, s.symbol, s.name, s.industry, s.market, s.list_date, s.is_st, s.is_paused,
                   GROUP_CONCAT(DISTINCT ii.name) AS index_names,
                   f.trade_date, f.payload_json
            FROM computed_factors f
            JOIN stocks s ON s.ts_code = f.ts_code
            LEFT JOIN index_members im ON im.ts_code = s.ts_code
            LEFT JOIN index_info ii ON ii.index_code = im.index_code
            GROUP BY s.ts_code
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            data = dict(row)
            data.pop("payload_json", None)
            data.update(payload)
            if isinstance(data.get("index_names"), str):
                data["index_names"] = [item for item in data["index_names"].split(",") if item]
            else:
                data["index_names"] = []
            result.append(data)
        return result

    def read_factor_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.read_factor_rows())

    def stock_daily_frame(self, ts_code: str, limit: int | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM stock_daily WHERE ts_code = ? ORDER BY trade_date ASC"
        rows = self.conn.execute(sql, (ts_code,)).fetchall()
        data = [dict(row) for row in rows]
        if limit:
            data = data[-limit:]
        return pd.DataFrame(data)

    def latest_fundamental(self, ts_code: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM fundamentals WHERE ts_code = ? ORDER BY trade_date DESC LIMIT 1",
            (ts_code,),
        ).fetchone()
        return dict(row) if row else {}

    def latest_capital(self, ts_code: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM capital_flows WHERE ts_code = ? ORDER BY trade_date DESC LIMIT 1",
            (ts_code,),
        ).fetchone()
        return dict(row) if row else {}

    def capital_window(self, ts_code: str, days: int = 20) -> dict[str, float]:
        rows = self.conn.execute(
            """
            SELECT north_inflow, main_net_inflow, margin_balance_delta
            FROM capital_flows
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (ts_code, days),
        ).fetchall()
        if not rows:
            return {"north_inflow_sum": 0, "main_net_inflow_sum": 0, "margin_balance_delta_sum": 0}
        return {
            "north_inflow_sum": sum(float(row["north_inflow"] or 0) for row in rows),
            "main_net_inflow_sum": sum(float(row["main_net_inflow"] or 0) for row in rows),
            "margin_balance_delta_sum": sum(float(row["margin_balance_delta"] or 0) for row in rows),
        }

    def recent_news(self, ts_code: str, days: int = 15) -> list[dict[str, Any]]:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        rows = self.conn.execute(
            """
            SELECT * FROM stock_news
            WHERE ts_code = ? AND publish_time >= ?
            ORDER BY publish_time DESC
            """,
            (ts_code, since),
        ).fetchall()
        return [dict(row) for row in rows]

    def index_members(self, index_codes: list[str]) -> set[str]:
        if not index_codes:
            return set()
        placeholders = ",".join("?" for _ in index_codes)
        rows = self.conn.execute(
            f"SELECT DISTINCT ts_code FROM index_members WHERE index_code IN ({placeholders})",
            index_codes,
        ).fetchall()
        return {row["ts_code"] for row in rows}

    def eligible_indices_by_valuation(
        self,
        index_codes: list[str],
        max_pe_percentile: float | None,
        max_pb_percentile: float | None,
    ) -> list[str]:
        if not index_codes and max_pe_percentile is None and max_pb_percentile is None:
            return []
        params: list[Any] = []
        where: list[str] = []
        if index_codes:
            where.append("v.index_code IN (" + ",".join("?" for _ in index_codes) + ")")
            params.extend(index_codes)
        if max_pe_percentile is not None:
            where.append("v.pe_percentile <= ?")
            params.append(max_pe_percentile)
        if max_pb_percentile is not None:
            where.append("v.pb_percentile <= ?")
            params.append(max_pb_percentile)
        rows = self.conn.execute(
            f"""
            SELECT v.index_code
            FROM index_valuation v
            JOIN (
                SELECT index_code, MAX(trade_date) AS trade_date
                FROM index_valuation
                GROUP BY index_code
            ) latest ON latest.index_code = v.index_code AND latest.trade_date = v.trade_date
            WHERE {" AND ".join(where) if where else "1=1"}
            """,
            params,
        ).fetchall()
        return [row["index_code"] for row in rows]

    def top_momentum_indices(self, pool: list[str], top_n: int) -> list[str]:
        params: list[Any] = []
        where = ""
        if pool:
            where = "WHERE d.index_code IN (" + ",".join("?" for _ in pool) + ")"
            params.extend(pool)
        rows = self.conn.execute(
            f"""
            SELECT d.index_code, d.momentum_20
            FROM index_daily d
            JOIN (
                SELECT index_code, MAX(trade_date) AS trade_date
                FROM index_daily
                GROUP BY index_code
            ) latest ON latest.index_code = d.index_code AND latest.trade_date = d.trade_date
            {where}
            ORDER BY d.momentum_20 DESC
            LIMIT ?
            """,
            [*params, top_n],
        ).fetchall()
        return [row["index_code"] for row in rows]

    def relative_return(self, ts_code: str, index_codes: list[str], days: int) -> float | None:
        stock_rows = self.conn.execute(
            "SELECT close FROM stock_daily WHERE ts_code = ? ORDER BY trade_date DESC LIMIT ?",
            (ts_code, days + 1),
        ).fetchall()
        if len(stock_rows) < 2:
            return None
        latest = float(stock_rows[0]["close"])
        base = float(stock_rows[-1]["close"])
        stock_return = (latest - base) / base * 100 if base else 0

        index_returns: list[float] = []
        for index_code in index_codes:
            rows = self.conn.execute(
                "SELECT close FROM index_daily WHERE index_code = ? ORDER BY trade_date DESC LIMIT ?",
                (index_code, days + 1),
            ).fetchall()
            if len(rows) >= 2:
                idx_latest = float(rows[0]["close"])
                idx_base = float(rows[-1]["close"])
                if idx_base:
                    index_returns.append((idx_latest - idx_base) / idx_base * 100)
        if not index_returns:
            return None
        return stock_return - sum(index_returns) / len(index_returns)

    def save_factor_payload(self, ts_code: str, trade_date: str, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO computed_factors(ts_code, trade_date, payload_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (ts_code, trade_date, json.dumps(payload, ensure_ascii=False)),
        )
