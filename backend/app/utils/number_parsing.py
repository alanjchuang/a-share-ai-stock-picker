from __future__ import annotations

import math
import re
from typing import Any


DEFAULT_SCORE_LABELS = {
    "极高": 90.0,
    "很高": 88.0,
    "高": 85.0,
    "较高": 80.0,
    "偏高": 75.0,
    "中高": 75.0,
    "中等": 65.0,
    "中": 65.0,
    "一般": 55.0,
    "普通": 55.0,
    "中性": 50.0,
    "偏低": 35.0,
    "较低": 35.0,
    "低": 40.0,
    "很低": 25.0,
    "极低": 15.0,
}


def coerce_score(
    value: Any,
    default: float = 50.0,
    *,
    label_map: dict[str, float] | None = None,
    scale_unit_interval: bool = True,
) -> float:
    """Convert loose LLM score text into a bounded 0-100 score."""
    labels = {**DEFAULT_SCORE_LABELS, **(label_map or {})}
    number = _coerce_number(value, labels)
    if number is None:
        number = float(default)
    if scale_unit_interval and 0 < number <= 1:
        number *= 100
    return round(max(0.0, min(number, 100.0)), 1)


def _coerce_number(value: Any, labels: dict[str, float]) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return _finite_float(value)

    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return None

    compact = re.sub(r"\s+", "", text)
    if compact in labels:
        return labels[compact]
    for label, score in sorted(labels.items(), key=lambda item: len(item[0]), reverse=True):
        if label and label in compact:
            return score

    cleaned = compact.replace(",", "").replace("，", "").replace("%", "").replace("分", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    return _finite_float(match.group(0))


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
