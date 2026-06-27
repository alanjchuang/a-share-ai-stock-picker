from __future__ import annotations

import json
from typing import Any

from app.core.config import load_settings
from app.models.schemas import MarketPromptRequest, MarketPromptResponse
from app.services.llm_client import LlmClient


class MarketPromptService:
    """生成适合市场情报检索的搜索Prompt。

    这里刻意不做规则兜底，避免在未配置LLM时伪装成AI结果。
    """

    def __init__(self) -> None:
        self.settings = load_settings()
        self.llm = LlmClient(self.settings.llm)

    def generate(self, payload: MarketPromptRequest) -> MarketPromptResponse:
        if not self.llm.available:
            raise RuntimeError("AI生成市场情报Prompt需要先配置LLM：请在系统配置填写 Provider、API地址、API Key 和模型名")

        count = max(1, min(payload.count, 10))
        raw = self.llm.chat_json(
            "你是A股市场情报检索Prompt规划专家，只生成搜索查询词，不做荐股和投资建议。",
            self._prompt(payload, count),
            temperature=0.4,
        )
        prompts = self._clean_prompts(raw.get("prompts"), count)
        if not prompts:
            raise RuntimeError("LLM未返回可用的市场情报Prompt")
        return MarketPromptResponse(
            prompts=prompts,
            reason=str(raw.get("reason") or "已结合用户输入生成可用于网页/网页摘要检索的市场情报Prompt。")[:500],
        )

    @staticmethod
    def _prompt(payload: MarketPromptRequest, count: int) -> str:
        seed = payload.seed_query.strip() or "A股今日市场情报"
        focus = (payload.focus or "").strip() or "全市场、政策、资金、行业主线、风险事件"
        return f"""
请基于用户输入生成 {count} 条适合火山搜索/网页搜索的中文检索Prompt。

用户输入：{seed}
关注方向：{focus}

要求：
1. 每条都围绕A股市场情报，不输出个股买卖建议。
2. 覆盖政策催化、资金流向、行业主线、业绩预期、风险事件、海外映射等不同角度。
3. 检索词要短而精准，适合直接放进搜索框，优先包含“A股”“今日/近期/最新”等时间词。
4. 不要编造新闻事实，不要生成股票代码清单。
5. 只输出JSON对象，格式如下：
{{
  "prompts": ["A股 今日 政策 资金面 行业机会", "..."],
  "reason": "生成逻辑"
}}
"""

    @staticmethod
    def _clean_prompts(raw_prompts: Any, count: int) -> list[str]:
        if isinstance(raw_prompts, str):
            try:
                raw_prompts = json.loads(raw_prompts)
            except json.JSONDecodeError:
                raw_prompts = [line.strip("- 0123456789.、") for line in raw_prompts.splitlines()]
        if not isinstance(raw_prompts, list):
            return []

        prompts: list[str] = []
        seen: set[str] = set()
        for item in raw_prompts:
            prompt = str(item or "").strip()
            if not prompt:
                continue
            prompt = " ".join(prompt.replace("\n", " ").split())
            if len(prompt) > 120:
                prompt = prompt[:120].rstrip()
            key = prompt.lower()
            if key in seen:
                continue
            seen.add(key)
            prompts.append(prompt)
            if len(prompts) >= count:
                break
        return prompts
