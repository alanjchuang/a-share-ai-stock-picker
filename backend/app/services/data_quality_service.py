from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd

from app.utils.data_quality import sanitize_daily_frame


class DataQualityService:
    """清理真实行情和演示行情混用后的本地脏数据。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def clean_mixed_demo_rows(self) -> dict[str, Any]:
        stock_count = int(self.conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0] or 0)
        if stock_count < 500:
            return {"skipped": True, "reason": "小股票池视为演示模式，跳过真实库清理。", "deleted_daily": 0}

        deleted_dates = self._delete_thin_trade_dates()
        deleted_outliers = self._delete_price_outliers()
        deleted_total = deleted_dates + deleted_outliers
        if deleted_total:
            self.conn.execute("DELETE FROM computed_factors")
            self.conn.commit()
        return {
            "skipped": False,
            "deleted_daily": deleted_total,
            "deleted_thin_date_rows": deleted_dates,
            "deleted_price_outlier_rows": deleted_outliers,
            "factor_cache_cleared": bool(deleted_total),
        }

    def _delete_thin_trade_dates(self) -> int:
        rows = self.conn.execute(
            """
            SELECT trade_date, COUNT(DISTINCT ts_code) AS coverage
            FROM stock_daily
            GROUP BY trade_date
            """
        ).fetchall()
        if not rows:
            return 0
        max_coverage = max(int(row["coverage"] or 0) for row in rows)
        if max_coverage < 500:
            return 0
        # 真实全市场/批量历史日期通常覆盖几十到几千只股票；演示残留日期只有十几只。
        thin_dates = [row["trade_date"] for row in rows if int(row["coverage"] or 0) < 50]
        if not thin_dates:
            return 0
        placeholders = ",".join("?" for _ in thin_dates)
        cursor = self.conn.execute(f"DELETE FROM stock_daily WHERE trade_date IN ({placeholders})", thin_dates)
        self.conn.execute(f"DELETE FROM capital_flows WHERE trade_date IN ({placeholders})", thin_dates)
        self.conn.commit()
        return int(cursor.rowcount or 0)

    def _delete_price_outliers(self) -> int:
        rows = self.conn.execute("SELECT * FROM stock_daily ORDER BY ts_code, trade_date").fetchall()
        if not rows:
            return 0
        frame = pd.DataFrame([dict(row) for row in rows])
        delete_keys: list[tuple[str, str]] = []
        for ts_code, group in frame.groupby("ts_code"):
            if len(group) < 3:
                continue
            result = sanitize_daily_frame(group)
            delete_keys.extend((str(ts_code), trade_date) for trade_date in result.removed_trade_dates)
        if not delete_keys:
            return 0
        self.conn.executemany("DELETE FROM stock_daily WHERE ts_code = ? AND trade_date = ?", delete_keys)
        self.conn.executemany("DELETE FROM capital_flows WHERE ts_code = ? AND trade_date = ?", delete_keys)
        self.conn.commit()
        return len(delete_keys)
