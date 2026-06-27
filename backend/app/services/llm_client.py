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
