from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.models.schemas import (
    CapitalConditions,
    FundamentalConditions,
    OneClickRecommendRequest,
    OneClickRecommendResponse,
    RangeFilter,
    ScreeningRequest,
    SentimentConditions,
    StockRecommendationItem,
    TechnicalConditions,
    WebSearchRequest,
    WeightOptions,
)
from app.services.llm_client import LlmClient
from app.services.screener_service import ScreenerService
from app.services.web_search_service import WebSearchService


class RecommendationService:
    """一键研究推荐：融合本地因子、舆情和可选联网资料，输出观察建议。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.screener = ScreenerService(conn)
        self.llm = LlmClient()
        self.search = WebSearchService()

    def one_click(self, payload: OneClickRecommendRequest) -> OneClickRecommendResponse:
        request = self._screening_request(payload)
        screening = self.screener.run(request)
        candidates = screening.rows[: max(payload.limit * 3, payload.limit)]
        search_context = self._search_context(payload, candidates) if payload.include_search else []
        try:
            return self._llm_recommend(payload, candidates, search_context)
        except Exception:
            return self._fallback_recommend(payload, candidates, search_context)

    def _screening_request(self, payload: OneClickRecommendRequest) -> ScreeningRequest:
        themes = [theme.strip() for theme in payload.focus_themes if theme.strip()]
        sentiment_keywords = themes[:]
        if payload.risk_preference == "conservative":
            return ScreeningRequest(
                fundamental=FundamentalConditions(
                    pe_ttm=RangeFilter(max=35),
                    pb=RangeFilter(max=5),
                    roe=RangeFilter(min=8),
                ),
                sentiment=SentimentConditions(days=7, min_avg_score=50, whitelist_keywords=sentiment_keywords),
                weights=WeightOptions(fundamental=45, technical=20, capital=20, sentiment=15),
                limit=max(payload.limit * 4, 40),
            )
        if payload.risk_preference == "aggressive":
            return ScreeningRequest(
                fundamental=FundamentalConditions(revenue_yoy=RangeFilter(min=8)),
                technical=TechnicalConditions(above_ma=[20], pct_chg_n=RangeFilter(min=0), pct_chg_days=20),
                capital=CapitalConditions(main_net_inflow_min=0),
                sentiment=SentimentConditions(days=7, min_avg_score=55, whitelist_keywords=sentiment_keywords),
                weights=WeightOptions(fundamental=25, technical=35, capital=20, sentiment=20),
                limit=max(payload.limit * 4, 40),
            )
        return ScreeningRequest(
            fundamental=FundamentalConditions(roe=RangeFilter(min=6)),
            sentiment=SentimentConditions(days=7, min_avg_score=50, whitelist_keywords=sentiment_keywords),
            weights=WeightOptions(fundamental=35, technical=30, capital=20, sentiment=15),
            limit=max(payload.limit * 4, 40),
        )

    def _llm_recommend(
        self,
        payload: OneClickRecommendRequest,
        candidates: list[Any],
        search_context: list[dict[str, object]],
    ) -> OneClickRecommendResponse:
        candidate_json = json.dumps([self._candidate_snapshot(row) for row in candidates[:20]], ensure_ascii=False)
        prompt = f"""
你是A股多因子研究助手。请只输出JSON，不要输出Markdown。
边界：这是公开数据研究参考，不构成投资建议；只给观察动作、风险点和复盘重点，不给实盘下单指令。

输出字段：
market_view: 一句话市场观察
strategy: 本次推荐逻辑
risk_notes: 字符串数组
recommendations: 数组，每项包含 ts_code,name,action,reason,risk,confidence

风险偏好：{payload.risk_preference}
关注主题：{payload.focus_themes}
候选股因子：
{candidate_json}
联网资料：
{json.dumps(search_context, ensure_ascii=False)}
"""
        raw = self.llm.chat_json("你是A股一键研究推荐 Agent。", prompt)
        return OneClickRecommendResponse(
            market_view=str(raw.get("market_view") or "已基于多因子候选池完成研究推荐。"),
            strategy=str(raw.get("strategy") or "综合AI评分、资金、技术和舆情进行排序。"),
            risk_preference=payload.risk_preference,
            recommendations=self._items_from_llm(raw.get("recommendations", []), candidates, payload.limit),
            risk_notes=[str(item) for item in raw.get("risk_notes", [])][:8],
            search_context=search_context,
        )

    def _fallback_recommend(
        self,
        payload: OneClickRecommendRequest,
        candidates: list[Any],
        search_context: list[dict[str, object]],
    ) -> OneClickRecommendResponse:
        selected = candidates[: payload.limit]
        items = [
            StockRecommendationItem(
                ts_code=row.ts_code,
                name=row.name,
                industry=row.industry,
                rating=row.rating,
                ai_score=round(row.ai_score, 2),
                action=self._action_for(row, payload.risk_preference),
                reason=(
                    f"AI评分{row.ai_score:.1f}，基本面{row.fundamental_score:.1f}，"
                    f"技术{row.technical_score:.1f}，资金{row.capital_score:.1f}，舆情{row.sentiment_score:.0f}。"
                ),
                risk=self._risk_for(row),
                confidence=round(min(95, max(45, row.ai_score)), 1),
                source="fallback",
                stock=row,
            )
            for row in selected
        ]
        return OneClickRecommendResponse(
            market_view=f"规则引擎从当前因子池中筛出 {len(items)} 只研究候选，按综合AI评分和风险偏好排序。",
            strategy=self._strategy_text(payload.risk_preference),
            risk_preference=payload.risk_preference,
            recommendations=items,
            risk_notes=[
                "公开行情、财务与舆情数据可能延迟，需结合公告原文复核。",
                "一键推荐只用于缩小研究范围，不代表买卖建议。",
                "若同一行业候选过多，需要控制组合暴露并等待确认信号。",
            ],
            search_context=search_context,
        )

    def _search_context(self, payload: OneClickRecommendRequest, candidates: list[Any]) -> list[dict[str, object]]:
        if not self.search.available:
            return []
        names = "、".join(row.name for row in candidates[:8])
        themes = "、".join(payload.focus_themes)
        query = f"A股 今日市场 行业政策 资金流 财报 舆情 {themes} 候选股 {names}".strip()
        try:
            response = self.search.search(WebSearchRequest(query=query, count=8, search_type="web"))
            return WebSearchService.compact_context(response, limit=8)
        except Exception:
            return []

    def _items_from_llm(self, raw_items: Any, candidates: list[Any], limit: int) -> list[StockRecommendationItem]:
        candidate_map = {row.ts_code: row for row in candidates}
        items: list[StockRecommendationItem] = []
        if isinstance(raw_items, list):
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                ts_code = str(raw.get("ts_code") or "")
                row = candidate_map.get(ts_code)
                if row is None:
                    continue
                items.append(
                    StockRecommendationItem(
                        ts_code=row.ts_code,
                        name=row.name,
                        industry=row.industry,
                        rating=row.rating,
                        ai_score=round(row.ai_score, 2),
                        action=str(raw.get("action") or "纳入观察"),
                        reason=str(raw.get("reason") or "多因子综合靠前"),
                        risk=str(raw.get("risk") or self._risk_for(row)),
                        confidence=round(float(raw.get("confidence") or row.ai_score), 1),
                        source="llm",
                        stock=row,
                    )
                )
                if len(items) >= limit:
                    break
        if items:
            return items
        return self._fallback_recommend(OneClickRecommendRequest(limit=limit), candidates, []).recommendations

    @staticmethod
    def _candidate_snapshot(row: Any) -> dict[str, object]:
        return {
            "ts_code": row.ts_code,
            "name": row.name,
            "industry": row.industry,
            "rating": row.rating,
            "ai_score": row.ai_score,
            "pe_ttm": row.pe_ttm,
            "pb": row.pb,
            "roe": row.roe,
            "pct_chg": row.pct_chg,
            "main_net_inflow": row.main_net_inflow,
            "sentiment_score": row.sentiment_score,
            "sentiment_label": row.sentiment_label,
        }

    @staticmethod
    def _action_for(row: Any, risk_preference: str) -> str:
        if row.sentiment_score < 45:
            return "风险复核"
        if risk_preference == "conservative" and row.rating in {"A", "B"}:
            return "重点观察"
        if risk_preference == "aggressive" and row.technical_score >= 60:
            return "等待技术确认"
        return "纳入观察"

    @staticmethod
    def _risk_for(row: Any) -> str:
        risks: list[str] = []
        if row.sentiment_score < 50:
            risks.append("舆情偏弱")
        if row.pe_ttm and row.pe_ttm > 60:
            risks.append("估值偏高")
        if row.pct_chg and abs(row.pct_chg) > 7:
            risks.append("短期波动较大")
        return "；".join(risks) or "需继续跟踪公告、资金流和技术位置"

    @staticmethod
    def _strategy_text(risk_preference: str) -> str:
        if risk_preference == "conservative":
            return "偏稳健：优先ROE、估值和舆情稳定性。"
        if risk_preference == "aggressive":
            return "偏进攻：优先成长、技术趋势、资金流和舆情催化。"
        return "均衡：综合基本面、技术、资金和舆情四维度。"
