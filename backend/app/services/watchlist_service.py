from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from app.models.schemas import (
    WatchlistAskRequest,
    WatchlistAskResponse,
    WatchlistGroupCreate,
    WatchlistGroupOut,
    WatchlistGroupUpdate,
    WatchlistItemCreate,
    WatchlistItemOut,
    WatchlistItemUpdate,
    WatchlistNoteCreate,
    WatchlistNoteOut,
    WebSearchRequest,
)
from app.services.llm_client import LlmClient
from app.services.screener_service import ScreenerService
from app.services.web_search_service import WebSearchService


DEFAULT_GROUPS = [
    ("观察池", "还在验证逻辑、等待触发条件的标的", "blue", 10),
    ("重点跟踪", "基本面、资金或舆情较强，需要高频复盘的标的", "green", 20),
    ("风险观察", "出现负面舆情、破位或逻辑弱化，需要谨慎跟踪的标的", "red", 30),
]


class WatchlistService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.llm = LlmClient()
        self.search = WebSearchService()

    def list_groups(self) -> list[WatchlistGroupOut]:
        self._ensure_default_groups()
        rows = self.conn.execute(
            """
            SELECT g.*, COUNT(i.id) AS item_count
            FROM watchlist_groups g
            LEFT JOIN watchlist_items i ON i.group_id = g.id AND i.status != 'closed'
            GROUP BY g.id
            ORDER BY g.sort_order ASC, g.id ASC
            """
        ).fetchall()
        return [WatchlistGroupOut.model_validate(dict(row)) for row in rows]

    def create_group(self, payload: WatchlistGroupCreate) -> WatchlistGroupOut:
        cursor = self.conn.execute(
            """
            INSERT INTO watchlist_groups(name, description, color, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (payload.name, payload.description, payload.color, payload.sort_order),
        )
        self.conn.commit()
        return self._group(cursor.lastrowid)

    def update_group(self, group_id: int, payload: WatchlistGroupUpdate) -> WatchlistGroupOut:
        current = self._group(group_id)
        self.conn.execute(
            """
            UPDATE watchlist_groups
            SET name = ?, description = ?, color = ?, sort_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.name if payload.name is not None else current.name,
                payload.description if payload.description is not None else current.description,
                payload.color if payload.color is not None else current.color,
                payload.sort_order if payload.sort_order is not None else current.sort_order,
                self._now(),
                group_id,
            ),
        )
        self.conn.commit()
        return self._group(group_id)

    def list_items(self, group_id: int | None = None, status: str | None = None) -> list[WatchlistItemOut]:
        self._ensure_default_groups()
        sql = """
            SELECT i.*, g.name AS group_name
            FROM watchlist_items i
            JOIN watchlist_groups g ON g.id = i.group_id
            WHERE 1 = 1
        """
        params: list[Any] = []
        if group_id is not None:
            sql += " AND i.group_id = ?"
            params.append(group_id)
        if status:
            sql += " AND i.status = ?"
            params.append(status)
        sql += " ORDER BY i.priority DESC, i.updated_at DESC"
        rows = self.conn.execute(sql, params).fetchall()
        factor_map = self._factor_map()
        return [self._item_out(dict(row), factor_map) for row in rows]

    def create_item(self, payload: WatchlistItemCreate) -> WatchlistItemOut:
        group_id = payload.group_id or self._group_id_by_name(payload.group_name or "观察池")
        if not self.conn.execute("SELECT 1 FROM stocks WHERE ts_code = ?", (payload.ts_code,)).fetchone():
            raise ValueError("股票不存在，无法加入自选")
        next_review = payload.next_review_date or self._review_date(payload.review_interval_days)
        cursor = self.conn.execute(
            """
            INSERT INTO watchlist_items
            (group_id, ts_code, reason, tags, priority, risk_level, status, cost_price,
             target_price, stop_loss_price, review_interval_days, next_review_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_id, ts_code) DO UPDATE SET
                reason = excluded.reason,
                tags = excluded.tags,
                priority = excluded.priority,
                risk_level = excluded.risk_level,
                status = excluded.status,
                cost_price = excluded.cost_price,
                target_price = excluded.target_price,
                stop_loss_price = excluded.stop_loss_price,
                review_interval_days = excluded.review_interval_days,
                next_review_date = excluded.next_review_date,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                group_id,
                payload.ts_code,
                payload.reason,
                ",".join(payload.tags),
                payload.priority,
                payload.risk_level,
                payload.status,
                payload.cost_price,
                payload.target_price,
                payload.stop_loss_price,
                payload.review_interval_days,
                next_review,
            ),
        )
        self.conn.commit()
        item_id = cursor.lastrowid or self._item_id(group_id, payload.ts_code)
        return self.get_item(item_id)

    def get_item(self, item_id: int) -> WatchlistItemOut:
        row = self.conn.execute(
            """
            SELECT i.*, g.name AS group_name
            FROM watchlist_items i
            JOIN watchlist_groups g ON g.id = i.group_id
            WHERE i.id = ?
            """,
            (item_id,),
        ).fetchone()
        if row is None:
            raise ValueError("自选股不存在")
        return self._item_out(dict(row), self._factor_map())

    def update_item(self, item_id: int, payload: WatchlistItemUpdate) -> WatchlistItemOut:
        current = self.get_item(item_id)
        review_interval = payload.review_interval_days if payload.review_interval_days is not None else current.review_interval_days
        next_review = payload.next_review_date if payload.next_review_date is not None else current.next_review_date
        self.conn.execute(
            """
            UPDATE watchlist_items
            SET group_id = ?, reason = ?, tags = ?, priority = ?, risk_level = ?, status = ?,
                cost_price = ?, target_price = ?, stop_loss_price = ?, review_interval_days = ?,
                next_review_date = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.group_id if payload.group_id is not None else current.group_id,
                payload.reason if payload.reason is not None else current.reason,
                ",".join(payload.tags) if payload.tags is not None else ",".join(current.tags),
                payload.priority if payload.priority is not None else current.priority,
                payload.risk_level if payload.risk_level is not None else current.risk_level,
                payload.status if payload.status is not None else current.status,
                payload.cost_price if payload.cost_price is not None else current.cost_price,
                payload.target_price if payload.target_price is not None else current.target_price,
                payload.stop_loss_price if payload.stop_loss_price is not None else current.stop_loss_price,
                review_interval,
                next_review,
                self._now(),
                item_id,
            ),
        )
        self.conn.commit()
        return self.get_item(item_id)

    def delete_item(self, item_id: int) -> dict[str, int]:
        cursor = self.conn.execute("DELETE FROM watchlist_items WHERE id = ?", (item_id,))
        self.conn.commit()
        return {"deleted": cursor.rowcount}

    def list_notes(self, item_id: int | None = None) -> list[WatchlistNoteOut]:
        sql = "SELECT * FROM watchlist_notes WHERE 1 = 1"
        params: list[Any] = []
        if item_id is not None:
            sql += " AND item_id = ?"
            params.append(item_id)
        sql += " ORDER BY created_at DESC LIMIT 200"
        rows = self.conn.execute(sql, params).fetchall()
        return [self._note_out(dict(row)) for row in rows]

    def create_note(self, payload: WatchlistNoteCreate) -> WatchlistNoteOut:
        cursor = self.conn.execute(
            """
            INSERT INTO watchlist_notes(item_id, note_type, content)
            VALUES (?, ?, ?)
            """,
            (payload.item_id, payload.note_type, payload.content),
        )
        self.conn.commit()
        return self._note(cursor.lastrowid)

    def ask(self, payload: WatchlistAskRequest) -> WatchlistAskResponse:
        items = self._scope_items(payload)
        snapshot = [self._snapshot_item(item) for item in items]
        search_context = self._search_context(payload.question, snapshot) if payload.include_search else []
        try:
            response = self._llm_answer(payload.question, snapshot, search_context)
        except Exception:
            response = self._fallback_answer(payload.question, snapshot)
        self._save_ai_note(payload, response)
        return response

    def _llm_answer(self, question: str, snapshot: list[dict[str, object]], search_context: list[dict[str, object]]) -> WatchlistAskResponse:
        prompt = f"""
你是A股自选股研究与复盘助手。请只输出JSON，不要输出Markdown。
输出字段：answer(中文总结), action_items(字符串数组), risk_notes(字符串数组), review_questions(字符串数组), focus_symbols(股票代码数组)。
边界：只能做公开数据统计、观察动作、复盘问题和风险提示，不构成投资建议，不给实盘下单指令。

用户问题：
{question}

自选股快照：
{json.dumps(snapshot, ensure_ascii=False)}

火山搜索资料：
{json.dumps(search_context, ensure_ascii=False)}
"""
        raw = self.llm.chat_json("你是A股自选股研究复盘助手。", prompt)
        return WatchlistAskResponse(
            answer=str(raw.get("answer") or "已完成自选股复盘。"),
            action_items=[str(item) for item in raw.get("action_items", [])][:8],
            risk_notes=[str(item) for item in raw.get("risk_notes", [])][:8],
            review_questions=[str(item) for item in raw.get("review_questions", [])][:8],
            focus_symbols=[str(item) for item in raw.get("focus_symbols", [])][:12],
            source="llm",
            snapshot=snapshot,
        )

    def _fallback_answer(self, question: str, snapshot: list[dict[str, object]]) -> WatchlistAskResponse:
        high_risk = [item for item in snapshot if item.get("risk_level") == "high" or float(item.get("sentiment_score") or 50) < 45]
        strong = sorted(snapshot, key=lambda item: float(item.get("ai_score") or 0), reverse=True)[:3]
        answer = f"已按规则完成自选池复盘：当前范围内共有 {len(snapshot)} 只股票，重点关注 {len(strong)} 只高评分标的，另有 {len(high_risk)} 只需要风险复核。"
        action_items = [
            "对高风险或舆情低于45分的标的做一次备注复盘，确认是否仍符合加入自选的原始理由。",
            "优先跟踪AI评分、资金分和舆情分同时靠前的标的，等待明确触发条件再行动。",
            "检查同一行业是否过度集中，避免自选池只暴露在单一赛道上。",
        ]
        if strong:
            action_items.insert(0, "重点观察：" + "、".join(f"{item['name']}({item['ts_code']})" for item in strong))
        risk_notes = [
            f"{item.get('name')}({item.get('ts_code')})：风险级别或舆情偏弱，需要复核新闻、资金流和技术位。"
            for item in high_risk[:5]
        ] or ["暂未发现显著高风险标记，但仍需关注公开数据延迟和突发公告。"]
        return WatchlistAskResponse(
            answer=answer,
            action_items=action_items,
            risk_notes=risk_notes,
            review_questions=[
                "这只股票当初加入自选的核心假设是否仍成立？",
                "最近的资金流和舆情变化是在强化逻辑，还是削弱逻辑？",
                "如果三天后重新评估，需要看到什么信号才继续保留？",
            ],
            focus_symbols=[str(item.get("ts_code")) for item in strong],
            source="fallback",
            snapshot=snapshot,
        )

    def _scope_items(self, payload: WatchlistAskRequest) -> list[WatchlistItemOut]:
        if payload.item_id is not None:
            return [self.get_item(payload.item_id)]
        return self.list_items(group_id=payload.group_id, status="active")

    def _snapshot_item(self, item: WatchlistItemOut) -> dict[str, object]:
        stock = item.stock
        return {
            "id": item.id,
            "group": item.group_name,
            "ts_code": item.ts_code,
            "name": stock.name if stock else item.ts_code,
            "industry": stock.industry if stock else None,
            "reason": item.reason,
            "tags": item.tags,
            "priority": item.priority,
            "risk_level": item.risk_level,
            "next_review_date": item.next_review_date,
            "close": stock.close if stock else None,
            "pct_chg": stock.pct_chg if stock else None,
            "pe_ttm": stock.pe_ttm if stock else None,
            "roe": stock.roe if stock else None,
            "main_net_inflow": stock.main_net_inflow if stock else None,
            "sentiment_score": stock.sentiment_score if stock else None,
            "sentiment_label": stock.sentiment_label if stock else None,
            "ai_score": stock.ai_score if stock else None,
            "rating": stock.rating if stock else None,
        }

    def _search_context(self, question: str, snapshot: list[dict[str, object]]) -> list[dict[str, object]]:
        if not self.search.available or not snapshot:
            return []
        names = "、".join(str(item.get("name")) for item in snapshot[:6])
        try:
            response = self.search.search(
                WebSearchRequest(
                    query=f"{question} A股 自选股 舆情 公告 资金 {names}",
                    count=5,
                    search_type="web",
                )
            )
            return WebSearchService.compact_context(response, limit=5)
        except Exception:
            return []

    def _save_ai_note(self, payload: WatchlistAskRequest, response: WatchlistAskResponse) -> None:
        self.conn.execute(
            """
            INSERT INTO watchlist_notes(item_id, note_type, content, ai_payload_json)
            VALUES (?, 'ai_review', ?, ?)
            """,
            (payload.item_id, response.answer, json.dumps(response.model_dump(mode="json"), ensure_ascii=False)),
        )
        self.conn.commit()

    def _factor_map(self) -> dict[str, Any]:
        rows = ScreenerService(self.conn).factor_engine.factor_rows()
        return {str(row["ts_code"]): row for row in rows}

    def _item_out(self, row: dict[str, Any], factor_map: dict[str, Any]) -> WatchlistItemOut:
        stock = None
        factor_row = factor_map.get(str(row["ts_code"]))
        if factor_row:
            stock = ScreenerService._to_stock_score(factor_row)
        return WatchlistItemOut(
            **{
                **row,
                "tags": [tag for tag in str(row.get("tags") or "").split(",") if tag],
                "stock": stock,
            }
        )

    def _ensure_default_groups(self) -> None:
        for name, description, color, sort_order in DEFAULT_GROUPS:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO watchlist_groups(name, description, color, sort_order)
                VALUES (?, ?, ?, ?)
                """,
                (name, description, color, sort_order),
            )
        self.conn.commit()

    def _group(self, group_id: int) -> WatchlistGroupOut:
        row = self.conn.execute(
            """
            SELECT g.*, COUNT(i.id) AS item_count
            FROM watchlist_groups g
            LEFT JOIN watchlist_items i ON i.group_id = g.id AND i.status != 'closed'
            WHERE g.id = ?
            GROUP BY g.id
            """,
            (group_id,),
        ).fetchone()
        if row is None:
            raise ValueError("自选分组不存在")
        return WatchlistGroupOut.model_validate(dict(row))

    def _group_id_by_name(self, name: str) -> int:
        self._ensure_default_groups()
        row = self.conn.execute("SELECT id FROM watchlist_groups WHERE name = ?", (name,)).fetchone()
        if row is None:
            return self.create_group(WatchlistGroupCreate(name=name)).id
        return int(row["id"])

    def _item_id(self, group_id: int, ts_code: str) -> int:
        row = self.conn.execute("SELECT id FROM watchlist_items WHERE group_id = ? AND ts_code = ?", (group_id, ts_code)).fetchone()
        if row is None:
            raise ValueError("自选股不存在")
        return int(row["id"])

    def _note(self, note_id: int) -> WatchlistNoteOut:
        row = self.conn.execute("SELECT * FROM watchlist_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise ValueError("复盘记录不存在")
        return self._note_out(dict(row))

    @staticmethod
    def _note_out(row: dict[str, Any]) -> WatchlistNoteOut:
        payload: dict[str, object] = {}
        if row.get("ai_payload_json"):
            try:
                payload = json.loads(str(row["ai_payload_json"]))
            except json.JSONDecodeError:
                payload = {}
        return WatchlistNoteOut(
            id=int(row["id"]),
            item_id=row.get("item_id"),
            note_type=str(row["note_type"]),
            content=str(row["content"]),
            ai_payload=payload,
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _review_date(days: int) -> str:
        return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
