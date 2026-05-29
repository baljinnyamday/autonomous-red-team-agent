from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

TOKENS_PER_MILLION = Decimal("1000000")
PRICING_SOURCE_DATE = "2026-05-29"


@dataclass(frozen=True)
class UsageSummary:
    requests: int = 0
    input_tokens: int = 0
    billable_input_tokens: int = 0
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


@dataclass(frozen=True, order=True)
class UsageGroup:
    provider: str
    model: str


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    input_per_million: Decimal
    cached_input_per_million: Decimal | None
    output_per_million: Decimal
    cache_write_per_million: Decimal | None = None
    note: str = "standard API pricing"
    source_date: str = PRICING_SOURCE_DATE


@dataclass(frozen=True)
class CostEstimate:
    input_usd: Decimal
    cached_input_usd: Decimal
    cache_write_usd: Decimal
    output_usd: Decimal
    total_usd: Decimal
    pricing: ModelPricing


_MODEL_PRICING: tuple[ModelPricing, ...] = (
    ModelPricing(
        provider="openai",
        model="gpt-5.5",
        input_per_million=Decimal("5.00"),
        cached_input_per_million=Decimal("0.50"),
        output_per_million=Decimal("30.00"),
        note="standard short-context API pricing",
    ),
    ModelPricing(
        provider="openai",
        model="gpt-5.5-pro",
        input_per_million=Decimal("30.00"),
        cached_input_per_million=None,
        output_per_million=Decimal("180.00"),
        note="standard short-context API pricing",
    ),
    ModelPricing(
        provider="openai",
        model="gpt-5.4",
        input_per_million=Decimal("2.50"),
        cached_input_per_million=Decimal("0.25"),
        output_per_million=Decimal("15.00"),
        note="standard short-context API pricing",
    ),
    ModelPricing(
        provider="openai",
        model="gpt-5.4-mini",
        input_per_million=Decimal("0.75"),
        cached_input_per_million=Decimal("0.075"),
        output_per_million=Decimal("4.50"),
        note="standard API pricing",
    ),
    ModelPricing(
        provider="openai",
        model="gpt-5.4-nano",
        input_per_million=Decimal("0.20"),
        cached_input_per_million=Decimal("0.02"),
        output_per_million=Decimal("1.25"),
        note="standard API pricing",
    ),
    ModelPricing(
        provider="openai",
        model="gpt-5.4-pro",
        input_per_million=Decimal("30.00"),
        cached_input_per_million=None,
        output_per_million=Decimal("180.00"),
        note="standard short-context API pricing",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-opus-4-8",
        input_per_million=Decimal("5.00"),
        cached_input_per_million=Decimal("0.50"),
        cache_write_per_million=Decimal("6.25"),
        output_per_million=Decimal("25.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-opus-4-7",
        input_per_million=Decimal("5.00"),
        cached_input_per_million=Decimal("0.50"),
        cache_write_per_million=Decimal("6.25"),
        output_per_million=Decimal("25.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-opus-4-6",
        input_per_million=Decimal("5.00"),
        cached_input_per_million=Decimal("0.50"),
        cache_write_per_million=Decimal("6.25"),
        output_per_million=Decimal("25.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-opus-4-5",
        input_per_million=Decimal("5.00"),
        cached_input_per_million=Decimal("0.50"),
        cache_write_per_million=Decimal("6.25"),
        output_per_million=Decimal("25.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-opus-4-1",
        input_per_million=Decimal("15.00"),
        cached_input_per_million=Decimal("1.50"),
        cache_write_per_million=Decimal("18.75"),
        output_per_million=Decimal("75.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_per_million=Decimal("3.00"),
        cached_input_per_million=Decimal("0.30"),
        cache_write_per_million=Decimal("3.75"),
        output_per_million=Decimal("15.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-sonnet-4-5",
        input_per_million=Decimal("3.00"),
        cached_input_per_million=Decimal("0.30"),
        cache_write_per_million=Decimal("3.75"),
        output_per_million=Decimal("15.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-sonnet-4",
        input_per_million=Decimal("3.00"),
        cached_input_per_million=Decimal("0.30"),
        cache_write_per_million=Decimal("3.75"),
        output_per_million=Decimal("15.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-haiku-4-5",
        input_per_million=Decimal("1.00"),
        cached_input_per_million=Decimal("0.10"),
        cache_write_per_million=Decimal("1.25"),
        output_per_million=Decimal("5.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
    ModelPricing(
        provider="anthropic",
        model="claude-haiku-3-5",
        input_per_million=Decimal("0.80"),
        cached_input_per_million=Decimal("0.08"),
        cache_write_per_million=Decimal("1.00"),
        output_per_million=Decimal("4.00"),
        note="standard API pricing with 5m cache-write rate",
    ),
)


def summarize_usage(usages: Iterable[Mapping[str, Any]]) -> UsageSummary:
    requests = 0
    input_tokens = 0
    billable_input_tokens = 0
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
        billable_input_tokens += _billable_input_tokens(usage, event_input)
        output_tokens += event_output
        total_tokens += _first_number(usage, ("total_tokens",)) or event_input + event_output
        cached_input_tokens += _cached_input_tokens(usage)
        cache_write_input_tokens += _number(usage.get("cache_creation_input_tokens"))
        reasoning_tokens += _reasoning_tokens(usage)

    return UsageSummary(
        requests=requests,
        input_tokens=input_tokens,
        billable_input_tokens=billable_input_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_input_tokens=cache_write_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
    )


def summarize_usage_by_model(
    usages: Iterable[Mapping[str, Any]],
    *,
    default_provider: str | None = None,
    default_model: str | None = None,
) -> dict[UsageGroup, UsageSummary]:
    grouped: dict[UsageGroup, list[Mapping[str, Any]]] = {}
    for usage in usages:
        group = usage_group(usage, default_provider=default_provider, default_model=default_model)
        grouped.setdefault(group, []).append(usage)
    return {group: summarize_usage(items) for group, items in grouped.items()}


def usage_group(
    usage: Mapping[str, Any],
    *,
    default_provider: str | None = None,
    default_model: str | None = None,
) -> UsageGroup:
    provider = _string(usage.get("provider")) or default_provider or "unknown"
    model = _string(usage.get("model")) or default_model or "unknown"
    return UsageGroup(provider=provider, model=model)


def format_usage_summary(summary: UsageSummary) -> str:
    if summary.requests == 0:
        return "no usage events"

    parts = [
        f"requests={summary.requests}",
        f"input={summary.input_tokens}",
        f"billable_input={summary.billable_input_tokens}",
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


def estimate_usage_cost(
    summary: UsageSummary,
    *,
    provider: str,
    model: str,
) -> CostEstimate | None:
    pricing = pricing_for_model(provider=provider, model=model)
    if pricing is None:
        return None
    if summary.cached_input_tokens and pricing.cached_input_per_million is None:
        return None
    if summary.cache_write_input_tokens and pricing.cache_write_per_million is None:
        return None

    input_usd = _token_cost(summary.billable_input_tokens, pricing.input_per_million)
    cached_input_usd = _token_cost(
        summary.cached_input_tokens,
        pricing.cached_input_per_million or Decimal("0"),
    )
    cache_write_usd = _token_cost(
        summary.cache_write_input_tokens,
        pricing.cache_write_per_million or Decimal("0"),
    )
    output_usd = _token_cost(summary.output_tokens, pricing.output_per_million)
    total_usd = input_usd + cached_input_usd + cache_write_usd + output_usd
    return CostEstimate(
        input_usd=input_usd,
        cached_input_usd=cached_input_usd,
        cache_write_usd=cache_write_usd,
        output_usd=output_usd,
        total_usd=total_usd,
        pricing=pricing,
    )


def pricing_for_model(*, provider: str, model: str) -> ModelPricing | None:
    normalized_provider = _normalize_provider(provider)
    normalized_model = _normalize_model(model)
    for pricing in _MODEL_PRICING:
        if pricing.provider == normalized_provider and pricing.model == normalized_model:
            return pricing
    return None


def format_cost_estimate(estimate: CostEstimate) -> str:
    parts = [
        f"cost≈{_format_usd(estimate.total_usd)}",
        f"input={_format_usd(estimate.input_usd)}",
        f"cached={_format_usd(estimate.cached_input_usd)}",
    ]
    if estimate.cache_write_usd:
        parts.append(f"cache_write={_format_usd(estimate.cache_write_usd)}")
    parts.append(f"output={_format_usd(estimate.output_usd)}")
    parts.append(f"pricing={estimate.pricing.note}")
    parts.append(f"pricing_date={estimate.pricing.source_date}")
    return ", ".join(parts)


def _cached_input_tokens(usage: Mapping[str, Any]) -> int:
    return (
        _nested_number(usage, "input_tokens_details", "cached_tokens")
        + _nested_number(usage, "prompt_tokens_details", "cached_tokens")
        + _number(usage.get("cache_read_input_tokens"))
    )


def _billable_input_tokens(usage: Mapping[str, Any], input_tokens: int) -> int:
    nested_cached_tokens = _nested_number(
        usage,
        "input_tokens_details",
        "cached_tokens",
    ) + _nested_number(usage, "prompt_tokens_details", "cached_tokens")
    if nested_cached_tokens:
        return max(input_tokens - nested_cached_tokens, 0)
    return input_tokens


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


def _string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_provider(provider: str) -> str:
    provider = provider.lower().strip()
    if provider in {"openai_responses", "openai-response", "openai_response"}:
        return "openai"
    return provider


def _normalize_model(model: str) -> str:
    normalized = model.lower().strip()
    if normalized.startswith("claude-"):
        parts = normalized.split("-")
        if parts[-1].isdecimal() and len(parts[-1]) == 8:
            normalized = "-".join(parts[:-1])
    return normalized


def _token_cost(tokens: int, per_million: Decimal) -> Decimal:
    return Decimal(tokens) * per_million / TOKENS_PER_MILLION


def _format_usd(value: Decimal) -> str:
    if value == 0:
        return "$0"
    if value < Decimal("0.01"):
        return f"${value.quantize(Decimal('0.000001'))}"
    return f"${value.quantize(Decimal('0.0001'))}"
