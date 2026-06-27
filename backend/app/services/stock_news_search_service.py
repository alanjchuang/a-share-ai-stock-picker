from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.schemas import NewsAnalyzeRequest, WebSearchRequest
from app.services.data_repository import DataRepository
from app.services.sentiment_service import SentimentService
from app.services.web_search_service import WebSearchService, WebSearchItem


DEMO_SOURCES = {"", "demo", "seed", "mock"}


class StockNewsSearchService:
    """用火山搜索补齐单股详情页新闻和公告。

    页面读取本地缓存优先；当近15日只有demo/空数据时，才触发外部搜索，避免详情页反复请求。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.repo = DataRepository(conn)
        self.sentiment = SentimentService(conn)
        self.search = WebSearchService()

    def ensure_recent_news(self, ts_code: str, name: str, days: int = 15, min_real_news: int = 3) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        rows = self._recent_news_safely(ts_code, days, warnings)
        real_rows = [row for row in rows if not self.is_demo_source(row.get("source"))]
        if len(real_rows) >= min_real_news:
            return real_rows, []

        if not self.search.available:
            if not real_rows:
                warnings.append("火山搜索未配置，近15日新闻公告不会再展示演示数据；请在系统配置填写搜索API后刷新个股详情。")
            return real_rows, warnings

        try:
            searched_rows = self.search_latest(ts_code, name, days=days)
        except Exception as exc:
            warnings.append(f"火山搜索补齐近15日新闻公告失败：{exc}")
            return real_rows, warnings

        inserted = 0
        if searched_rows:
            try:
                inserted = self.persist_news(ts_code, searched_rows)
            except sqlite3.OperationalError as exc:
                if not self._is_locked(exc):
                    raise
                self.conn.rollback()
                warnings.append("火山搜索已返回真实新闻，但本地数据库正在写入，暂未缓存；稍后刷新会再次尝试写入。")

        refreshed = self._recent_news_safely(ts_code, days, warnings)
        refreshed_real = [row for row in refreshed if not self.is_demo_source(row.get("source"))]
        if inserted == 0 and not refreshed_real and not searched_rows:
            warnings.append("火山搜索暂未返回可匹配该股票的近15日新闻公告。")
        return (refreshed_real or searched_rows), warnings

    def refresh_from_search(self, ts_code: str, name: str, days: int = 15) -> int:
        return self.persist_news(ts_code, self.search_latest(ts_code, name, days=days))

    def search_latest(self, ts_code: str, name: str, days: int = 15) -> list[dict[str, Any]]:
        symbol = ts_code.split(".")[0]
        queries = [
            f"{name} {symbol} A股 近{days}日 公告 新闻",
            f"{name} {symbol} 业绩预告 减持 重组 问询 诉讼",
        ]
        response = self.search.search(
            WebSearchRequest(
                queries=queries,
                count=6,
                search_type="web_summary",
                need_summary=True,
                need_content=False,
            )
        )

        rows: list[dict[str, Any]] = []
        seen_titles: set[str] = set()
        for item in response.items:
            if item.type != "web":
                continue
            news = self._to_news(ts_code, name, symbol, item, days)
            if news is None or news["title"] in seen_titles:
                continue
            seen_titles.add(news["title"])
            sentiment = self.sentiment.analyze(
                NewsAnalyzeRequest(
                    ts_code=ts_code,
                    title=news["title"],
                    content=news["content"],
                    source=news["source"],
                    publish_time=news["publish_time"],
                ),
                persist=False,
                prefer_llm=False,
            )
            rows.append(
                {
                    "id": -len(rows) - 1,
                    "ts_code": ts_code,
                    "title": news["title"],
                    "content": news["content"],
                    "source": news["source"],
                    "publish_time": news["publish_time"],
                    "sentiment_score": sentiment.score,
                    "sentiment_label": sentiment.label,
                    "keywords": ",".join(sentiment.keywords),
                }
            )
        return rows

    def persist_news(self, ts_code: str, rows: list[dict[str, Any]]) -> int:
        inserted = 0
        for news in rows:
            if self._exists(ts_code, str(news["title"])):
                continue
            self.conn.execute(
                """
                INSERT INTO stock_news(ts_code, title, content, source, publish_time, sentiment_score, sentiment_label, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_code,
                    news["title"],
                    news["content"],
                    news["source"],
                    news["publish_time"],
                    news["sentiment_score"],
                    news["sentiment_label"],
                    news["keywords"],
                ),
            )
            inserted += 1
        if inserted:
            self.conn.commit()
        return inserted

    @classmethod
    def is_demo_source(cls, source: object) -> bool:
        value = str(source or "").strip().lower()
        return value in DEMO_SOURCES or value.startswith("demo")

    def _to_news(self, ts_code: str, name: str, symbol: str, item: WebSearchItem, days: int) -> dict[str, str] | None:
        title = " ".join((item.title or "").split())[:180]
        body = item.summary or item.snippet or item.content
        content = " ".join((body or "").split())
        if item.url:
            content = f"{content}\n原文链接：{item.url}".strip()
        if not title or not content:
            return None
        if not self._matches_stock(f"{title} {content}", name, symbol):
            return None

        publish_time = self._publish_time(item.publish_time)
        parsed_time = self._parse_time(publish_time)
        if parsed_time and parsed_time < datetime.now() - timedelta(days=days + 1):
            return None

        site = item.site_name or self._host(item.url) or "web"
        return {
            "title": title,
            "content": content[:2200],
            "source": f"volc-search/{site}"[:120],
            "publish_time": publish_time,
        }

    @staticmethod
    def _matches_stock(text: str, name: str, symbol: str) -> bool:
        compact = re.sub(r"\s+", "", text or "").lower()
        normalized_name = re.sub(r"^\*?st", "", name or "", flags=re.I).lower()
        return bool(normalized_name and normalized_name in compact) or bool(symbol and symbol in compact)

    @classmethod
    def _publish_time(cls, value: str | None) -> str:
        parsed = cls._parse_time(value or "")
        if parsed is None:
            parsed = datetime.now()
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _parse_time(value: str) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[: len(fmt)], fmt)
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
            return parsed
        except ValueError:
            return None

    def _exists(self, ts_code: str, title: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM stock_news WHERE ts_code = ? AND title = ? LIMIT 1",
            (ts_code, title),
        ).fetchone()
        return row is not None

    def _recent_news_safely(self, ts_code: str, days: int, warnings: list[str]) -> list[dict[str, Any]]:
        try:
            return self.repo.recent_news(ts_code, days)
        except sqlite3.OperationalError as exc:
            if not self._is_locked(exc):
                raise
            warnings.append("本地新闻缓存正在被后台任务写入，已跳过缓存读取并尝试使用火山搜索实时结果。")
            return []

    @staticmethod
    def _is_locked(exc: sqlite3.OperationalError) -> bool:
        return "locked" in str(exc).lower()

    @staticmethod
    def _host(url: str) -> str:
        match = re.match(r"^https?://([^/]+)", url or "")
        return match.group(1) if match else ""
