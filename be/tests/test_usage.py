from agent_redteam.llm.usage import format_usage_summary, summarize_usage


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
    assert summary.cached_input_tokens == 1600
    assert summary.output_tokens == 300
    assert summary.reasoning_tokens == 10
    assert format_usage_summary(summary) == (
        "requests=1, input=2000, cached_input=1600 (80.0%), output=300, total=2300, reasoning=10"
    )
