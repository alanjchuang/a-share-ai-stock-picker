from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from app.models.schemas import StrategyCreate, StrategyOut, StrategyUpdate
from app.services.screener_service import ScreenerService


class StrategyService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.screener = ScreenerService(conn)

    def list(self) -> list[StrategyOut]:
        rows = self.conn.execute("SELECT * FROM strategies ORDER BY updated_at DESC").fetchall()
        return [self._to_out(dict(row)) for row in rows]

    def create(self, payload: StrategyCreate) -> StrategyOut:
        stats = self._evaluate(payload.conditions)
        cursor = self.conn.execute(
            """
            INSERT INTO strategies
            (name, remark, conditions_json, result_count, avg_score, avg_pct_chg, schedule_enabled, schedule_cron)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.remark,
                json.dumps(payload.conditions.model_dump(mode="json"), ensure_ascii=False),
                stats["count"],
                stats["avg_score"],
                stats["avg_pct_chg"],
                1 if payload.schedule_enabled else 0,
                payload.schedule_cron,
            ),
        )
        self.conn.commit()
        return self.get(cursor.lastrowid)

    def get(self, strategy_id: int) -> StrategyOut:
        row = self.conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if row is None:
            raise ValueError("策略不存在")
        return self._to_out(dict(row))

    def update(self, strategy_id: int, payload: StrategyUpdate) -> StrategyOut:
        current = self.get(strategy_id)
        name = payload.name if payload.name is not None else current.name
        remark = payload.remark if payload.remark is not None else current.remark
        conditions = payload.conditions if payload.conditions is not None else current.conditions
        schedule_enabled = payload.schedule_enabled if payload.schedule_enabled is not None else current.schedule_enabled
        schedule_cron = payload.schedule_cron if payload.schedule_cron is not None else current.schedule_cron
        stats = self._evaluate(conditions)
        self.conn.execute(
            """
            UPDATE strategies
            SET name = ?, remark = ?, conditions_json = ?, result_count = ?, avg_score = ?,
                avg_pct_chg = ?, schedule_enabled = ?, schedule_cron = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                remark,
                json.dumps(conditions.model_dump(mode="json"), ensure_ascii=False),
                stats["count"],
                stats["avg_score"],
                stats["avg_pct_chg"],
                1 if schedule_enabled else 0,
                schedule_cron,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                strategy_id,
            ),
        )
        self.conn.commit()
        return self.get(strategy_id)

    def delete(self, strategy_id: int) -> dict[str, int]:
        cursor = self.conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
        self.conn.commit()
        return {"deleted": cursor.rowcount}

    def _evaluate(self, conditions: Any) -> dict[str, float]:
        result = self.screener.run(conditions)
        count = len(result.rows)
        avg_score = sum(row.ai_score for row in result.rows) / count if count else 0
        avg_pct_chg = sum(float(row.pct_chg or 0) for row in result.rows) / count if count else 0
        return {"count": count, "avg_score": round(avg_score, 2), "avg_pct_chg": round(avg_pct_chg, 2)}

    @staticmethod
    def _to_out(row: dict[str, Any]) -> StrategyOut:
        data = row.copy()
        data["conditions"] = json.loads(str(row["conditions_json"]))
        data["schedule_enabled"] = bool(row["schedule_enabled"])
        return StrategyOut.model_validate(data)
