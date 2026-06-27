from __future__ import annotations

import re
from typing import Any

from app.core.config import load_settings
from app.models.schemas import ScreeningRequest
from app.services.llm_client import LlmClient
from app.services.stock_selection_builtin_tools import INDEX_ALIASES, StockSelectionBuiltinTools


class NaturalLanguageParser:
    def parse(self, text: str) -> ScreeningRequest:
        settings = load_settings()
        if LlmClient(settings.llm).available:
            try:
                return self._llm_tool_parse(text)
            except Exception:
                return self._heuristic_parse(text)
        return self._heuristic_parse(text)

    def parse_ai(self, text: str) -> ScreeningRequest:
        settings = load_settings()
        if not LlmClient(settings.llm).available:
            raise RuntimeError("AI解析选股需要先完成配置：LLM 未配置，请在系统配置填写 Provider、API 地址、API Key 和模型名")
        try:
            return self._llm_tool_parse(text, require_calls=True)
        except Exception as exc:
            raise RuntimeError(f"AI解析选股失败：LLM工具调用规划或参数校验失败，请检查API Key、模型名、Workflow和输入条件后重试：{exc}") from exc

    def _heuristic_parse(self, text: str) -> ScreeningRequest:
        data: dict[str, Any] = {
            "logic": "and",
            "index": {"index_codes": [], "require_member": True, "excess_return_days": 20},
            "fundamental": {},
            "technical": {},
            "capital": {},
            "sentiment": {"days": 7},
            "filters": {},
            "weights": load_settings().weights.__dict__,
            "limit": 200,
        }

        for alias, code in INDEX_ALIASES.items():
            if alias in text and code not in data["index"]["index_codes"]:
                data["index"]["index_codes"].append(code)

        self._parse_range(text, data["fundamental"], "pe_ttm", [r"PE[^\d]*(?:低于|小于|<)\s*(\d+(?:\.\d+)?)"], "max")
        self._parse_range(text, data["fundamental"], "pb", [r"PB[^\d]*(?:低于|小于|<)\s*(\d+(?:\.\d+)?)"], "max")
        self._parse_range(text, data["fundamental"], "roe", [r"ROE[^\d]*(?:大于|高于|超过|>)\s*(\d+(?:\.\d+)?)%?"], "min")
        self._parse_range(text, data["fundamental"], "revenue_yoy", [r"(?:营收|收入)[^\d]*(?:增速|同比)?[^\d]*(?:大于|高于|超过|>)\s*(\d+(?:\.\d+)?)%?"], "min")
        self._parse_range(text, data["fundamental"], "debt_to_assets", [r"(?:资产负债率|负债率)[^\d]*(?:低于|小于|<)\s*(\d+(?:\.\d+)?)%?"], "max")

        mv_match = re.search(r"流通市值[^\d]*(\d+(?:\.\d+)?)\s*[-到至~]\s*(\d+(?:\.\d+)?)\s*亿?", text)
        if mv_match:
            data["fundamental"]["circ_mv"] = {"min": float(mv_match.group(1)), "max": float(mv_match.group(2))}
        else:
            self._parse_range(text, data["fundamental"], "circ_mv", [r"流通市值[^\d]*(?:大于|高于|超过|>)\s*(\d+(?:\.\d+)?)\s*亿?"], "min")

        sentiment_match = re.search(r"(?:近)?(\d+)?天?舆情[^\d]*(?:高于|大于|超过|>)\s*(\d+(?:\.\d+)?)", text)
        if sentiment_match:
            data["sentiment"]["days"] = int(sentiment_match.group(1) or 7)
            data["sentiment"]["min_avg_score"] = float(sentiment_match.group(2))
        if "利好" in text:
            data["sentiment"]["include_labels"] = ["重大利好", "普通利好"]
        blacklist = [word for word in ["暴雷", "退市", "减持", "监管问询", "诉讼"] if word in text]
        if blacklist:
            data["sentiment"]["blacklist_keywords"] = blacklist
        whitelist = [word for word in ["算力", "国产替代", "储能", "创新药", "大额订单"] if word in text]
        if whitelist:
            data["sentiment"]["whitelist_keywords"] = whitelist

        if "主力" in text and "流入" in text:
            data["capital"]["main_net_inflow_min"] = 0
        if "北向" in text and "流入" in text:
            data["capital"]["north_inflow_min"] = 0
        if "站上" in text and "均线" in text:
            data["technical"]["above_ma"] = [20, 60]
        if "金叉" in text and "MACD" in text.upper():
            data["technical"]["macd_cross"] = "golden"
        if "近20日" in text and "涨幅" in text:
            self._parse_range(text, data["technical"], "pct_chg_n", [r"近20日[^\d]*(?:涨幅|涨跌幅)[^\d]*(?:大于|高于|超过|>)\s*(\d+(?:\.\d+)?)%?"], "min")
            data["technical"]["pct_chg_days"] = 20

        if "低估" in text:
            data["index"]["max_pe_percentile"] = 35
            data["index"]["max_pb_percentile"] = 35
        if "动量靠前" in text or "赛道动量" in text:
            data["index"]["track_momentum_top_n"] = 3

        return ScreeningRequest.model_validate(data)

    def _llm_parse(self, text: str) -> ScreeningRequest:
        return self._llm_tool_parse(text, require_calls=True)

    def _llm_tool_parse(self, text: str, require_calls: bool = False) -> ScreeningRequest:
        settings = load_settings()
        toolbox = StockSelectionBuiltinTools(settings)
        calls = LlmClient(settings.llm).chat_tool_calls(
            "你是A股自然语言选股Workflow的工具规划Agent。只通过函数工具表达筛选意图。",
            StockSelectionBuiltinTools.planning_prompt(text),
            StockSelectionBuiltinTools.tool_definitions(),
        )
        if require_calls and not calls:
            raise ValueError("LLM未返回任何builtin tool调用")
        result = toolbox.execute(calls, user_text=text)
        return result.request

    @staticmethod
    def _parse_range(text: str, target: dict[str, Any], field: str, patterns: list[str], bound: str) -> None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                target.setdefault(field, {})
                target[field][bound] = float(match.group(1))
                return
