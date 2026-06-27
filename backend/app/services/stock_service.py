from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from app.models.schemas import FinancialSnapshot, KLinePoint, StockDetail, StockLlmAnalysisResponse, StockMarketItem, StockMarketResponse, StockNewsItem
from app.core.config import load_settings
from app.services.data_repository import DataRepository
from app.services.factor_engine import FactorEngine
from app.services.llm_client import LlmClient
from app.services.screener_service import ScreenerService
from app.services.stock_news_search_service import StockNewsSearchService
from app.utils.indicators import add_technical_indicators, safe_float
from app.utils.number_parsing import coerce_score


class StockService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = DataRepository(conn)
        self.factor_engine = FactorEngine(conn)

    def list_market(
        self,
        q: str = "",
        industry: str | None = None,
        rating: str | None = None,
        include_st: bool = False,
        include_paused: bool = False,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "ai_score",
        sort_order: str = "desc",
    ) -> StockMarketResponse:
        """读取本地因子缓存形成全市场行情表，不触发同步写库，避免浏览页面造成锁竞争。"""

        rows = self.factor_engine.factor_rows()
        industries = sorted({str(row.get("industry") or "未分类") for row in rows})
        keyword = q.strip().lower()
        filtered = [
            row
            for row in rows
            if self._market_row_matches(
                row,
                keyword=keyword,
                industry=industry,
                rating=rating,
                include_st=include_st,
                include_paused=include_paused,
            )
        ]

        sort_field = sort_by if sort_by in self._sortable_fields() else "ai_score"
        reverse = sort_order.lower() != "asc"
        filtered.sort(key=lambda row: self._sort_value(row, sort_field), reverse=reverse)

        safe_page_size = min(max(int(page_size or 50), 10), 200)
        safe_page = max(int(page or 1), 1)
        start = (safe_page - 1) * safe_page_size
        page_rows = filtered[start : start + safe_page_size]
        return StockMarketResponse(
            total=len(filtered),
            page=safe_page,
            page_size=safe_page_size,
            rows=[self._to_market_item(row) for row in page_rows],
            latest_trade_date=self.repo.latest_trade_date(),
            industries=industries,
            factor_universe_count=len(rows),
        )

    def detail(self, ts_code: str) -> StockDetail:
        rows = self.factor_engine.factor_rows()
        row = next((item for item in rows if item["ts_code"] == ts_code), None)
        if not row:
            raise ValueError("股票不存在或尚未计算因子")
        base = ScreenerService._to_stock_score(row)

        daily, data_warnings = self.repo.stock_daily_quality(ts_code, limit=120)
        tech = add_technical_indicators(daily)
        kline = [
            KLinePoint(
                trade_date=str(item["trade_date"]),
                open=self._float(item.get("open")),
                close=self._float(item.get("close")),
                low=self._float(item.get("low")),
                high=self._float(item.get("high")),
                volume=self._float(item.get("vol")),
                ma5=self._optional_float(item.get("ma5")),
                ma10=self._optional_float(item.get("ma10")),
                ma20=self._optional_float(item.get("ma20")),
                ma60=self._optional_float(item.get("ma60")),
            )
            for item in tech.to_dict(orient="records")
        ]

        financial_history = [
            FinancialSnapshot(
                report_date=str(item.get("trade_date") or ""),
                pe_ttm=self._optional_float(item.get("pe_ttm")),
                pb=self._optional_float(item.get("pb")),
                roe=self._optional_float(item.get("roe")),
                gross_margin=self._optional_float(item.get("gross_margin")),
                netprofit_margin=self._optional_float(item.get("netprofit_margin")),
                revenue_yoy=self._optional_float(item.get("revenue_yoy")),
                deduct_profit_yoy=self._optional_float(item.get("deduct_profit_yoy")),
                debt_to_assets=self._optional_float(item.get("debt_to_assets")),
                ocf=self._optional_float(item.get("ocf")),
                dividend_yield=self._optional_float(item.get("dividend_yield")),
                total_mv=self._optional_float(item.get("total_mv")),
                circ_mv=self._optional_float(item.get("circ_mv")),
                goodwill_ratio=self._optional_float(item.get("goodwill_ratio")),
            )
            for item in self.repo.financial_history(ts_code, limit=16)
        ]

        news_rows, news_warnings = StockNewsSearchService(self.conn).ensure_recent_news(
            ts_code=ts_code,
            name=base.name,
            days=15,
            min_real_news=3,
        )
        news = [
            StockNewsItem(
                id=int(item["id"]),
                title=item["title"],
                content=item["content"],
                source=item.get("source"),
                publish_time=item["publish_time"],
                sentiment_score=coerce_score(item.get("sentiment_score"), default=50),
                sentiment_label=item.get("sentiment_label") or "中性",
                keywords=[keyword for keyword in str(item.get("keywords") or "").split(",") if keyword],
            )
            for item in news_rows
        ]
        if news:
            sentiment_score = round(sum(item.sentiment_score for item in news[:15]) / len(news[:15]), 2)
            base.sentiment_score = sentiment_score
            base.sentiment_label = self._sentiment_label(sentiment_score)
            base.sentiment_factor_score = sentiment_score
        radar = {
            "价值": base.fundamental_score,
            "成长": self._float(row.get("revenue_yoy")),
            "资金": base.capital_score,
            "舆情": base.sentiment_factor_score,
        }
        settings = load_settings()
        source = f"本地SQLite缓存 / {settings.market_data.provider}"
        if settings.market_data.fallback_to_demo:
            source += " / 允许DEMO兜底"
        if any(str(item.get("source") or "").startswith("volc-search/") for item in news_rows):
            source += " / 火山搜索新闻"
        if not kline:
            data_warnings.append("当前个股缺少可用K线，请在数据中心触发真实行情同步。")
        elif len(kline) < 30:
            data_warnings.append(f"当前仅有 {len(kline)} 条可信K线，部分均线和回测信号会偏弱；请在数据中心同步更多历史行情。")
        if not financial_history:
            data_warnings.append("当前个股缺少可用财务历史，请在数据中心触发财务数据同步。")
        data_warnings.extend(news_warnings)
        return StockDetail(
            base=base,
            kline=kline,
            financial_history=financial_history,
            news=news,
            radar=radar,
            rating=base.rating,
            data_source=source,
            data_warnings=data_warnings,
        )

    def llm_analysis(self, ts_code: str) -> StockLlmAnalysisResponse:
        detail = self.detail(ts_code)
        llm = LlmClient(load_settings().llm)
        if not llm.available:
            return self._fallback_analysis(detail, "LLM未配置，已使用本地因子生成规则解析。")
        try:
            raw = llm.chat_json("你是A股个股研究解析助手。", self._analysis_prompt(detail))
            return self._analysis_from_llm(detail, raw)
        except Exception as exc:
            return self._fallback_analysis(detail, f"LLM解析失败，已使用本地因子生成规则解析：{exc}")

    @staticmethod
    def _market_row_matches(
        row: dict[str, Any],
        keyword: str,
        industry: str | None,
        rating: str | None,
        include_st: bool,
        include_paused: bool,
    ) -> bool:
        if keyword:
            if not StockService._keyword_matches(row, keyword):
                return False
        if industry and industry != "全部" and str(row.get("industry") or "未分类") != industry:
            return False
        if rating and rating != "全部" and str(row.get("rating") or "") != rating:
            return False
        if not include_st and int(row.get("is_st") or 0):
            return False
        if not include_paused and int(row.get("is_paused") or 0):
            return False
        return True

    @classmethod
    def _keyword_matches(cls, row: dict[str, Any], keyword: str) -> bool:
        normalized_keyword = cls._normalize_keyword(keyword)
        if not normalized_keyword:
            return True
        fields = [
            str(row.get("ts_code") or ""),
            str(row.get("symbol") or ""),
            str(row.get("name") or ""),
            str(row.get("industry") or ""),
            str(row.get("market") or ""),
        ]
        candidates = {cls._normalize_keyword(value) for value in fields if value}
        raw_name = str(row.get("name") or "")
        normalized_name = cls._normalize_stock_name(raw_name)
        if normalized_name:
            candidates.add(normalized_name)

        for candidate in candidates:
            if not candidate:
                continue
            if normalized_keyword in candidate:
                return True
            # 兼容 XD/DR 前缀和行情源短名称，例如“中国联通” vs “XD中国联”。
            if len(candidate) >= 3 and candidate in normalized_keyword:
                return True
        return False

    @classmethod
    def _normalize_keyword(cls, value: str) -> str:
        return cls._normalize_stock_name(value).lower().replace(" ", "").replace("-", "").replace("_", "")

    @staticmethod
    def _normalize_stock_name(value: str) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"^\*?st", "", text)
        text = re.sub(r"^(xd|xr|dr|n|c)", "", text)
        return text.replace(" ", "")

    @staticmethod
    def _sortable_fields() -> set[str]:
        return {
            "ai_score",
            "pct_chg",
            "pct_chg_20",
            "pct_chg_60",
            "close",
            "turnover_rate",
            "volume_ratio",
            "pe_ttm",
            "pb",
            "roe",
            "total_mv",
            "circ_mv",
            "main_net_inflow_sum",
            "sentiment_score",
        }

    @classmethod
    def _sort_value(cls, row: dict[str, Any], field: str) -> float:
        return cls._float(row.get(field))

    @classmethod
    def _to_market_item(cls, row: dict[str, Any]) -> StockMarketItem:
        base = ScreenerService._to_stock_score(row)
        return StockMarketItem(
            **base.model_dump(),
            trade_date=str(row.get("trade_date") or "") or None,
            total_mv=cls._optional_float(row.get("total_mv")),
            turnover_rate=cls._optional_float(row.get("turnover_rate")),
            volume_ratio=cls._optional_float(row.get("volume_ratio")),
            pct_chg_20=cls._optional_float(row.get("pct_chg_20")),
            pct_chg_60=cls._optional_float(row.get("pct_chg_60")),
            is_st=bool(row.get("is_st")),
            is_paused=bool(row.get("is_paused")),
        )

    @staticmethod
    def _optional_float(value: object) -> float | None:
        try:
            return None if value is None else round(float(value), 2)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float(value: object, default: float = 0.0) -> float:
        return safe_float(value, default)

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
    def _analysis_prompt(detail: StockDetail) -> str:
        base = detail.base
        snapshot = {
            "ts_code": base.ts_code,
            "name": base.name,
            "industry": base.industry,
            "rating": base.rating,
            "ai_score": base.ai_score,
            "factor_scores": {
                "fundamental": base.fundamental_score,
                "technical": base.technical_score,
                "capital": base.capital_score,
                "sentiment": base.sentiment_factor_score,
            },
            "market": {
                "close": base.close,
                "pct_chg": base.pct_chg,
                "pe_ttm": base.pe_ttm,
                "pb": base.pb,
                "roe": base.roe,
                "revenue_yoy": base.revenue_yoy,
                "main_net_inflow": base.main_net_inflow,
            },
            "latest_financial": [item.model_dump(mode="json") for item in detail.financial_history[:4]],
            "recent_news": [
                {
                    "title": item.title,
                    "sentiment_score": item.sentiment_score,
                    "sentiment_label": item.sentiment_label,
                    "keywords": item.keywords,
                    "publish_time": item.publish_time,
                }
                for item in detail.news[:8]
            ],
            "data_warnings": detail.data_warnings,
        }
        return f"""
请基于以下本地公开数据，对单只A股做研究解析。只输出JSON，不要输出Markdown。
边界：不能给实盘买卖指令，只能给观察、复盘和风险提示。

输出字段：
summary: 一句话结论
key_points: 字符串数组，3到5条，说明支持或关注依据
risks: 字符串数组，2到5条，说明主要风险
watch_items: 字符串数组，2到5条，说明后续观察指标或事件
questions: 字符串数组，2到4条，给复盘时要问的问题

个股数据：
{json.dumps(snapshot, ensure_ascii=False, default=str)}
"""

    @classmethod
    def _analysis_from_llm(cls, detail: StockDetail, raw: dict[str, Any]) -> StockLlmAnalysisResponse:
        return StockLlmAnalysisResponse(
            ts_code=detail.base.ts_code,
            name=detail.base.name,
            source="llm",
            summary=str(raw.get("summary") or cls._fallback_summary(detail)),
            key_points=cls._string_list(raw.get("key_points"))[:5],
            risks=cls._string_list(raw.get("risks"))[:5],
            watch_items=cls._string_list(raw.get("watch_items"))[:5],
            questions=cls._string_list(raw.get("questions"))[:4],
        )

    @classmethod
    def _fallback_analysis(cls, detail: StockDetail, reason: str = "") -> StockLlmAnalysisResponse:
        base = detail.base
        risks: list[str] = []
        if base.sentiment_score < 45:
            risks.append("舆情分偏弱，需要复核近期公告、新闻和投资者互动。")
        if base.pe_ttm and base.pe_ttm > 60:
            risks.append("市盈率处于偏高区间，需关注业绩兑现和估值回落风险。")
        if base.pct_chg and abs(base.pct_chg) > 7:
            risks.append("短期价格波动较大，需避免只依据单日涨跌做判断。")
        if detail.data_warnings:
            risks.extend(detail.data_warnings[:2])
        if reason:
            risks.append(reason)

        return StockLlmAnalysisResponse(
            ts_code=base.ts_code,
            name=base.name,
            source="fallback",
            summary=cls._fallback_summary(detail),
            key_points=[
                f"AI评分 {base.ai_score:.1f}，评级 {base.rating}，行业为 {base.industry or '未分类'}。",
                f"基本面/技术/资金/舆情分分别为 {base.fundamental_score:.1f}/{base.technical_score:.1f}/{base.capital_score:.1f}/{base.sentiment_factor_score:.1f}。",
                f"最新舆情为 {base.sentiment_label} {base.sentiment_score:.0f} 分。",
            ],
            risks=risks or ["暂未发现显著单项风险，但仍需结合最新公告和数据延迟复核。"],
            watch_items=[
                "复核最新财报的营收、利润率和现金流变化。",
                "观察主力资金流、成交量和均线位置是否与评分方向一致。",
                "跟踪近期新闻舆情是否持续改善或转弱。",
            ],
            questions=[
                "当前评分靠前主要来自基本面、技术、资金还是舆情？",
                "估值与成长是否匹配，是否存在单一指标驱动的误判？",
                "近期风险事件是否会改变原有跟踪逻辑？",
            ],
        )

    @staticmethod
    def _fallback_summary(detail: StockDetail) -> str:
        base = detail.base
        return f"{base.name}({base.ts_code}) 当前AI评分 {base.ai_score:.1f}、评级 {base.rating}，适合作为公开数据研究对象继续复盘。"

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [line.strip(" -·\t") for line in value.splitlines() if line.strip(" -·\t")]
        return []
