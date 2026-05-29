from agent_redteam.llm.usage import (
    estimate_usage_cost,
    format_cost_estimate,
    format_usage_summary,
    summarize_usage,
    summarize_usage_by_model,
)


def test_summarize_openai_responses_usage_counts_cached_tokens() -> None:
    summary = summarize_usage(
        [
            {
                "input_tokens": 2358,
                "input_tokens_details": {"cached_tokens": 512},
                "output_tokens": 54,
                "output_tokens_details": {"reasoning_tokens": 7},
                "total_tokens": 2412,
            }
        ]
    )

    assert summary.requests == 1
    assert summary.input_tokens == 2358
    assert summary.billable_input_tokens == 1846
    assert summary.cached_input_tokens == 512
    assert summary.output_tokens == 54
    assert summary.reasoning_tokens == 7
    assert summary.total_tokens == 2412
    assert summary.cache_hit_rate == 512 / 2358


def test_summarize_chat_completions_usage_counts_cached_tokens() -> None:
    summary = summarize_usage(
        [
            {
                "prompt_tokens": 2000,
                "prompt_tokens_details": {"cached_tokens": 1600},
                "completion_tokens": 300,
                "completion_tokens_details": {"reasoning_tokens": 10},
                "total_tokens": 2300,
            }
        ]
    )

    assert summary.input_tokens == 2000
    assert summary.billable_input_tokens == 400
    assert summary.cached_input_tokens == 1600
    assert summary.output_tokens == 300
    assert summary.reasoning_tokens == 10
    assert format_usage_summary(summary) == (
        "requests=1, input=2000, billable_input=400, cached_input=1600 (80.0%), "
        "output=300, total=2300, reasoning=10"
    )


def test_summarize_usage_by_model_and_estimate_cost() -> None:
    by_model = summarize_usage_by_model(
        [
            {
                "provider": "openai",
                "model": "gpt-5.5",
                "input_tokens": 2000,
                "input_tokens_details": {"cached_tokens": 1000},
                "output_tokens": 500,
                "total_tokens": 2500,
            },
            {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250929",
                "input_tokens": 1000,
                "cache_read_input_tokens": 2000,
                "cache_creation_input_tokens": 500,
                "output_tokens": 300,
            },
        ]
    )

    openai_group = next(group for group in by_model if group.model == "gpt-5.5")
    openai_cost = estimate_usage_cost(
        by_model[openai_group],
        provider=openai_group.provider,
        model=openai_group.model,
    )
    assert openai_cost is not None
    assert format_cost_estimate(openai_cost).startswith("cost≈$0.0205")

    anthropic_group = next(group for group in by_model if group.provider == "anthropic")
    anthropic_cost = estimate_usage_cost(
        by_model[anthropic_group],
        provider=anthropic_group.provider,
        model=anthropic_group.model,
    )
    assert anthropic_cost is not None
    assert format_cost_estimate(anthropic_cost).startswith("cost≈$0.009975")
