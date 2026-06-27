from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime
from typing import Any, Callable

from app.core.config import load_settings
from app.models.schemas import RangeFilter, ScreeningDiagnostics, ScreeningRequest, ScreeningResult, StockScore
from app.services.data_repository import DataRepository
from app.services.factor_engine import FactorEngine


class ScreenerService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = DataRepository(conn)
        self.factor_engine = FactorEngine(conn)

    def run(self, request: ScreeningRequest) -> ScreeningResult:
        rows = self.factor_engine.factor_rows()
        base_filtered: list[dict[str, Any]] = []
        excluded_counts: Counter[str] = Counter()
        missing_list_date_count = 0
        base_options = self._resolve_base_options(request)
        for row in rows:
            passed, reason = self._base_filter_result(row, base_options)
            if passed:
                base_filtered.append(row)
                if reason == "missing_list_date":
                    missing_list_date_count += 1
            elif reason:
                excluded_counts[reason] += 1

        conditions: list[Callable[[dict[str, Any]], bool]] = []
        index_condition = self._index_condition(request)
        if index_condition:
            conditions.append(index_condition)
        conditions.extend(self._fundamental_conditions(request))
        conditions.extend(self._technical_conditions(request))
        conditions.extend(self._capital_conditions(request))
        sentiment_condition = self._sentiment_condition(request)
        if sentiment_condition:
            conditions.append(sentiment_condition)

        if conditions:
            if request.logic == "or":
                matched = [row for row in base_filtered if any(condition(row) for condition in conditions)]
            else:
                matched = [row for row in base_filtered if all(condition(row) for condition in conditions)]
        else:
            matched = base_filtered

        matched.sort(key=lambda item: float(item.get("ai_score") or 0), reverse=True)
        limited = matched[: request.limit]
        stock_rows = [self._to_stock_score(row) for row in limited]
        stock_count = self.conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        warnings = self._diagnostic_warnings(request, rows, int(stock_count or 0), missing_list_date_count)
        return ScreeningResult(
            total=len(matched),
            rows=stock_rows,
            industry_distribution=dict(Counter(row.industry or "未分类" for row in stock_rows)),
            sentiment_distribution=dict(Counter(row.sentiment_label for row in stock_rows)),
            factor_distribution={
                "fundamental": [row.fundamental_score for row in stock_rows],
                "technical": [row.technical_score for row in stock_rows],
                "capital": [row.capital_score for row in stock_rows],
                "sentiment": [row.sentiment_factor_score for row in stock_rows],
                "ai": [row.ai_score for row in stock_rows],
            },
            latest_trade_date=self.repo.latest_trade_date(),
            diagnostics=ScreeningDiagnostics(
                stock_universe_count=int(stock_count or 0),
                factor_universe_count=len(rows),
                base_universe_count=len(base_filtered),
                condition_count=len(conditions),
                matched_count=len(matched),
                returned_count=len(stock_rows),
                excluded_counts=dict(excluded_counts),
                warnings=warnings,
            ),
        )

    def _pass_base_filters(self, row: dict[str, Any], request: ScreeningRequest) -> bool:
        return self._base_filter_result(row, self._resolve_base_options(request))[0]

    @staticmethod
    def _resolve_base_options(request: ScreeningRequest) -> dict[str, Any]:
        settings = load_settings()
        return {
            "exclude_st": request.filters.exclude_st if request.filters.exclude_st is not None else settings.filters.exclude_st,
            "exclude_paused": request.filters.exclude_paused if request.filters.exclude_paused is not None else settings.filters.exclude_paused,
            "new_stock_days": request.filters.new_stock_days if request.filters.new_stock_days is not None else settings.filters.new_stock_days,
            "min_market_cap": request.filters.min_market_cap if request.filters.min_market_cap is not None else settings.filters.min_market_cap,
        }

    def _base_filter_result(self, row: dict[str, Any], options: dict[str, Any]) -> tuple[bool, str | None]:
        if options["exclude_st"] and int(row.get("is_st") or 0):
            return False, "ST/*ST"
        if options["exclude_paused"] and int(row.get("is_paused") or 0):
            return False, "停牌"
        min_market_cap = options["min_market_cap"]
        if min_market_cap and float(row.get("total_mv") or 0) < min_market_cap:
            return False, "低于最小市值"
        new_stock_days = options["new_stock_days"]
        if new_stock_days:
            list_date = str(row.get("list_date") or "")
            try:
                listed_days = (datetime.now() - datetime.strptime(list_date, "%Y%m%d")).days
                if listed_days < new_stock_days:
                    return False, "次新股"
            except ValueError:
                # AKShare部分行情接口不会提供上市日期。缺失时保留股票，并通过诊断提示用户该过滤条件无法覆盖这些标的。
                return True, "missing_list_date"
        return True, None

    @staticmethod
    def _diagnostic_warnings(
        request: ScreeningRequest,
        rows: list[dict[str, Any]],
        stock_count: int,
        missing_list_date_count: int,
    ) -> list[str]:
        warnings: list[str] = []
        if request.filters.new_stock_days and missing_list_date_count:
            warnings.append(
                f"有 {missing_list_date_count} 只股票缺少上市日期，已保留参与筛选；次新股过滤仅对有上市日期的股票生效。"
            )
        if not rows:
            warnings.append("当前没有可用因子缓存，请先在系统配置中同步行情或重算因子。")
        elif len(rows) < stock_count:
            warnings.append(f"因子缓存仅覆盖 {len(rows)} / {stock_count} 只股票，后台已尝试预热缺失缓存。")
        return warnings

    def _index_condition(self, request: ScreeningRequest) -> Callable[[dict[str, Any]], bool] | None:
        index_codes = request.index.index_codes[:]
        if request.index.track_momentum_top_n:
            index_codes = self.repo.top_momentum_indices(index_codes, request.index.track_momentum_top_n)
        if request.index.max_pe_percentile is not None or request.index.max_pb_percentile is not None:
            index_codes = self.repo.eligible_indices_by_valuation(
                index_codes,
                request.index.max_pe_percentile,
                request.index.max_pb_percentile,
            )
        member_set = self.repo.index_members(index_codes) if index_codes else set()

        if not index_codes and not request.index.min_excess_return:
            return None

        def condition(row: dict[str, Any]) -> bool:
            if request.index.require_member and index_codes and row["ts_code"] not in member_set:
                return False
            if request.index.min_excess_return is not None:
                days = request.index.excess_return_days or 20
                relative = self.repo.relative_return(row["ts_code"], index_codes, days)
                if relative is None or relative < request.index.min_excess_return:
                    return False
            return True

        return condition

    def _fundamental_conditions(self, request: ScreeningRequest) -> list[Callable[[dict[str, Any]], bool]]:
        fields = [
            "pe_ttm",
            "pb",
            "peg",
            "roe",
            "gross_margin",
            "netprofit_margin",
            "revenue_yoy",
            "deduct_profit_yoy",
            "debt_to_assets",
            "dividend_yield",
            "total_mv",
            "circ_mv",
            "goodwill_ratio",
        ]
        conditions: list[Callable[[dict[str, Any]], bool]] = []
        for field in fields:
            range_filter = getattr(request.fundamental, field)
            if range_filter is not None and (range_filter.min is not None or range_filter.max is not None):
                conditions.append(lambda row, f=field, rf=range_filter: self._in_range(row.get(f), rf))
        if request.fundamental.industry_percentile_top is not None:
            threshold = request.fundamental.industry_percentile_top
            conditions.append(lambda row: float(row.get("fundamental_score") or 0) >= threshold)
        return conditions

    def _technical_conditions(self, request: ScreeningRequest) -> list[Callable[[dict[str, Any]], bool]]:
        conditions: list[Callable[[dict[str, Any]], bool]] = []
        if request.technical.above_ma:
            conditions.append(
                lambda row: all(float(row.get("close") or 0) >= float(row.get(f"ma{window}") or 10**12) for window in request.technical.above_ma)
            )
        if request.technical.macd_cross:
            conditions.append(lambda row: row.get("macd_cross") == request.technical.macd_cross)
        if request.technical.kdj_cross:
            conditions.append(lambda row: row.get("kdj_cross") == request.technical.kdj_cross)
        if request.technical.rsi:
            conditions.append(lambda row: self._in_range(row.get("rsi"), request.technical.rsi))
        if request.technical.pct_chg_n:
            field = f"pct_chg_{request.technical.pct_chg_days}"
            conditions.append(lambda row, f=field: self._in_range(row.get(f), request.technical.pct_chg_n))
        if request.technical.turnover_rate:
            conditions.append(lambda row: self._in_range(row.get("turnover_rate"), request.technical.turnover_rate))
        if request.technical.volume_ratio:
            conditions.append(lambda row: self._in_range(row.get("volume_ratio"), request.technical.volume_ratio))
        if request.technical.breakout_days:
            conditions.append(lambda row: bool(row.get(f"breakout_{request.technical.breakout_days}") or row.get("breakout_20")))
        if request.technical.limit_up_days_min is not None:
            conditions.append(lambda row: int(row.get("limit_up_days_60") or 0) >= int(request.technical.limit_up_days_min or 0))
        return conditions

    def _capital_conditions(self, request: ScreeningRequest) -> list[Callable[[dict[str, Any]], bool]]:
        mapping = {
            "north_inflow_min": "north_inflow_sum",
            "main_net_inflow_min": "main_net_inflow_sum",
            "margin_balance_delta_min": "margin_balance_delta_sum",
            "institution_holding_ratio_min": "institution_holding_ratio",
            "top_list_score_min": "top_list_score",
        }
        conditions: list[Callable[[dict[str, Any]], bool]] = []
        for request_field, row_field in mapping.items():
            value = getattr(request.capital, request_field)
            if value is not None:
                conditions.append(lambda row, f=row_field, min_value=value: float(row.get(f) or 0) >= min_value)
        return conditions

    def _sentiment_condition(self, request: ScreeningRequest) -> Callable[[dict[str, Any]], bool] | None:
        has_condition = any(
            [
                request.sentiment.min_avg_score is not None,
                request.sentiment.include_labels,
                request.sentiment.whitelist_keywords,
                request.sentiment.blacklist_keywords,
                request.sentiment.max_negative_ratio is not None,
            ]
        )
        if not has_condition:
            return None

        def condition(row: dict[str, Any]) -> bool:
            score_field = "sentiment_score_15" if request.sentiment.days > 7 else "sentiment_score"
            if request.sentiment.min_avg_score is not None and float(row.get(score_field) or 50) < request.sentiment.min_avg_score:
                return False
            if request.sentiment.include_labels and str(row.get("sentiment_label")) not in request.sentiment.include_labels:
                return False
            text = str(row.get("recent_news_text") or "")
            if request.sentiment.whitelist_keywords and not any(keyword in text for keyword in request.sentiment.whitelist_keywords):
                return False
            if request.sentiment.blacklist_keywords and any(keyword in text for keyword in request.sentiment.blacklist_keywords):
                return False
            if request.sentiment.max_negative_ratio is not None and float(row.get("negative_news_ratio") or 0) > request.sentiment.max_negative_ratio:
                return False
            return True

        return condition

    @staticmethod
    def _in_range(value: Any, range_filter: RangeFilter) -> bool:
        number = float(value or 0)
        if range_filter.min is not None and number < range_filter.min:
            return False
        if range_filter.max is not None and number > range_filter.max:
            return False
        return True

    @staticmethod
    def _to_stock_score(row: dict[str, Any]) -> StockScore:
        metrics = {
            key: row.get(key)
            for key in [
                "ma5",
                "ma20",
                "ma60",
                "macd",
                "kdj_k",
                "rsi",
                "boll_upper",
                "atr",
                "turnover_rate",
                "volume_ratio",
                "amplitude",
                "pct_chg_20",
                "pct_chg_60",
                "north_inflow_sum",
                "main_net_inflow_sum",
                "chip_profit_ratio",
                "limit_up_days_60",
            ]
        }
        return StockScore(
            ts_code=str(row["ts_code"]),
            symbol=str(row.get("symbol") or row["ts_code"].split(".")[0]),
            name=str(row.get("name") or row["ts_code"]),
            industry=row.get("industry"),
            index_names=row.get("index_names") or [],
            close=row.get("close"),
            pct_chg=row.get("pct_chg"),
            pe_ttm=row.get("pe_ttm"),
            pb=row.get("pb"),
            roe=row.get("roe"),
            revenue_yoy=row.get("revenue_yoy"),
            circ_mv=row.get("circ_mv"),
            main_net_inflow=row.get("main_net_inflow_sum"),
            sentiment_score=float(row.get("sentiment_score") or 50),
            sentiment_label=str(row.get("sentiment_label") or "中性"),
            fundamental_score=float(row.get("fundamental_score") or 0),
            technical_score=float(row.get("technical_score") or 0),
            capital_score=float(row.get("capital_score") or 0),
            sentiment_factor_score=float(row.get("sentiment_factor_score") or 0),
            ai_score=float(row.get("ai_score") or 0),
            rating=row.get("rating") if row.get("rating") in {"A", "B", "C", "D"} else "C",
            metrics=metrics,
        )
