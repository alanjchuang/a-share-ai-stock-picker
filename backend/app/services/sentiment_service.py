from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx

from app.core.config import load_settings
from app.models.schemas import NewsAnalyzeRequest, NewsSentiment
from app.services.llm_client import LlmClient, extract_json
from app.utils.number_parsing import coerce_score


POSITIVE_KEYWORDS = {
    "业绩大增": 20,
    "预增": 15,
    "政策扶持": 14,
    "大额订单": 18,
    "中标": 12,
    "资产重组": 20,
    "回购": 12,
    "国产替代": 12,
    "算力": 10,
    "突破": 10,
    "创新药": 10,
}

NEGATIVE_KEYWORDS = {
    "亏损": -18,
    "监管问询": -18,
    "问询函": -14,
    "减持": -16,
    "诉讼": -16,
    "立案": -24,
    "退市": -30,
    "暴雷": -28,
    "商誉减值": -16,
    "业绩下滑": -14,
}

SENTIMENT_SCORE_LABELS = {
    "重大利好": 90.0,
    "普通利好": 70.0,
    "利好": 70.0,
    "中性": 50.0,
    "普通利空": 30.0,
    "重大利空": 10.0,
    "利空": 30.0,
}


class SentimentService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def analyze(self, request: NewsAnalyzeRequest, persist: bool = False, prefer_llm: bool = True) -> NewsSentiment:
        settings = load_settings()
        if prefer_llm and settings.llm.provider != "heuristic" and settings.llm.api_base and settings.llm.api_key:
            try:
                result = self._llm_analyze(request)
            except Exception as exc:
                result = self._heuristic_analyze(request, reason=f"LLM调用失败，已回退关键词规则：{exc}")
        else:
            result = self._heuristic_analyze(request)

        if persist:
            self.conn.execute(
                """
                INSERT INTO stock_news(ts_code, title, content, source, publish_time, sentiment_score, sentiment_label, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.ts_code,
                    request.title,
                    request.content,
                    request.source,
                    request.publish_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    result.score,
                    result.label,
                    ",".join(result.keywords),
                ),
            )
            self.conn.commit()
        return result

    def batch_refresh_existing(self, limit: int = 200, cancel_check: Callable[[], None] | None = None) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT id, ts_code, title, content, source, publish_time
            FROM stock_news
            ORDER BY publish_time DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            if cancel_check:
                cancel_check()
            result = self.analyze(
                NewsAnalyzeRequest(
                    ts_code=row["ts_code"],
                    title=row["title"],
                    content=row["content"],
                    source=row["source"] or "database",
                    publish_time=row["publish_time"],
                ),
                persist=False,
            )
            self.conn.execute(
                "UPDATE stock_news SET sentiment_score = ?, sentiment_label = ?, keywords = ? WHERE id = ?",
                (result.score, result.label, ",".join(result.keywords), row["id"]),
            )
        self.conn.commit()
        return {"updated": len(rows)}

    def _heuristic_analyze(self, request: NewsAnalyzeRequest, reason: str = "关键词规则评分") -> NewsSentiment:
        text = f"{request.title}\n{request.content}"
        score = 50
        keywords: list[str] = []
        for keyword, weight in POSITIVE_KEYWORDS.items():
            if keyword in text:
                score += weight
                keywords.append(keyword)
        for keyword, weight in NEGATIVE_KEYWORDS.items():
            if keyword in text:
                score += weight
                keywords.append(keyword)

        # 财经新闻中“重大”语义会显著放大情绪方向。
        if "重大" in text and score > 50:
            score += 8
        if "重大" in text and score < 50:
            score -= 8
        score = max(0, min(100, score))
        return NewsSentiment(score=score, label=self._label(score), keywords=keywords, reason=reason)

    def _llm_analyze(self, request: NewsAnalyzeRequest) -> NewsSentiment:
        settings = load_settings()
        prompt = f"""
你是A股财经舆情分析模型。请只输出JSON，字段为score(0-100数字)、label(重大利好/普通利好/中性/普通利空/重大利空)、keywords(字符串数组)、reason(一句中文原因)。
评分规则：80-100重大利好；60-79普通利好；40-59中性；20-39普通利空；0-19重大利空。
股票：{request.ts_code}
标题：{request.title}
正文：{request.content}
"""
        raw = LlmClient(settings.llm).chat_json("你是A股财经舆情打分模型。", prompt)
        score = coerce_score(raw.get("score"), default=50, label_map=SENTIMENT_SCORE_LABELS)
        return NewsSentiment(
            score=score,
            label=str(raw.get("label") or self._label(score)),
            keywords=[str(item) for item in raw.get("keywords", [])],
            reason=str(raw.get("reason") or "LLM评分"),
        )

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        raw = extract_json(content)
        if not isinstance(raw, dict):
            raise ValueError("未解析到JSON对象")
        return raw

    @staticmethod
    def _label(score: float) -> str:
        if score >= 80:
            return "重大利好"
        if score >= 60:
            return "普通利好"
        if score >= 40:
            return "中性"
        if score >= 20:
            return "普通利空"
        return "重大利空"
