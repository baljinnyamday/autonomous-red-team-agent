from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UsageSummary:
    requests: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    @property
    def cache_hit_rate(self) -> float | None:
        if self.input_tokens <= 0:
            return None
        return self.cached_input_tokens / self.input_tokens


def summarize_usage(usages: Iterable[Mapping[str, Any]]) -> UsageSummary:
    requests = 0
    input_tokens = 0
    cached_input_tokens = 0
    cache_write_input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    total_tokens = 0

    for usage in usages:
        requests += 1
        event_input = _first_number(usage, ("input_tokens", "prompt_tokens"))
        event_output = _first_number(usage, ("output_tokens", "completion_tokens"))

        input_tokens += event_input
        output_tokens += event_output
        total_tokens += _first_number(usage, ("total_tokens",)) or event_input + event_output
        cached_input_tokens += _cached_input_tokens(usage)
        cache_write_input_tokens += _number(usage.get("cache_creation_input_tokens"))
        reasoning_tokens += _reasoning_tokens(usage)

    return UsageSummary(
        requests=requests,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_input_tokens=cache_write_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
    )


def format_usage_summary(summary: UsageSummary) -> str:
    if summary.requests == 0:
        return "no usage events"

    parts = [
        f"requests={summary.requests}",
        f"input={summary.input_tokens}",
        f"cached_input={summary.cached_input_tokens}",
    ]
    if summary.cache_hit_rate is not None:
        parts[-1] += f" ({summary.cache_hit_rate:.1%})"
    if summary.cache_write_input_tokens:
        parts.append(f"cache_write_input={summary.cache_write_input_tokens}")
    parts.extend(
        [
            f"output={summary.output_tokens}",
            f"total={summary.total_tokens}",
        ]
    )
    if summary.reasoning_tokens:
        parts.append(f"reasoning={summary.reasoning_tokens}")
    return ", ".join(parts)


def _cached_input_tokens(usage: Mapping[str, Any]) -> int:
    return (
        _nested_number(usage, "input_tokens_details", "cached_tokens")
        + _nested_number(usage, "prompt_tokens_details", "cached_tokens")
        + _number(usage.get("cache_read_input_tokens"))
    )


def _reasoning_tokens(usage: Mapping[str, Any]) -> int:
    return _nested_number(usage, "output_tokens_details", "reasoning_tokens") + _nested_number(
        usage,
        "completion_tokens_details",
        "reasoning_tokens",
    )


def _first_number(usage: Mapping[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = _number(usage.get(key))
        if value:
            return value
    return 0


def _nested_number(usage: Mapping[str, Any], object_key: str, value_key: str) -> int:
    details = usage.get(object_key)
    if not isinstance(details, Mapping):
        return 0
    return _number(details.get(value_key))


def _number(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
