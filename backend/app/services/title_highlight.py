from __future__ import annotations

import json
from typing import Any, Iterable


TitleHighlightRange = dict[str, int]


def normalize_highlight_ranges(title: str, ranges: Iterable[dict[str, Any]]) -> list[TitleHighlightRange]:
    """Normalize Unicode code-point [start, end) ranges for a title."""
    valid: list[TitleHighlightRange] = []
    title_length = len(title)
    for item in ranges:
        start = item.get("start")
        end = item.get("end")
        if type(start) is not int or type(end) is not int:
            raise ValueError("제목 강조 범위는 정수여야 합니다.")
        if start < 0 or end <= start or end > title_length:
            raise ValueError("제목 강조 범위가 올바르지 않습니다.")
        if title[start:end].isspace():
            continue
        valid.append({"start": start, "end": end})

    valid.sort(key=lambda item: (item["start"], item["end"]))
    merged: list[TitleHighlightRange] = []
    for item in valid:
        if merged and item["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    return merged


def legacy_highlight_range(title: str, highlight: str) -> list[TitleHighlightRange]:
    start = title.find(highlight) if highlight else -1
    if start < 0:
        return []
    return [{"start": start, "end": start + len(highlight)}]


def load_highlight_ranges(title: str, value: str | None) -> list[TitleHighlightRange]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    try:
        return normalize_highlight_ranges(title, parsed)
    except ValueError:
        return []


def dump_highlight_ranges(title: str, ranges: Iterable[dict[str, Any]]) -> str:
    return json.dumps(normalize_highlight_ranges(title, ranges), ensure_ascii=False, separators=(",", ":"))
