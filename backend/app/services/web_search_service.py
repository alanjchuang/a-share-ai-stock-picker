from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.core.config import SearchConfig, load_settings
from app.models.schemas import WebSearchItem, WebSearchRequest, WebSearchResponse


class WebSearchService:
    """火山独立搜索 API 封装，给选股 workflow 提供可追溯的实时资料上下文。"""

    def __init__(self, config: SearchConfig | None = None) -> None:
        self.config = config or load_settings().search

    @property
    def available(self) -> bool:
        api_key = self._api_key()
        return bool(self.config.enabled and self._base_url() and api_key)

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        if not self.config.enabled:
            raise RuntimeError("火山搜索未启用")
        api_key = self._api_key()
        if not api_key:
            raise RuntimeError("火山搜索API Key未配置")

        queries = self._queries(request)
        if not queries:
            raise ValueError("缺少搜索关键词 query 或 queries")

        count = self._count(request.count)
        search_type = (request.search_type or self.config.default_search_type or "web").strip().lower()
        if search_type not in {"web", "image", "web_summary"}:
            raise ValueError(f"不支持的搜索类型：{search_type}")

        items: list[WebSearchItem] = []
        request_ids: list[str] = []
        rag_values: list[str] = []
        time_cost_ms = 0
        last_error: Exception | None = None

        for query in queries:
            try:
                raw = self._post(query, count, search_type, request, api_key)
            except Exception as exc:
                last_error = exc
                continue
            metadata = raw.get("ResponseMetadata") if isinstance(raw.get("ResponseMetadata"), dict) else {}
            request_id = str(metadata.get("RequestId") or "")
            if request_id:
                request_ids.append(request_id)

            result = raw.get("Result") if isinstance(raw.get("Result"), dict) else {}
            time_cost_ms += int(result.get("TimeCost") or 0)
            rag = result.get("Rag")
            if isinstance(rag, str) and rag:
                rag_values.append(rag)

            for item in result.get("WebResults") or []:
                if isinstance(item, dict):
                    parsed = self._web_item(query, item)
                    if parsed:
                        items.append(parsed)
            for item in result.get("ImageResults") or []:
                if isinstance(item, dict):
                    parsed = self._image_item(query, item)
                    if parsed:
                        items.append(parsed)

        if not items and last_error is not None:
            raise RuntimeError(f"火山搜索调用失败：{last_error}") from last_error
        if not items:
            raise RuntimeError("火山搜索未返回可用结果")

        return WebSearchResponse(
            provider=self.config.model or "volc-search",
            search_type=search_type,
            queries=queries,
            total=len(items),
            items=items,
            rag="\n".join(rag_values) or None,
            request_ids=request_ids,
            time_cost_ms=time_cost_ms or None,
        )

    @staticmethod
    def compact_context(response: WebSearchResponse, limit: int = 8) -> list[dict[str, Any]]:
        """压缩成适合塞进候选股复核提示词的上下文，避免把长正文直接灌给模型。"""
        context: list[dict[str, Any]] = []
        for idx, item in enumerate(response.items[: max(1, limit)], start=1):
            text = item.summary or item.snippet or item.content
            context.append(
                {
                    "rank": idx,
                    "query": item.query,
                    "title": item.title,
                    "site": item.site_name,
                    "url": item.url,
                    "publish_time": item.publish_time,
                    "summary": text[:800],
                }
            )
        return context

    def _post(self, query: str, count: int, search_type: str, request: WebSearchRequest, api_key: str) -> dict[str, Any]:
        need_summary = self.config.need_summary if request.need_summary is None else request.need_summary
        need_content = self.config.need_content if request.need_content is None else request.need_content
        payload: dict[str, Any] = {
            "Query": query,
            "SearchType": search_type,
            "Count": count,
            "Filter": {
                "NeedContent": bool(need_content),
                "NeedUrl": True,
            },
            "NeedSummary": bool(need_summary and search_type != "image"),
        }
        if request.time_range:
            payload["TimeRange"] = request.time_range
        if request.sites:
            payload["Filter"]["Sites"] = request.sites

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=max(1, self.config.timeout_seconds)) as client:
            response = client.post(self._base_url(), headers=headers, json=payload)
            if response.status_code < 200 or response.status_code >= 300:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
            raw = self._decode_response(response)
            if not isinstance(raw, dict):
                raise RuntimeError("搜索响应不是JSON对象")
            return raw

    def _decode_response(self, response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()
        text = response.text
        if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
            return self._decode_event_stream(text)
        try:
            raw = response.json()
        except ValueError as exc:
            raise RuntimeError(f"搜索响应不是有效JSON：{self._response_preview(response)}") from exc
        if not isinstance(raw, dict):
            raise RuntimeError("搜索响应不是JSON对象")
        return raw

    @classmethod
    def _decode_event_stream(cls, text: str) -> dict[str, Any]:
        base: dict[str, Any] | None = None
        fallback: dict[str, Any] | None = None
        rag_parts: list[str] = []

        for payload in cls._event_stream_payloads(text):
            if payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"搜索SSE响应包含无效JSON事件：{payload[:200]}") from exc
            if not isinstance(event, dict):
                continue

            fallback = event
            result = event.get("Result") if isinstance(event.get("Result"), dict) else {}
            if base is None and (result.get("WebResults") or result.get("ImageResults")):
                base = event

            rag = result.get("Rag")
            if isinstance(rag, str) and rag:
                rag_parts.append(rag)

            choices = result.get("Choices")
            if isinstance(choices, list):
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("Delta") if isinstance(choice.get("Delta"), dict) else {}
                    content = delta.get("Content")
                    if isinstance(content, str) and content:
                        rag_parts.append(content)

        raw = base or fallback
        if raw is None:
            raise RuntimeError("搜索SSE响应为空")

        if rag_parts:
            result = raw.setdefault("Result", {})
            if isinstance(result, dict):
                existing = result.get("Rag")
                result["Rag"] = (existing if isinstance(existing, str) else "") + "".join(rag_parts)
        return raw

    @staticmethod
    def _event_stream_payloads(text: str) -> list[str]:
        payloads: list[str] = []
        data_lines: list[str] = []
        for line in text.splitlines():
            if not line:
                if data_lines:
                    payloads.append("\n".join(data_lines))
                    data_lines = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                value = line[5:]
                data_lines.append(value[1:] if value.startswith(" ") else value)
        if data_lines:
            payloads.append("\n".join(data_lines))
        return payloads

    @staticmethod
    def _response_preview(response: httpx.Response) -> str:
        text = response.text.strip()
        if not text:
            return f"空响应（Content-Type: {response.headers.get('content-type') or 'unknown'}）"
        return f"Content-Type: {response.headers.get('content-type') or 'unknown'}，响应前缀：{text[:300]}"

    def _queries(self, request: WebSearchRequest) -> list[str]:
        queries = [item.strip() for item in request.queries if item and item.strip()]
        if not queries and request.query and request.query.strip():
            queries.append(request.query.strip())
        return queries

    def _count(self, count: int | None) -> int:
        value = count or self.config.default_count or 8
        return max(1, min(int(value), self.config.max_count or 20, 20))

    def _api_key(self) -> str:
        return (
            os.getenv("VOLC_SEARCH_API_KEY")
            or os.getenv("SEARCH_API_KEY")
            or self.config.api_key
            or ""
        ).strip()

    def _base_url(self) -> str:
        return (os.getenv("VOLC_SEARCH_API_URL") or self.config.base_url or "").strip()

    @staticmethod
    def _web_item(query: str, item: dict[str, Any]) -> WebSearchItem | None:
        title = str(item.get("Title") or "").strip()
        url = str(item.get("Url") or "").strip()
        summary = str(item.get("Summary") or "").strip()
        snippet = str(item.get("Snippet") or "").strip()
        content = str(item.get("Content") or "").strip()
        if not title and not (summary or snippet or content):
            return None
        return WebSearchItem(
            type="web",
            query=query,
            title=title or url,
            url=url,
            site_name=str(item.get("SiteName") or "").strip() or None,
            snippet=snippet,
            summary=summary,
            content=content,
            publish_time=str(item.get("PublishTime") or "").strip() or None,
            rank_score=_float_or_none(item.get("RankScore")),
        )

    @staticmethod
    def _image_item(query: str, item: dict[str, Any]) -> WebSearchItem | None:
        image = item.get("Image") if isinstance(item.get("Image"), dict) else {}
        image_url = str(image.get("Url") or item.get("Url") or "").strip()
        if not image_url:
            return None
        return WebSearchItem(
            type="image",
            query=query,
            title=str(item.get("Title") or image_url).strip(),
            url=str(item.get("Url") or image_url).strip(),
            site_name=str(item.get("SiteName") or "").strip() or None,
            snippet=str(item.get("Snippet") or "").strip(),
            publish_time=str(item.get("PublishTime") or "").strip() or None,
            image_url=image_url,
            image_width=_int_or_none(image.get("Width")),
            image_height=_int_or_none(image.get("Height")),
        )


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return None if value is None or value == "" else int(value)
    except (TypeError, ValueError):
        return None
