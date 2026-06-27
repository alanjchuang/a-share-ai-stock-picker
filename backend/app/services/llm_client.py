from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.core.config import LlmConfig, load_settings


class LlmClient:
    """OpenAI-compatible LLM client with retry and JSON extraction."""

    def __init__(self, config: LlmConfig | None = None) -> None:
        self.config = config or load_settings().llm

    @property
    def available(self) -> bool:
        return bool(self.config.api_base and self.config.api_key and self.config.model and self.config.provider != "heuristic")

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float | None = None) -> dict[str, Any]:
        content = self.chat_text(system_prompt, user_prompt, temperature=temperature, json_mode=True)
        raw = extract_json(content)
        if not isinstance(raw, dict):
            raise ValueError("LLM未返回JSON对象")
        return raw

    def chat_tool_calls(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        temperature: float | None = None,
    ) -> list[dict[str, Any]]:
        """调用OpenAI兼容的function calling，并兼容不支持tools的模型。

        可靠性重点不在于完全相信模型参数，而是把模型输出收敛成“工具调用计划”，
        后续再由业务侧builtin tools做字段白名单、类型转换和Pydantic校验。
        """
        if not self.available:
            raise RuntimeError("LLM未配置或当前provider为heuristic")
        url = self.config.api_base.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens,
            "tools": tools,
            "tool_choice": "auto",
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        last_error: Exception | None = None
        retries = max(1, self.config.num_retries)
        tools_disabled = False
        for attempt in range(retries):
            try:
                if tools_disabled:
                    return self._chat_tool_calls_via_json(system_prompt, user_prompt, tools, temperature=temperature)
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                message = response.json()["choices"][0]["message"]
                calls = self._extract_tool_calls_from_message(message)
                if calls:
                    return calls
                content = str(message.get("content") or "")
                return self._extract_tool_calls_from_content(content)
            except httpx.HTTPStatusError as exc:
                body = exc.response.text
                if not tools_disabled and exc.response.status_code == 400 and ("tool" in body.lower() or "function" in body.lower()):
                    tools_disabled = True
                    continue
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(min(2**attempt, 8))
            except Exception as exc:
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"LLM工具调用失败：{last_error}") from last_error

    def chat_text(self, system_prompt: str, user_prompt: str, temperature: float | None = None, json_mode: bool = False) -> str:
        if not self.available:
            raise RuntimeError("LLM未配置或当前provider为heuristic")
        url = self.config.api_base.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        last_error: Exception | None = None
        retries = max(1, self.config.num_retries)
        response_format_disabled = False
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                return str(response.json()["choices"][0]["message"]["content"])
            except httpx.HTTPStatusError as exc:
                body = exc.response.text
                if json_mode and not response_format_disabled and exc.response.status_code == 400 and "response_format" in body:
                    payload.pop("response_format", None)
                    response_format_disabled = True
                    continue
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(min(2**attempt, 8))
            except Exception as exc:
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"LLM调用失败：{last_error}") from last_error

    def _chat_tool_calls_via_json(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        temperature: float | None = None,
    ) -> list[dict[str, Any]]:
        tool_names = [str(item.get("function", {}).get("name")) for item in tools]
        schema_prompt = f"""
当前模型接口不支持原生function calling。请改为只输出JSON对象：
{{
  "tool_calls": [
    {{"name": "工具名", "arguments": {{"参数名": "参数值"}}}}
  ]
}}

允许的工具名：{json.dumps(tool_names, ensure_ascii=False)}
原始任务：
{user_prompt}
"""
        content = self.chat_text(system_prompt, schema_prompt, temperature=temperature, json_mode=True)
        return self._extract_tool_calls_from_content(content)

    @staticmethod
    def _extract_tool_calls_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
        raw_calls = message.get("tool_calls") or []
        result: list[dict[str, Any]] = []
        for item in raw_calls:
            function = item.get("function") if isinstance(item, dict) else None
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = extract_json(arguments)
            result.append({"name": name, "arguments": arguments if isinstance(arguments, dict) else {}})
        legacy = message.get("function_call")
        if isinstance(legacy, dict):
            arguments = legacy.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = extract_json(arguments)
            result.append({"name": legacy.get("name"), "arguments": arguments if isinstance(arguments, dict) else {}})
        return result

    @staticmethod
    def _extract_tool_calls_from_content(content: str) -> list[dict[str, Any]]:
        if not content.strip():
            return []
        raw = extract_json(content)
        if isinstance(raw, dict):
            calls = raw.get("tool_calls") or raw.get("calls")
            if isinstance(calls, list):
                return [item for item in calls if isinstance(item, dict)]
            if raw.get("name"):
                return [raw]
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        return []


def extract_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        object_match = re.search(r"\{.*\}", content, re.S)
        if object_match:
            return json.loads(object_match.group(0))
        array_match = re.search(r"\[.*\]", content, re.S)
        if array_match:
            return json.loads(array_match.group(0))
        raise
