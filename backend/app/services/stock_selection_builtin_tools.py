from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings, load_settings
from app.models.schemas import ScreeningRequest
from app.services.llm_client import extract_json


INDEX_ALIASES = {
    "沪深300": "000300.SH",
    "HS300": "000300.SH",
    "中证500": "000905.SH",
    "中证1000": "000852.SH",
    "上证50": "000016.SH",
    "创业板": "399006.SZ",
    "创业板指": "399006.SZ",
    "科创50": "000688.SH",
    "北证50": "899050.BJ",
    "AI": "CONCEPT_AI",
    "人工智能": "CONCEPT_AI",
    "算力": "CONCEPT_AI",
    "半导体": "CONCEPT_SEMI",
    "芯片": "CONCEPT_SEMI",
    "国产替代": "CONCEPT_SEMI",
    "储能": "CONCEPT_STORAGE",
    "新能源": "CONCEPT_STORAGE",
    "军工": "CONCEPT_DEFENSE",
    "医药": "CONCEPT_MEDICAL",
}

FUNDAMENTAL_FIELD_ALIASES = {
    "pe": "pe_ttm",
    "pe_ttm": "pe_ttm",
    "市盈率": "pe_ttm",
    "市盈率ttm": "pe_ttm",
    "pb": "pb",
    "市净率": "pb",
    "peg": "peg",
    "roe": "roe",
    "净资产收益率": "roe",
    "毛利率": "gross_margin",
    "gross_margin": "gross_margin",
    "净利率": "netprofit_margin",
    "netprofit_margin": "netprofit_margin",
    "营收同比": "revenue_yoy",
    "营收增速": "revenue_yoy",
    "收入同比": "revenue_yoy",
    "revenue_yoy": "revenue_yoy",
    "扣非净利": "deduct_profit_yoy",
    "扣非净利润增速": "deduct_profit_yoy",
    "deduct_profit_yoy": "deduct_profit_yoy",
    "资产负债率": "debt_to_assets",
    "负债率": "debt_to_assets",
    "debt_to_assets": "debt_to_assets",
    "股息率": "dividend_yield",
    "dividend_yield": "dividend_yield",
    "总市值": "total_mv",
    "total_mv": "total_mv",
    "流通市值": "circ_mv",
    "circ_mv": "circ_mv",
    "商誉占比": "goodwill_ratio",
    "goodwill_ratio": "goodwill_ratio",
}

SENTIMENT_LABEL_ALIASES = {
    "重大利好": "重大利好",
    "大利好": "重大利好",
    "普通利好": "普通利好",
    "利好": "普通利好",
    "中性": "中性",
    "普通利空": "普通利空",
    "利空": "普通利空",
    "重大利空": "重大利空",
}

TECHNICAL_CROSS_ALIASES = {
    "golden": "golden",
    "金叉": "golden",
    "dead": "dead",
    "death": "dead",
    "死叉": "dead",
}


@dataclass
class BuiltinToolExecutionResult:
    request: ScreeningRequest
    raw_conditions: dict[str, Any]
    applied_tools: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class StockSelectionBuiltinTools:
    """把不可靠的LLM输出收敛到受控的选股条件构造器。

    LLM只能提出“调用哪个工具、参数是什么”。每个工具都会做字段白名单、类型转换、
    范围修正和默认值补齐，最终只有通过Pydantic校验的ScreeningRequest会进入筛选器。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.data = self._initial_request_data()
        self.warnings: list[str] = []
        self.applied_tools: list[dict[str, Any]] = []

    @classmethod
    def tool_definitions(cls) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "select_index_pool",
                    "description": "设置指数、行业或概念选股池，以及指数估值/超额收益过滤。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "indexes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "指数代码或中文名称，例如沪深300、中证500、半导体、算力。",
                            },
                            "require_member": {"type": "boolean", "description": "是否只保留指数成分股。"},
                            "excess_return_days": {"type": "integer", "description": "相对指数超额收益计算天数。"},
                            "min_excess_return": {"type": "number", "description": "相对指数最小超额收益，单位百分比。"},
                            "max_pe_percentile": {"type": "number", "description": "指数PE估值分位上限，0到100。"},
                            "max_pb_percentile": {"type": "number", "description": "指数PB估值分位上限，0到100。"},
                            "track_momentum_top_n": {"type": "integer", "description": "仅保留动量排名前N的指数池。"},
                        },
                        "required": ["indexes"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_fundamental_ranges",
                    "description": "设置基本面区间条件，可一次传入多个字段。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "field": {"type": "string", "description": "PE、PB、ROE、营收同比、流通市值等。"},
                                        "min": {"type": "number"},
                                        "max": {"type": "number"},
                                    },
                                    "required": ["field"],
                                },
                            },
                            "industry_percentile_top": {"type": "number", "description": "行业内基本面分位下限，0到100。"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_technical_conditions",
                    "description": "设置技术指标条件，包括均线、MACD/KDJ、N日涨跌幅、换手率、量比等。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "above_ma": {"type": "array", "items": {"type": "integer"}, "description": "站上的均线窗口，如5/10/20/60/120。"},
                            "macd_cross": {"type": "string", "description": "golden/dead或金叉/死叉。"},
                            "kdj_cross": {"type": "string", "description": "golden/dead或金叉/死叉。"},
                            "rsi_min": {"type": "number"},
                            "rsi_max": {"type": "number"},
                            "pct_chg_days": {"type": "integer"},
                            "pct_chg_min": {"type": "number"},
                            "pct_chg_max": {"type": "number"},
                            "turnover_rate_min": {"type": "number"},
                            "turnover_rate_max": {"type": "number"},
                            "volume_ratio_min": {"type": "number"},
                            "volume_ratio_max": {"type": "number"},
                            "breakout_days": {"type": "integer"},
                            "limit_up_days_min": {"type": "integer"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_capital_conditions",
                    "description": "设置资金流条件。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "north_inflow_min": {"type": "number", "description": "北向资金净流入下限。"},
                            "main_net_inflow_min": {"type": "number", "description": "主力净流入下限。"},
                            "margin_balance_delta_min": {"type": "number", "description": "融资余额变化下限。"},
                            "institution_holding_ratio_min": {"type": "number", "description": "机构持仓比例下限。"},
                            "top_list_score_min": {"type": "number", "description": "龙虎榜强度下限。"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_sentiment_conditions",
                    "description": "设置新闻公告舆情过滤条件。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer", "description": "近N日舆情窗口。"},
                            "min_avg_score": {"type": "number", "description": "平均舆情分下限，0到100。"},
                            "include_labels": {"type": "array", "items": {"type": "string"}, "description": "重大利好、普通利好、中性、普通利空、重大利空。"},
                            "whitelist_keywords": {"type": "array", "items": {"type": "string"}},
                            "blacklist_keywords": {"type": "array", "items": {"type": "string"}},
                            "max_negative_ratio": {"type": "number", "description": "利空新闻占比上限，0到1或0到100。"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_risk_filters",
                    "description": "设置全局风险过滤条件，例如剔除ST、停牌、次新股、市值下限。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "exclude_st": {"type": "boolean"},
                            "exclude_paused": {"type": "boolean"},
                            "new_stock_days": {"type": "integer"},
                            "min_market_cap": {"type": "number", "description": "最小总市值，单位亿元。"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_score_weights",
                    "description": "设置综合评分四维权重。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "fundamental": {"type": "number"},
                            "technical": {"type": "number"},
                            "capital": {"type": "number"},
                            "sentiment": {"type": "number"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_result_limit",
                    "description": "设置返回结果数量上限。",
                    "parameters": {
                        "type": "object",
                        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}},
                        "required": ["limit"],
                    },
                },
            },
        ]

    @classmethod
    def planning_prompt(cls, user_text: str) -> str:
        tool_names = [str(item["function"]["name"]) for item in cls.tool_definitions()]
        return f"""
请把用户的A股自然语言选股需求转换成一组函数工具调用。

规则：
1. 只调用已提供的工具：{", ".join(tool_names)}。
2. 不要直接输出股票名单，不要编造行情数据。
3. 用户没有明确提出的参数不要传，不要传 null；未知字段直接省略。
4. 指数/题材可以传中文名称，后端会统一映射。
5. 数字统一使用 number，例如 PE低于25 => set_fundamental_ranges filters=[{{"field":"PE","max":25}}]。
6. 默认风险过滤应调用 set_risk_filters，剔除ST、停牌和180日内次新股。

可识别指数/题材别名：
{json.dumps(INDEX_ALIASES, ensure_ascii=False)}

用户需求：
{user_text}
"""

    def execute(self, raw_calls: Any, user_text: str = "") -> BuiltinToolExecutionResult:
        calls = self._normalize_tool_calls(raw_calls)
        if not calls:
            self.warnings.append("LLM未返回可执行工具调用，已仅使用系统默认筛选条件。")

        for call in calls:
            name = str(call.get("name") or "")
            args = call.get("arguments")
            if not isinstance(args, dict):
                self.warnings.append(f"{name or '未知工具'} 参数不是对象，已忽略。")
                continue
            handler = getattr(self, f"_tool_{name}", None)
            if handler is None:
                self.warnings.append(f"LLM尝试调用未注册工具 {name}，已拒绝。")
                continue
            before = json.dumps(self.data, ensure_ascii=False, sort_keys=True)
            handler(args)
            after = json.dumps(self.data, ensure_ascii=False, sort_keys=True)
            self.applied_tools.append({"name": name, "arguments": self._jsonable(args), "changed": before != after})

        if user_text:
            self._apply_text_safety_defaults(user_text)

        try:
            request = ScreeningRequest.model_validate(self.data)
        except ValidationError as exc:
            raise ValueError(f"builtin工具生成的筛选条件未通过校验：{exc}") from exc

        return BuiltinToolExecutionResult(
            request=request,
            raw_conditions=self._jsonable(self.data),
            applied_tools=self.applied_tools,
            warnings=self.warnings,
        )

    def _initial_request_data(self) -> dict[str, Any]:
        return {
            "logic": "and",
            "index": {
                "index_codes": [],
                "require_member": False,
                "excess_return_days": 20,
                "min_excess_return": None,
                "max_pe_percentile": None,
                "max_pb_percentile": None,
                "track_momentum_top_n": None,
            },
            "fundamental": {},
            "technical": {"above_ma": [], "pct_chg_days": 20},
            "capital": {},
            "sentiment": {"days": 7, "include_labels": [], "whitelist_keywords": [], "blacklist_keywords": []},
            "filters": {
                "exclude_st": self.settings.filters.exclude_st,
                "exclude_paused": self.settings.filters.exclude_paused,
                "new_stock_days": self.settings.filters.new_stock_days,
                "min_market_cap": self.settings.filters.min_market_cap,
            },
            "weights": {
                "fundamental": self.settings.weights.fundamental,
                "technical": self.settings.weights.technical,
                "capital": self.settings.weights.capital,
                "sentiment": self.settings.weights.sentiment,
            },
            "limit": 200,
        }

    def _tool_select_index_pool(self, args: dict[str, Any]) -> None:
        raw_indexes = args.get("indexes") or args.get("index_codes") or args.get("indices") or []
        codes: list[str] = []
        for item in self._ensure_list(raw_indexes):
            code = self._normalize_index_code(item)
            if code and code not in codes:
                codes.append(code)
            elif item:
                self.warnings.append(f"无法识别指数/题材 {item}，已忽略。")
        self.data["index"]["index_codes"] = codes
        self.data["index"]["require_member"] = self._bool(args.get("require_member"), default=bool(codes))
        self._set_int("index", "excess_return_days", args.get("excess_return_days"), min_value=1, max_value=250)
        self._set_number("index", "min_excess_return", args.get("min_excess_return"))
        self._set_number("index", "max_pe_percentile", args.get("max_pe_percentile"), min_value=0, max_value=100)
        self._set_number("index", "max_pb_percentile", args.get("max_pb_percentile"), min_value=0, max_value=100)
        self._set_int("index", "track_momentum_top_n", args.get("track_momentum_top_n"), min_value=1, max_value=50)

    def _tool_set_fundamental_ranges(self, args: dict[str, Any]) -> None:
        filters = args.get("filters")
        if isinstance(filters, dict):
            filters = [filters]
        if not isinstance(filters, list):
            filters = []
        for item in filters:
            if not isinstance(item, dict):
                self.warnings.append("基本面过滤项不是对象，已忽略。")
                continue
            field = self._normalize_fundamental_field(item.get("field"))
            if not field:
                self.warnings.append(f"未知基本面字段 {item.get('field')}，已忽略。")
                continue
            self._set_range("fundamental", field, item.get("min"), item.get("max"))
        self._set_number("fundamental", "industry_percentile_top", args.get("industry_percentile_top"), min_value=0, max_value=100)

    def _tool_set_technical_conditions(self, args: dict[str, Any]) -> None:
        ma_values = []
        for item in self._ensure_list(args.get("above_ma")):
            window = self._int(item, min_value=1, max_value=250)
            if window in {5, 10, 20, 60, 120} and window not in ma_values:
                ma_values.append(window)
            elif window is not None:
                self.warnings.append(f"暂不支持MA{window}，已忽略。")
        if ma_values:
            self.data["technical"]["above_ma"] = ma_values

        self._set_cross("technical", "macd_cross", args.get("macd_cross"))
        self._set_cross("technical", "kdj_cross", args.get("kdj_cross"))
        self._set_range("technical", "rsi", args.get("rsi_min"), args.get("rsi_max"), min_value=0, max_value=100)
        self._set_int("technical", "pct_chg_days", args.get("pct_chg_days"), min_value=1, max_value=250)
        self._set_range("technical", "pct_chg_n", args.get("pct_chg_min"), args.get("pct_chg_max"))
        self._set_range("technical", "turnover_rate", args.get("turnover_rate_min"), args.get("turnover_rate_max"), min_value=0)
        self._set_range("technical", "volume_ratio", args.get("volume_ratio_min"), args.get("volume_ratio_max"), min_value=0)
        self._set_int("technical", "breakout_days", args.get("breakout_days"), min_value=1, max_value=250)
        self._set_int("technical", "limit_up_days_min", args.get("limit_up_days_min"), min_value=0, max_value=60)

    def _tool_set_capital_conditions(self, args: dict[str, Any]) -> None:
        for key in [
            "north_inflow_min",
            "main_net_inflow_min",
            "margin_balance_delta_min",
            "institution_holding_ratio_min",
            "top_list_score_min",
        ]:
            self._set_number("capital", key, args.get(key))

    def _tool_set_sentiment_conditions(self, args: dict[str, Any]) -> None:
        self._set_int("sentiment", "days", args.get("days"), min_value=1, max_value=60)
        self._set_number("sentiment", "min_avg_score", args.get("min_avg_score"), min_value=0, max_value=100)
        labels: list[str] = []
        for item in self._ensure_list(args.get("include_labels")):
            normalized = SENTIMENT_LABEL_ALIASES.get(str(item).strip())
            if normalized and normalized not in labels:
                labels.append(normalized)
            elif item:
                self.warnings.append(f"未知舆情标签 {item}，已忽略。")
        if labels:
            self.data["sentiment"]["include_labels"] = labels
        for key in ["whitelist_keywords", "blacklist_keywords"]:
            values = [str(item).strip() for item in self._ensure_list(args.get(key)) if str(item).strip()]
            if values:
                self.data["sentiment"][key] = values
        ratio = self._num(args.get("max_negative_ratio"))
        if ratio is not None:
            self.data["sentiment"]["max_negative_ratio"] = min(1.0, max(0.0, ratio / 100 if ratio > 1 else ratio))

    def _tool_set_risk_filters(self, args: dict[str, Any]) -> None:
        for key in ["exclude_st", "exclude_paused"]:
            if key in args and args.get(key) is not None:
                self.data["filters"][key] = self._bool(args.get(key), default=True)
        self._set_int("filters", "new_stock_days", args.get("new_stock_days"), min_value=0, max_value=5000)
        self._set_number("filters", "min_market_cap", args.get("min_market_cap"), min_value=0)

    def _tool_set_score_weights(self, args: dict[str, Any]) -> None:
        for key in ["fundamental", "technical", "capital", "sentiment"]:
            self._set_number("weights", key, args.get(key), min_value=0, max_value=100)

    def _tool_set_result_limit(self, args: dict[str, Any]) -> None:
        limit = self._int(args.get("limit"), min_value=1, max_value=500)
        if limit is not None:
            self.data["limit"] = limit

    def _apply_text_safety_defaults(self, user_text: str) -> None:
        """对常见高风险短语做确定性补强，防止模型漏掉用户明确表达的排除条件。"""
        text = str(user_text or "")
        blacklist = set(self.data["sentiment"].get("blacklist_keywords") or [])
        for keyword in ["暴雷", "退市", "减持", "立案", "监管问询", "诉讼", "业绩预警"]:
            if keyword in text:
                blacklist.add(keyword)
        if blacklist:
            self.data["sentiment"]["blacklist_keywords"] = sorted(blacklist)
        if "利好" in text and not self.data["sentiment"].get("include_labels"):
            self.data["sentiment"]["include_labels"] = ["重大利好", "普通利好"]

    def _set_range(
        self,
        section: str,
        field_name: str,
        min_raw: Any,
        max_raw: Any,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> None:
        min_num = self._num(min_raw)
        max_num = self._num(max_raw)
        if min_num is None and max_num is None:
            return
        if min_num is not None and min_value is not None:
            min_num = max(min_value, min_num)
        if min_num is not None and max_value is not None:
            min_num = min(max_value, min_num)
        if max_num is not None and min_value is not None:
            max_num = max(min_value, max_num)
        if max_num is not None and max_value is not None:
            max_num = min(max_value, max_num)
        if min_num is not None and max_num is not None and min_num > max_num:
            self.warnings.append(f"{section}.{field_name} 最小值大于最大值，已自动交换。")
            min_num, max_num = max_num, min_num
        self.data.setdefault(section, {})[field_name] = {"min": min_num, "max": max_num}

    def _set_number(
        self,
        section: str,
        key: str,
        value: Any,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> None:
        number = self._num(value)
        if number is None:
            return
        if min_value is not None:
            number = max(min_value, number)
        if max_value is not None:
            number = min(max_value, number)
        self.data.setdefault(section, {})[key] = number

    def _set_int(
        self,
        section: str,
        key: str,
        value: Any,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> None:
        number = self._int(value, min_value=min_value, max_value=max_value)
        if number is not None:
            self.data.setdefault(section, {})[key] = number

    def _set_cross(self, section: str, key: str, value: Any) -> None:
        if value is None or value == "":
            return
        normalized = TECHNICAL_CROSS_ALIASES.get(str(value).strip().lower()) or TECHNICAL_CROSS_ALIASES.get(str(value).strip())
        if normalized:
            self.data.setdefault(section, {})[key] = normalized
        else:
            self.warnings.append(f"{key} 只支持金叉/死叉，收到 {value}，已忽略。")

    @staticmethod
    def _normalize_tool_calls(raw_calls: Any) -> list[dict[str, Any]]:
        if isinstance(raw_calls, dict) and "tool_calls" in raw_calls:
            raw_calls = raw_calls.get("tool_calls")
        elif isinstance(raw_calls, dict) and "calls" in raw_calls:
            raw_calls = raw_calls.get("calls")
        elif isinstance(raw_calls, dict) and raw_calls.get("name"):
            raw_calls = [raw_calls]
        if not isinstance(raw_calls, list):
            return []

        result: list[dict[str, Any]] = []
        for item in raw_calls:
            if not isinstance(item, dict):
                continue
            function = item.get("function") if isinstance(item.get("function"), dict) else {}
            name = item.get("name") or function.get("name")
            arguments = item.get("arguments", function.get("arguments", {}))
            if isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                except Exception:
                    try:
                        parsed = extract_json(arguments)
                    except Exception:
                        parsed = {}
                arguments = parsed if isinstance(parsed, dict) else {}
            result.append({"name": name, "arguments": arguments if isinstance(arguments, dict) else {}})
        return result

    @classmethod
    def _normalize_index_code(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        direct = INDEX_ALIASES.get(text) or INDEX_ALIASES.get(text.upper())
        if direct:
            return direct
        for alias, code in INDEX_ALIASES.items():
            if alias and alias.lower() in text.lower():
                return code
        if re.fullmatch(r"\d{6}\.(SH|SZ|BJ|SI)", text, flags=re.I):
            return text.upper()
        if re.fullmatch(r"CONCEPT_[A-Z_]+", text, flags=re.I):
            return text.upper()
        return ""

    @staticmethod
    def _normalize_fundamental_field(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        key = re.sub(r"[\s_\-/()（）]", "", text).lower()
        if key in FUNDAMENTAL_FIELD_ALIASES:
            return FUNDAMENTAL_FIELD_ALIASES[key]
        if text in FUNDAMENTAL_FIELD_ALIASES:
            return FUNDAMENTAL_FIELD_ALIASES[text]
        return ""

    @staticmethod
    def _ensure_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple | set):
            return list(value)
        text = str(value).strip()
        if not text:
            return []
        if re.search(r"[,，、/;\s]", text):
            return [part for part in re.split(r"[,，、/;\s]+", text) if part]
        return [text]

    @staticmethod
    def _num(value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, int | float):
            return float(value)
        text = str(value).strip()
        if text.lower() in {"none", "null", "nan"}:
            return None
        text = text.replace("%", "").replace("亿", "").replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None

    @classmethod
    def _int(cls, value: Any, min_value: int | None = None, max_value: int | None = None) -> int | None:
        number = cls._num(value)
        if number is None:
            return None
        integer = int(round(number))
        if min_value is not None:
            integer = max(min_value, integer)
        if max_value is not None:
            integer = min(max_value, integer)
        return integer

    @staticmethod
    def _bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "是", "开启", "剔除"}:
            return True
        if text in {"0", "false", "no", "n", "否", "关闭", "不剔除"}:
            return False
        return default

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._jsonable(item) for item in value]
        if isinstance(value, tuple | set):
            return [cls._jsonable(item) for item in value]
        return value
