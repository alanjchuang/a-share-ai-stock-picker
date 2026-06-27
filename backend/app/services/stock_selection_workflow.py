from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from app.core.config import PROJECT_ROOT, load_settings
from app.models.schemas import (
    ScreeningRequest,
    ScreeningResult,
    StockSelectionWorkflowResult,
    WebSearchRequest,
    WorkflowRunRequest,
    WorkflowStepTrace,
)
from app.services.llm_client import LlmClient
from app.services.nl_parser import INDEX_ALIASES, NaturalLanguageParser
from app.services.screener_service import ScreenerService
from app.services.web_search_service import WebSearchService


class StockSelectionWorkflow:
    """AgentLoom-style sequential workflow for LLM-assisted stock selection."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.settings = load_settings()
        self.llm = LlmClient(self.settings.llm)
        self.parser = NaturalLanguageParser()
        self.screener = ScreenerService(conn)
        self.search = WebSearchService(self.settings.search)

    def list_workflows(self) -> list[dict[str, Any]]:
        workflows_dir = PROJECT_ROOT / "workflows"
        result: list[dict[str, Any]] = []
        default_path = self.settings.workflow.default_path or self._default_workflow_path(required=False)
        for path in sorted(workflows_dir.glob("*.toml")):
            try:
                config = self._load_workflow_config(str(path))
                relative_path = str(path.relative_to(PROJECT_ROOT))
                result.append(
                    {
                        "name": config.get("name", path.stem),
                        "description": config.get("description", ""),
                        "version": config.get("version", ""),
                        "path": relative_path,
                        "is_default": relative_path == default_path or str(path) == default_path,
                        "steps": [
                            {
                                "id": step.get("id"),
                                "name": step.get("name"),
                                "type": step.get("type"),
                                "enabled": bool(step.get("enabled", True)),
                            }
                            for step in config.get("steps", [])
                        ],
                    }
                )
            except Exception as exc:
                result.append({"name": path.stem, "path": str(path), "error": str(exc), "steps": []})
        return result

    def run(self, request: WorkflowRunRequest) -> StockSelectionWorkflowResult:
        if not self.settings.workflow.enabled:
            raise RuntimeError("AI解析选股需要先完成配置：Workflow 未启用，请在系统配置启用 Workflow")

        workflow_path = request.workflow_path or self.settings.workflow.default_path or self._default_workflow_path()
        config = self._load_workflow_config(workflow_path)
        self._validate_ready(config)
        context: dict[str, Any] = {"user_text": request.text}
        traces: list[WorkflowStepTrace] = []

        for step in config.get("steps", []):
            if not step.get("enabled", True):
                traces.append(self._trace(step, "skipped", "步骤已禁用", {}))
                continue
            started = datetime.now()
            try:
                output, summary, status = self._run_step(step, config, context)
                output_key = str(step.get("output_key") or step.get("id"))
                context[output_key] = output
                traces.append(self._trace(step, status, summary, output, started=started))
            except Exception as exc:
                if str(step.get("type") or "").startswith("llm_"):
                    traces.append(self._trace(step, "failed", str(exc), {}, started=started))
                    raise RuntimeError(
                        f"AI解析选股失败：{step.get('name') or step.get('id')} 调用失败，请检查 LLM API Key、模型名和接口权限：{exc}"
                    ) from exc
                fallback = str(step.get("fallback") or "")
                if fallback:
                    output, summary = self._fallback(step, fallback, context, exc)
                    context[str(step.get("output_key") or step.get("id"))] = output
                    traces.append(self._trace(step, "fallback", summary, output, started=started))
                else:
                    traces.append(self._trace(step, "failed", str(exc), {}, started=started))
                    raise

        parsed_request = context.get("screening_request")
        if not isinstance(parsed_request, ScreeningRequest):
            raw = context.get("raw_conditions")
            if raw is None:
                raise RuntimeError("AI解析选股失败：Workflow 未生成结构化筛选条件，请检查 Workflow 步骤配置")
            parsed_request = self._build_request(raw, request.text)
        screening_result = context.get("screening_result")
        if screening_result is not None and not isinstance(screening_result, ScreeningResult):
            screening_result = ScreeningResult.model_validate(screening_result)
        if screening_result is None:
            screening_result = self.screener.run(parsed_request)

        llm_analysis = context.get("llm_analysis")
        if not isinstance(llm_analysis, dict):
            llm_analysis = self._deterministic_summary(request.text, parsed_request, screening_result)

        return StockSelectionWorkflowResult(
            workflow_name=str(config.get("name") or "stock_selection_workflow"),
            workflow_path=self._resolve_path(workflow_path).as_posix(),
            parsed_request=parsed_request,
            screening_result=screening_result,
            llm_analysis=llm_analysis,
            raw_conditions=self._as_dict(context.get("raw_conditions") or parsed_request.model_dump(mode="json")),
            steps=traces,
        )

    def _validate_ready(self, config: dict[str, Any]) -> None:
        enabled_step_types = {str(step.get("type") or "") for step in config.get("steps", []) if step.get("enabled", True)}
        missing: list[str] = []
        if "llm_intent_parse" not in enabled_step_types:
            missing.append("Workflow 缺少启用的 LLM 自然语言解析步骤")
        if any(step_type.startswith("llm_") for step_type in enabled_step_types) and not self.llm.available:
            missing.append("LLM 未配置，请在系统配置填写 Provider、API 地址、API Key 和模型名")
        if missing:
            raise RuntimeError("AI解析选股需要先完成配置：" + "；".join(missing))

    def _run_step(self, step: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> tuple[Any, str, str]:
        step_type = str(step.get("type") or "")
        if step_type == "llm_intent_parse":
            prompt = self._render_prompt(str(step.get("prompt") or ""), context)
            raw = self.llm.chat_json("你是A股选股 workflow 的条件解析 Agent。", prompt)
            return raw, "LLM已输出结构化选股条件", "success"
        if step_type == "condition_guard":
            raw = context.get("raw_conditions")
            parsed = self._build_request(raw, str(context.get("user_text") or ""))
            return parsed, "结构化条件已通过Pydantic校验并补齐默认值", "success"
        if step_type == "screen":
            parsed = context.get("screening_request")
            if not isinstance(parsed, ScreeningRequest):
                parsed = self._build_request(context.get("raw_conditions"), str(context.get("user_text") or ""))
            result = self.screener.run(parsed)
            candidate_limit = int(step.get("candidate_limit") or parsed.limit)
            if candidate_limit and len(result.rows) > candidate_limit:
                result.rows = result.rows[:candidate_limit]
            return result, f"确定性多因子筛选完成，候选 {result.total} 只", "success"
        if step_type == "web_search":
            if not self.search.available:
                return self._empty_search_context("火山搜索未启用或API Key未配置"), "火山搜索未配置，已跳过联网检索", "skipped"
            search_context = {
                **context,
                "candidate_names": "、".join(self._candidate_names(context.get("screening_result"), int(step.get("candidate_limit") or 8))),
                "candidate_ts_codes": "、".join(self._candidate_codes(context.get("screening_result"), int(step.get("candidate_limit") or 8))),
            }
            query_template = str(step.get("query_template") or "{{user_text}} A股 最新 新闻 政策 财报 舆情")
            query = " ".join(self._render_prompt(query_template, search_context).split())[:400]
            if not query:
                return self._empty_search_context("搜索关键词为空"), "搜索关键词为空，已跳过联网检索", "skipped"
            response = self.search.search(
                WebSearchRequest(
                    query=query,
                    count=int(step.get("count") or self.settings.search.default_count),
                    time_range=str(step.get("time_range") or "") or None,
                    search_type=str(step.get("search_type") or self.settings.search.default_search_type or "web"),  # type: ignore[arg-type]
                )
            )
            result_limit = int(step.get("result_limit") or step.get("count") or self.settings.search.default_count)
            output = {
                "provider": response.provider,
                "query": query,
                "search_type": response.search_type,
                "total": response.total,
                "items": WebSearchService.compact_context(response, limit=result_limit),
                "time_cost_ms": response.time_cost_ms,
                "request_ids": response.request_ids,
            }
            return output, f"火山搜索完成，获得 {len(output['items'])} 条可用资料", "success"
        if step_type == "llm_candidate_review":
            parsed = context.get("screening_request")
            screening = context.get("screening_result")
            if not isinstance(parsed, ScreeningRequest):
                parsed = self._build_request(context.get("raw_conditions"), str(context.get("user_text") or ""))
            if not isinstance(screening, ScreeningResult):
                screening = self.screener.run(parsed)
            prompt_context = {
                **context,
                "screening_request_json": json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False),
                "candidate_rows_json": json.dumps(self._candidate_rows(screening, int(step.get("candidate_limit") or 20)), ensure_ascii=False),
                "web_search_context_json": json.dumps(self._jsonable(context.get("web_search_context") or {}), ensure_ascii=False),
            }
            prompt = self._render_prompt(str(step.get("prompt") or ""), prompt_context)
            analysis = self.llm.chat_json("你是A股多因子候选股复核 Agent。", prompt)
            return analysis, "LLM已完成候选股复核", "success"
        raise ValueError(f"未知workflow步骤类型：{step_type}")

    def _fallback(self, step: dict[str, Any], fallback: str, context: dict[str, Any], exc: Exception) -> tuple[Any, str]:
        if fallback == "heuristic_parse":
            raise RuntimeError(f"AI解析选股失败：LLM输出条件无法校验，已停止规则解析兜底：{exc}") from exc
        if fallback == "deterministic_summary":
            raise RuntimeError(f"AI解析选股失败：候选股复核模型调用失败，已停止确定性摘要兜底：{exc}") from exc
        if fallback == "empty_search_context":
            return self._empty_search_context(f"联网搜索失败：{exc}"), f"火山搜索失败，已跳过联网上下文：{exc}"
        raise exc

    def _build_request(self, raw: Any, user_text: str = "") -> ScreeningRequest:
        if isinstance(raw, ScreeningRequest):
            return raw
        if not isinstance(raw, dict):
            raise ValueError("LLM结构化条件为空或格式错误")
        data = raw.copy()
        if user_text:
            data = self._merge_missing(data, self.parser._heuristic_parse(user_text).model_dump(mode="json"))
        data.setdefault("weights", self.settings.weights.__dict__)
        data.setdefault("limit", 200)
        data.setdefault("logic", "and")
        data.setdefault("index", {})
        data.setdefault("fundamental", {})
        data.setdefault("technical", {})
        data.setdefault("capital", {})
        data.setdefault("sentiment", {})
        data.setdefault("filters", {})
        return ScreeningRequest.model_validate(data)

    @classmethod
    def _merge_missing(cls, primary: Any, fallback: Any) -> Any:
        if primary is None:
            return fallback
        if isinstance(primary, dict) and isinstance(fallback, dict):
            merged = primary.copy()
            for key, fallback_value in fallback.items():
                if key not in merged or merged[key] is None:
                    merged[key] = fallback_value
                else:
                    merged[key] = cls._merge_missing(merged[key], fallback_value)
            return merged
        if isinstance(primary, list) and not primary and isinstance(fallback, list):
            return fallback
        return primary

    def _deterministic_summary(self, text: str, parsed: ScreeningRequest, screening: ScreeningResult) -> dict[str, Any]:
        rows = screening.rows[:10]
        return {
            "market_view": f"根据用户需求完成多因子筛选，命中 {screening.total} 只股票。",
            "selection_logic": [
                f"指数池：{','.join(parsed.index.index_codes) or '全市场'}",
                f"权重：基本面{parsed.weights.fundamental}/技术{parsed.weights.technical}/资金{parsed.weights.capital}/舆情{parsed.weights.sentiment}",
                "候选按综合AI评分降序展示",
            ],
            "risk_notes": ["本系统仅做公开数据统计，不构成投资建议", "AKShare/Tushare等公开数据可能存在延迟或临时缺失"],
            "watchlist": [
                {
                    "ts_code": row.ts_code,
                    "name": row.name,
                    "reason": f"AI评分{row.ai_score:.1f}，基本面{row.fundamental_score:.1f}，技术{row.technical_score:.1f}",
                    "risk": row.sentiment_label,
                    "confidence": round(row.ai_score, 1),
                }
                for row in rows
            ],
            "disclaimer": "不构成投资建议",
            "source_text": text,
        }

    def _render_prompt(self, template: str, context: dict[str, Any]) -> str:
        values = {
            "user_text": str(context.get("user_text") or ""),
            "index_aliases_json": json.dumps(INDEX_ALIASES, ensure_ascii=False),
            "default_weights_json": json.dumps(self.settings.weights.__dict__, ensure_ascii=False),
        }
        for key, value in context.items():
            if key not in values:
                values[key] = value if isinstance(value, str) else json.dumps(self._jsonable(value), ensure_ascii=False)
        result = template
        for key, value in values.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result

    def _load_workflow_config(self, path_value: str) -> dict[str, Any]:
        path = self._resolve_path(path_value)
        if not path.exists():
            raise ValueError(f"workflow配置不存在：{path}")
        with path.open("rb") as file:
            return tomllib.load(file)

    @staticmethod
    def _resolve_path(path_value: str) -> Path:
        path = Path(path_value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @staticmethod
    def _default_workflow_path(required: bool = True) -> str:
        workflows = sorted((PROJECT_ROOT / "workflows").glob("*.toml"))
        if workflows:
            return str(workflows[0].relative_to(PROJECT_ROOT))
        if required:
            raise ValueError("未配置Workflow，且 workflows/ 目录下没有可用TOML文件")
        return ""

    def _trace(
        self,
        step: dict[str, Any],
        status: str,
        summary: str,
        output: Any,
        started: datetime | None = None,
    ) -> WorkflowStepTrace:
        started_at = started or datetime.now()
        preview = self._preview(output) if self.settings.workflow.trace_payload_preview else {}
        return WorkflowStepTrace(
            id=str(step.get("id") or ""),
            name=str(step.get("name") or step.get("id") or ""),
            type=str(step.get("type") or ""),
            status=status,  # type: ignore[arg-type]
            started_at=started_at.strftime("%Y-%m-%d %H:%M:%S"),
            finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            summary=summary,
            output_preview=preview,
        )

    def _preview(self, output: Any) -> dict[str, object]:
        if isinstance(output, ScreeningRequest):
            return {"index": output.index.index_codes, "limit": output.limit}
        if isinstance(output, ScreeningResult):
            return {"total": output.total, "rows": [row.model_dump(mode="json") for row in output.rows[:3]]}
        if isinstance(output, dict):
            preview: dict[str, object] = {}
            for key, value in output.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    preview[key] = value
                elif isinstance(value, list):
                    preview[key] = value[:3]
                elif isinstance(value, dict):
                    preview[key] = {k: v for k, v in list(value.items())[:6]}
            return preview
        return {"value": str(output)[:500]}

    @staticmethod
    def _candidate_rows(screening: ScreeningResult, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "ts_code": row.ts_code,
                "name": row.name,
                "industry": row.industry,
                "index_names": row.index_names,
                "pe_ttm": row.pe_ttm,
                "pb": row.pb,
                "roe": row.roe,
                "pct_chg": row.pct_chg,
                "sentiment_score": row.sentiment_score,
                "sentiment_label": row.sentiment_label,
                "fundamental_score": row.fundamental_score,
                "technical_score": row.technical_score,
                "capital_score": row.capital_score,
                "ai_score": row.ai_score,
                "rating": row.rating,
            }
            for row in screening.rows[:limit]
        ]

    @staticmethod
    def _candidate_names(screening: Any, limit: int) -> list[str]:
        if not isinstance(screening, ScreeningResult):
            return []
        return [row.name for row in screening.rows[:limit] if row.name]

    @staticmethod
    def _candidate_codes(screening: Any, limit: int) -> list[str]:
        if not isinstance(screening, ScreeningResult):
            return []
        return [row.ts_code for row in screening.rows[:limit] if row.ts_code]

    @staticmethod
    def _empty_search_context(reason: str) -> dict[str, object]:
        return {
            "provider": "volc-search",
            "query": "",
            "search_type": "web",
            "total": 0,
            "items": [],
            "skipped_reason": reason,
        }

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    @staticmethod
    def _as_dict(value: Any) -> dict[str, object]:
        if isinstance(value, ScreeningRequest):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return value
        return {"value": str(value)}
