from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from statistics import median
from typing import Any, Callable

from app.models.schemas import (
    DecisionDashboardResponse,
    IndustryHeatItem,
    KlinePatternHit,
    PatternRadarResponse,
    StrategyBacktestSummary,
    StrategyDefinition,
    StrategyHit,
    StrategyScanResponse,
)
from app.services.data_repository import DataRepository
from app.services.factor_engine import FactorEngine
from app.services.screener_service import ScreenerService


class AnalysisService:
    """日报复盘、K线形态和策略实验室。

    所有方法默认读取本地行情/因子缓存，不做网络同步和写库操作，保证页面浏览足够轻。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = DataRepository(conn)
        self.factor_engine = FactorEngine(conn)

    def dashboard(self, limit: int = 8) -> DecisionDashboardResponse:
        rows = self._tradable_rows()
        total = len(rows)
        up_count = sum(1 for row in rows if self._num(row.get("pct_chg")) > 0)
        down_count = sum(1 for row in rows if self._num(row.get("pct_chg")) < 0)
        flat_count = max(0, total - up_count - down_count)
        limit_up_count = sum(1 for row in rows if self._num(row.get("pct_chg")) >= 9.5)
        limit_down_count = sum(1 for row in rows if self._num(row.get("pct_chg")) <= -9.5)
        avg_pct_chg = self._avg(row.get("pct_chg") for row in rows)
        avg_ai_score = self._avg(row.get("ai_score") for row in rows)
        avg_sentiment_score = self._avg(row.get("sentiment_score") for row in rows)
        risk_alerts = self._risk_alerts(rows, limit_down_count)
        return DecisionDashboardResponse(
            latest_trade_date=self.repo.latest_trade_date(),
            total=total,
            up_count=up_count,
            down_count=down_count,
            flat_count=flat_count,
            limit_up_count=limit_up_count,
            limit_down_count=limit_down_count,
            avg_pct_chg=round(avg_pct_chg, 2),
            avg_ai_score=round(avg_ai_score, 2),
            avg_sentiment_score=round(avg_sentiment_score, 2),
            market_view=self._market_view(total, up_count, down_count, avg_pct_chg, avg_ai_score),
            risk_alerts=risk_alerts,
            industry_heat=self._industry_heat(rows, limit=12),
            top_ai=self._scores(sorted(rows, key=lambda row: self._num(row.get("ai_score")), reverse=True)[:limit]),
            top_gainers=self._scores(sorted(rows, key=lambda row: self._num(row.get("pct_chg")), reverse=True)[:limit]),
            top_losers=self._scores(sorted(rows, key=lambda row: self._num(row.get("pct_chg")))[:limit]),
            high_risk=self._scores(
                sorted(
                    [row for row in rows if self._num(row.get("sentiment_score")) < 45 or self._num(row.get("pct_chg")) <= -7],
                    key=lambda row: (self._num(row.get("sentiment_score")), self._num(row.get("pct_chg"))),
                )[:limit]
            ),
            strategy_hits=[
                {"key": item.key, "name": item.name, "count": len(self._strategy_matches(item.key, rows)[:50])}
                for item in self.strategy_definitions()
            ],
        )

    def strategy_definitions(self) -> list[StrategyDefinition]:
        return [
            StrategyDefinition(
                key="volume_surge_up",
                name="放量上涨",
                category="技术面",
                description="当日上涨、量比放大且换手活跃，用于捕捉资金推动的短线候选。",
                risk_level="high",
            ),
            StrategyDefinition(
                key="ma_bullish",
                name="均线多头",
                category="技术面",
                description="收盘价站上短中期均线，MA5 > MA20 > MA60，趋势相对顺滑。",
            ),
            StrategyDefinition(
                key="platform_breakout",
                name="突破平台",
                category="技术面",
                description="收盘站上MA60，20日涨幅转正，叠加放量信号。",
                risk_level="high",
            ),
            StrategyDefinition(
                key="turtle_breakout",
                name="海龟突破",
                category="趋势",
                description="最新收盘接近近60日最高收盘，偏趋势突破候选。",
                risk_level="high",
            ),
            StrategyDefinition(
                key="value_quality",
                name="低估质量",
                category="基本面",
                description="PE/PB/ROE满足稳健阈值，并要求综合评分不弱。",
                risk_level="low",
            ),
            StrategyDefinition(
                key="oversold_rebound",
                name="超跌反弹",
                category="技术面",
                description="RSI/KDJ处于低位且舆情未明显恶化，用于复盘反弹观察池。",
                risk_level="high",
            ),
            StrategyDefinition(
                key="low_atr_growth",
                name="低波成长",
                category="成长",
                description="营收增速为正、20日趋势不弱，同时ATR相对收盘价较低。",
            ),
            StrategyDefinition(
                key="high_tight_flag",
                name="高而窄旗形",
                category="强势股",
                description="20日涨幅较强但短期波动收窄，适合观察强势整理。",
                risk_level="high",
            ),
        ]

    def scan_strategy(self, strategy_key: str, limit: int = 80, holding_days: int = 10) -> StrategyScanResponse:
        strategy = self._strategy(strategy_key)
        rows = self._tradable_rows()
        matches = self._strategy_matches(strategy.key, rows)
        hits = [self._strategy_hit(strategy, row) for row in matches[: max(1, min(limit, 300))]]
        return StrategyScanResponse(
            strategy=strategy,
            total=len(matches),
            rows=hits,
            backtest=self._backtest(strategy.key, matches[:80], holding_days=holding_days),
            latest_trade_date=self.repo.latest_trade_date(),
        )

    def pattern_radar(self, limit: int = 120, signal: str | None = None) -> PatternRadarResponse:
        rows_by_code = {row["ts_code"]: row for row in self._tradable_rows()}
        daily_map = self._recent_daily_map(limit_per_stock=3)
        hits: list[KlinePatternHit] = []
        for ts_code, daily_rows in daily_map.items():
            factor_row = rows_by_code.get(ts_code)
            if not factor_row:
                continue
            patterns = self._detect_patterns(daily_rows)
            for pattern in patterns:
                if signal and signal != "all" and pattern["signal"] != signal:
                    continue
                hits.append(
                    KlinePatternHit(
                        ts_code=ts_code,
                        name=str(factor_row.get("name") or ts_code),
                        industry=factor_row.get("industry"),
                        pattern=str(pattern["pattern"]),
                        signal=pattern["signal"],  # type: ignore[arg-type]
                        strength=round(float(pattern["strength"]), 2),
                        trade_date=str(daily_rows[0].get("trade_date") or ""),
                        close=self._optional_float(daily_rows[0].get("close")),
                        pct_chg=self._optional_float(daily_rows[0].get("pct_chg")),
                        reason=str(pattern["reason"]),
                        stock=ScreenerService._to_stock_score(factor_row),
                    )
                )
        hits.sort(key=lambda item: item.strength, reverse=True)
        distribution = Counter(hit.pattern for hit in hits)
        safe_limit = max(1, min(limit, 500))
        return PatternRadarResponse(
            total=len(hits),
            rows=hits[:safe_limit],
            latest_trade_date=self.repo.latest_trade_date(),
            distribution=dict(distribution),
        )

    def _tradable_rows(self) -> list[dict[str, Any]]:
        return [
            row
            for row in self.factor_engine.factor_rows()
            if not int(row.get("is_st") or 0) and not int(row.get("is_paused") or 0)
        ]

    def _strategy(self, key: str) -> StrategyDefinition:
        strategies = {item.key: item for item in self.strategy_definitions()}
        if key not in strategies:
            raise ValueError(f"未知策略：{key}")
        return strategies[key]

    def _strategy_matches(self, key: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        predicates: dict[str, Callable[[dict[str, Any]], bool]] = {
            "volume_surge_up": lambda row: self._num(row.get("pct_chg")) >= 2 and self._num(row.get("volume_ratio")) >= 1.8 and self._num(row.get("turnover_rate")) >= 2,
            "ma_bullish": lambda row: self._num(row.get("close")) > self._num(row.get("ma5")) > self._num(row.get("ma20")) > self._num(row.get("ma60")) and self._num(row.get("pct_chg_20")) > 0,
            "platform_breakout": lambda row: self._num(row.get("close")) >= self._num(row.get("ma60")) and self._num(row.get("pct_chg_20")) >= 0 and self._num(row.get("volume_ratio")) >= 1.3,
            "turtle_breakout": lambda row: self._num(row.get("pct_chg_60")) >= 15 and self._num(row.get("close")) >= self._num(row.get("ma20")) >= self._num(row.get("ma60")),
            "value_quality": lambda row: 0 < self._num(row.get("pe_ttm")) <= 20 and 0 < self._num(row.get("pb")) <= 3 and self._num(row.get("roe")) >= 8 and self._num(row.get("ai_score")) >= 48,
            "oversold_rebound": lambda row: self._num(row.get("rsi")) <= 35 and self._num(row.get("kdj_k")) <= 30 and self._num(row.get("sentiment_score")) >= 40,
            "low_atr_growth": lambda row: self._num(row.get("revenue_yoy")) >= 10 and self._num(row.get("pct_chg_20")) >= -5 and self._atr_ratio(row) <= 0.06,
            "high_tight_flag": lambda row: self._num(row.get("pct_chg_20")) >= 25 and abs(self._num(row.get("pct_chg_5"))) <= 10 and self._num(row.get("turnover_rate")) >= 1,
        }
        predicate = predicates[key]
        matched = [row for row in rows if predicate(row)]
        matched.sort(key=lambda row: self._signal_score(key, row), reverse=True)
        return matched

    def _strategy_hit(self, strategy: StrategyDefinition, row: dict[str, Any]) -> StrategyHit:
        return StrategyHit(
            ts_code=str(row["ts_code"]),
            name=str(row.get("name") or row["ts_code"]),
            industry=row.get("industry"),
            strategy_key=strategy.key,
            strategy_name=strategy.name,
            signal_score=round(self._signal_score(strategy.key, row), 2),
            reason=self._strategy_reason(strategy.key, row),
            stock=ScreenerService._to_stock_score(row),
        )

    def _signal_score(self, key: str, row: dict[str, Any]) -> float:
        ai = self._num(row.get("ai_score"))
        if key in {"volume_surge_up", "platform_breakout"}:
            return ai * 0.5 + self._num(row.get("volume_ratio")) * 8 + self._num(row.get("pct_chg")) * 2
        if key == "ma_bullish":
            return ai * 0.6 + self._num(row.get("pct_chg_20")) * 1.2 + self._num(row.get("technical_score")) * 0.2
        if key == "value_quality":
            return ai * 0.5 + self._num(row.get("roe")) * 1.5 - max(self._num(row.get("pe_ttm")), 0) * 0.2
        if key == "oversold_rebound":
            return ai * 0.4 + (40 - self._num(row.get("rsi"))) + self._num(row.get("sentiment_score")) * 0.3
        return ai * 0.65 + self._num(row.get("technical_score")) * 0.35

    def _strategy_reason(self, key: str, row: dict[str, Any]) -> str:
        if key == "value_quality":
            return f"PE {self._num(row.get('pe_ttm')):.1f}，PB {self._num(row.get('pb')):.1f}，ROE {self._num(row.get('roe')):.1f}%，估值和质量同时满足阈值。"
        if key == "oversold_rebound":
            return f"RSI {self._num(row.get('rsi')):.1f}，KDJ-K {self._num(row.get('kdj_k')):.1f}，舆情 {self._num(row.get('sentiment_score')):.0f}。"
        if key == "volume_surge_up":
            return f"当日涨跌幅 {self._num(row.get('pct_chg')):.2f}%，量比 {self._num(row.get('volume_ratio')):.2f}，换手率 {self._num(row.get('turnover_rate')):.2f}%。"
        return f"AI评分 {self._num(row.get('ai_score')):.1f}，技术分 {self._num(row.get('technical_score')):.1f}，20日涨幅 {self._num(row.get('pct_chg_20')):.2f}%。"

    def _backtest(self, strategy_key: str, rows: list[dict[str, Any]], holding_days: int) -> StrategyBacktestSummary:
        returns: list[float] = []
        for row in rows[:40]:
            daily = self.repo.stock_daily_frame(str(row["ts_code"]), limit=160)
            if len(daily) <= holding_days + 30:
                continue
            records = daily.to_dict(orient="records")
            for idx in range(30, len(records) - holding_days, max(holding_days, 5)):
                window = records[max(0, idx - 60) : idx + 1]
                proxy = self._daily_proxy(row, window)
                if self._strategy_matches(strategy_key, [proxy]):
                    entry = self._num(records[idx].get("close"))
                    exit_price = self._num(records[idx + holding_days].get("close"))
                    if entry > 0 and exit_price > 0:
                        returns.append((exit_price - entry) / entry * 100)
        if not returns:
            return StrategyBacktestSummary(holding_days=holding_days)
        return StrategyBacktestSummary(
            sample_count=len(returns),
            win_rate=round(sum(1 for value in returns if value > 0) / len(returns) * 100, 2),
            avg_return=round(sum(returns) / len(returns), 2),
            median_return=round(float(median(returns)), 2),
            max_return=round(max(returns), 2),
            min_return=round(min(returns), 2),
            holding_days=holding_days,
        )

    def _daily_proxy(self, base: dict[str, Any], window: list[dict[str, Any]]) -> dict[str, Any]:
        latest = window[-1]
        closes = [self._num(item.get("close")) for item in window if self._num(item.get("close")) > 0]
        vols = [self._num(item.get("vol")) for item in window if self._num(item.get("vol")) > 0]
        proxy = dict(base)
        proxy["close"] = self._num(latest.get("close"))
        proxy["pct_chg"] = self._num(latest.get("pct_chg"))
        proxy["volume_ratio"] = vols[-1] / (sum(vols[-5:]) / min(len(vols), 5)) if len(vols) >= 5 and sum(vols[-5:]) else 1
        for window_size in [5, 20, 60]:
            proxy[f"ma{window_size}"] = sum(closes[-window_size:]) / min(len(closes), window_size) if closes else 0
        proxy["pct_chg_5"] = self._period_return(closes, 5)
        proxy["pct_chg_20"] = self._period_return(closes, 20)
        proxy["pct_chg_60"] = self._period_return(closes, 60)
        return proxy

    def _recent_daily_map(self, limit_per_stock: int) -> dict[str, list[dict[str, Any]]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM (
                SELECT d.*, ROW_NUMBER() OVER (PARTITION BY d.ts_code ORDER BY d.trade_date DESC) AS rn
                FROM stock_daily d
            )
            WHERE rn <= ?
            ORDER BY ts_code, trade_date DESC
            """,
            (limit_per_stock,),
        ).fetchall()
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            data = dict(row)
            data.pop("rn", None)
            result[str(data["ts_code"])].append(data)
        return result

    def _detect_patterns(self, rows: list[dict[str, Any]]) -> list[dict[str, object]]:
        if not rows:
            return []
        latest = rows[0]
        previous = rows[1] if len(rows) > 1 else None
        third = rows[2] if len(rows) > 2 else None
        patterns: list[dict[str, object]] = []
        open_price = self._num(latest.get("open"))
        close = self._num(latest.get("close"))
        high = self._num(latest.get("high"))
        low = self._num(latest.get("low"))
        body = abs(close - open_price)
        full_range = max(high - low, 0.01)
        upper = high - max(open_price, close)
        lower = min(open_price, close) - low
        if body / full_range <= 0.1:
            patterns.append({"pattern": "十字星", "signal": "neutral", "strength": 55 + (0.1 - body / full_range) * 200, "reason": "实体很小，多空分歧加剧。"})
        if lower >= max(body * 2, full_range * 0.35) and upper <= full_range * 0.25:
            patterns.append({"pattern": "锤头线", "signal": "bullish", "strength": min(95, 55 + lower / full_range * 45), "reason": "下影线较长，显示下方承接增强。"})
        if upper >= max(body * 2, full_range * 0.35) and lower <= full_range * 0.25:
            patterns.append({"pattern": "射击之星", "signal": "bearish", "strength": min(95, 55 + upper / full_range * 45), "reason": "上影线较长，显示上方抛压较重。"})
        if previous:
            prev_open = self._num(previous.get("open"))
            prev_close = self._num(previous.get("close"))
            if close > open_price and prev_close < prev_open and close >= prev_open and open_price <= prev_close:
                patterns.append({"pattern": "看涨吞没", "signal": "bullish", "strength": 82, "reason": "阳线实体吞没前一日阴线实体。"})
            if close < open_price and prev_close > prev_open and close <= prev_open and open_price >= prev_close:
                patterns.append({"pattern": "看跌吞没", "signal": "bearish", "strength": 82, "reason": "阴线实体吞没前一日阳线实体。"})
        if previous and third:
            prev_body = abs(self._num(previous.get("close")) - self._num(previous.get("open")))
            first_down = self._num(third.get("close")) < self._num(third.get("open"))
            first_up = self._num(third.get("close")) > self._num(third.get("open"))
            middle_small = prev_body <= max(abs(self._num(third.get("close")) - self._num(third.get("open"))) * 0.55, 0.01)
            if first_down and middle_small and close > open_price and close > (self._num(third.get("open")) + self._num(third.get("close"))) / 2:
                patterns.append({"pattern": "早晨之星", "signal": "bullish", "strength": 88, "reason": "下跌后小实体整理，再由阳线收复前段跌幅。"})
            if first_up and middle_small and close < open_price and close < (self._num(third.get("open")) + self._num(third.get("close"))) / 2:
                patterns.append({"pattern": "黄昏之星", "signal": "bearish", "strength": 88, "reason": "上涨后小实体整理，再由阴线跌破前段中位。"})
        return patterns

    def _industry_heat(self, rows: list[dict[str, Any]], limit: int) -> list[IndustryHeatItem]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row.get("industry") or "未分类")].append(row)
        result = [
            IndustryHeatItem(
                industry=industry,
                count=len(items),
                avg_pct_chg=round(self._avg(item.get("pct_chg") for item in items), 2),
                avg_ai_score=round(self._avg(item.get("ai_score") for item in items), 2),
                up_ratio=round(sum(1 for item in items if self._num(item.get("pct_chg")) > 0) / max(1, len(items)) * 100, 2),
            )
            for industry, items in groups.items()
        ]
        result.sort(key=lambda item: (item.avg_pct_chg, item.avg_ai_score), reverse=True)
        return result[:limit]

    def _risk_alerts(self, rows: list[dict[str, Any]], limit_down_count: int) -> list[str]:
        alerts: list[str] = []
        weak_sentiment = sum(1 for row in rows if self._num(row.get("sentiment_score")) < 40)
        big_drop = sum(1 for row in rows if self._num(row.get("pct_chg")) <= -7)
        if limit_down_count:
            alerts.append(f"跌停或接近跌停股票 {limit_down_count} 只，短线风险偏高。")
        if big_drop:
            alerts.append(f"单日跌幅超过7%的股票 {big_drop} 只，需要检查行业或主题集中风险。")
        if weak_sentiment:
            alerts.append(f"舆情低于40分的股票 {weak_sentiment} 只，建议复核公告、问询、减持和诉讼信息。")
        if not alerts:
            alerts.append("未发现显著系统性风险信号，仍需结合交易日新闻和公告复核。")
        return alerts

    def _market_view(self, total: int, up_count: int, down_count: int, avg_pct_chg: float, avg_ai_score: float) -> str:
        if not total:
            return "当前没有可用行情缓存，请先同步行情并刷新因子。"
        up_ratio = up_count / total * 100
        if up_ratio >= 60 and avg_pct_chg > 0:
            tone = "市场整体偏强"
        elif up_ratio <= 40 and avg_pct_chg < 0:
            tone = "市场整体偏弱"
        else:
            tone = "市场分化震荡"
        return f"{tone}：上涨占比 {up_ratio:.1f}%，平均涨跌幅 {avg_pct_chg:.2f}%，全市场平均AI评分 {avg_ai_score:.1f}。"

    @staticmethod
    def _scores(rows: list[dict[str, Any]]) -> list[Any]:
        return [ScreenerService._to_stock_score(row) for row in rows]

    @staticmethod
    def _avg(values: Any) -> float:
        nums = [AnalysisService._num(value) for value in values if value is not None]
        return sum(nums) / len(nums) if nums else 0

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            return None if value is None else round(float(value), 2)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _period_return(closes: list[float], days: int) -> float:
        if len(closes) <= days or closes[-days - 1] == 0:
            return 0
        return (closes[-1] - closes[-days - 1]) / closes[-days - 1] * 100

    @classmethod
    def _atr_ratio(cls, row: dict[str, Any]) -> float:
        close = cls._num(row.get("close"))
        return cls._num(row.get("atr")) / close if close else 1
