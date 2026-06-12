"""
Estimate token usage and cost for each Incalmo run from llm.log.

Incalmo uses LangChain and discards usage_metadata, so we estimate from
logged message text. The model sends the full conversation each turn, so
input tokens accumulate. Heuristic: 4 chars ≈ 1 token (standard for mixed
English + code + JSON).

Sonnet 4.6 pricing (as of 2025):
  Input:  $3.00 / M tokens
  Output: $15.00 / M tokens
  (No cache data available; cache reads would be ~$0.30/M)
"""

import re
from pathlib import Path

CHARS_PER_TOKEN = 4
INPUT_PRICE_PER_M = 3.00
OUTPUT_PRICE_PER_M = 15.00

LOG_SPLIT = re.compile(
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ INFO:"
)

ARTIFACTS = Path(__file__).parent

RUNS = {
    "Dumbbell A":      "dumbbell_a_sonnet46_2026-06-05",
    "Dumbbell B":      "dumbbell_b_sonnet46_2026-06-05",
    "Enterprise A":    "enterprise_a_sonnet46_2026-06-04",
    "Enterprise B R1": "enterprise_b_sonnet46_2026-06-05",
    "Enterprise B R2": "enterprise_b_sonnet46_run2_2026-06-05",
    "Equifax Large":   "equifax_large_sonnet46_2026-06-04",
    "Equifax Small":   "equifax_small_sonnet46_2026-06-04",
    "ICS R1":          "ics_sonnet46_2026-06-04",
    "ICS R2":          "ics_sonnet46_rerun_2026-06-04",
    "Star-6":          "star_6_sonnet46_2026-06-05",
}


def parse_log(path: Path) -> tuple[int, int]:
    """Return (input_tokens_est, output_tokens_est) for one run."""
    text = path.read_text(errors="replace")

    # Split into labelled blocks
    parts = LOG_SPLIT.split(text)
    # parts[0] is empty or pre-log; rest begin with the label text

    input_total_chars = 0
    output_total_chars = 0

    # The first model call has: [system_prompt] + [starter user msg]
    # We capture pre_prompt length from the first "Starting LLM strategy" block
    # and first response to infer it indirectly. Instead we use the log structure:
    #   - "claude-4.6-sonnet response:" = output turn (assistant msg)
    #   - "Incalmo's response:" = next user turn (environment feedback)
    # Input to turn N = system_prompt + all prior user msgs + all prior assistant msgs

    turns_output = []
    turns_user = []

    for part in parts:
        if part.startswith("claude-4.6-sonnet response:"):
            content = part[len("claude-4.6-sonnet response:"):].strip()
            turns_output.append(content)
        elif part.startswith("Incalmo's response:"):
            content = part[len("Incalmo's response:"):].strip()
            turns_user.append(content)

    if not turns_output:
        return 0, 0

    # Reconstruct cumulative input per model call.
    # Turn 0: input = system_prompt + starter_msg (both unlogged; approximate from
    #          first output size as a proxy — we add them later).
    # Turn k: input = system_prompt + user[0..k] + assistant[0..k-1]
    # We don't have the system prompt in the log. Use log file size as conservative
    # lower bound and add 2000 tokens for the fixed preprompt (typical ~8000 chars).
    # Static preprompt: pre_prompt.txt (2552) + codebase.txt (7200) + final_prompt.txt (50)
    # plus initial environment state (~400 chars per host; approximated from first query logs)
    PREPROMPT_CHARS = 9802

    cumulative_user_chars = 0
    cumulative_asst_chars = 0

    for i, asst_msg in enumerate(turns_output):
        # Input this turn: preprompt + all prior context + current user msg
        user_msg_chars = len(turns_user[i]) if i < len(turns_user) else 0
        input_chars = PREPROMPT_CHARS + cumulative_user_chars + user_msg_chars + cumulative_asst_chars
        input_total_chars += input_chars
        output_total_chars += len(asst_msg)
        # Advance cumulative context for next turn
        cumulative_user_chars += user_msg_chars
        cumulative_asst_chars += len(asst_msg)

    input_tokens = input_total_chars // CHARS_PER_TOKEN
    output_tokens = output_total_chars // CHARS_PER_TOKEN
    return input_tokens, output_tokens


def cost_usd(input_tok: int, output_tok: int) -> float:
    return (input_tok * INPUT_PRICE_PER_M + output_tok * OUTPUT_PRICE_PER_M) / 1_000_000


def main():
    print(f"{'Run':<18} {'In (k)':>8} {'Out (k)':>8} {'Total (k)':>10} {'Cost (USD)':>11}")
    print("-" * 60)
    for label, dirname in RUNS.items():
        log = ARTIFACTS / dirname / "incalmo_run" / "llm.log"
        if not log.exists():
            print(f"{label:<18} {'N/A':>8}")
            continue
        inp, out = parse_log(log)
        cost = cost_usd(inp, out)
        print(f"{label:<18} {inp//1000:>7}k {out//1000:>7}k {(inp+out)//1000:>9}k  ${cost:>9.2f}")


if __name__ == "__main__":
    main()
