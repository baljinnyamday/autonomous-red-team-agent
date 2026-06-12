from typing import Literal

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings, get_settings
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import AttemptRecord
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

Outcome = Literal["success", "failure", "blocked", "partial"]
_UNPRODUCTIVE = frozenset({"failure", "blocked"})


class RecordAttemptArgs(ToolArgs):
    technique: str = Field(
        description="What was tried (e.g. 'ssh password spray', 'exploit CVE-2017-5638').",
    )
    outcome: Outcome = Field(
        description='Result: "success" | "failure" | "blocked" (stopped by a defense) | "partial".',
    )
    target: str | None = Field(
        default=None,
        description="Topology host id (or address) the attempt was against.",
    )
    detail: str | None = Field(
        default=None,
        description="One line of context: tool, error, or what the defense did.",
    )


def record_attempt_definition() -> ToolDefinition:
    return ToolDefinition(
        name="record_attempt",
        description=(
            "Log an attack attempt and its outcome to the engagement ledger, and get back "
            "what has already been tried so you do not repeat dead ends.\n\n"
            "Usage:\n"
            "- Call after each distinct attempt (exploit, cred spray, pivot) with its outcome.\n"
            "- The returned ledger warns when the same technique/target already failed or was "
            "blocked — pick a different approach instead of retrying.\n"
            '- Use outcome "blocked" when a defense stopped you, so the cost of noise is visible.'
        ),
        input_schema=tool_input_schema(RecordAttemptArgs),
        input_model=RecordAttemptArgs,
        parallel_safe=False,
        mutating=True,
    )


async def record_attempt_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = RecordAttemptArgs.model_validate(tool_call.arguments or {})
    store = _require_engagement_store(context)
    settings = _settings_from_context(context)
    engagement_id = context.engagement_id or settings.engagement_id

    prior = store.list_attempts(engagement_id)
    repeat = _is_unproductive_repeat(prior, arguments)

    store.add_attempt(
        engagement_id,
        AttemptRecord(
            technique=arguments.technique,
            target=arguments.target,
            outcome=arguments.outcome,
            detail=arguments.detail,
        ),
    )
    ledger = store.list_attempts(engagement_id)
    header = (
        "⚠ repeat of a technique/target that already failed or was blocked — change approach.\n"
        if repeat
        else ""
    )
    return header + _format_ledger(ledger)


def _is_unproductive_repeat(prior: list[AttemptRecord], arguments: RecordAttemptArgs) -> bool:
    return any(
        record.technique == arguments.technique
        and record.target == arguments.target
        and record.outcome in _UNPRODUCTIVE
        for record in prior
    )


def _format_ledger(ledger: list[AttemptRecord]) -> str:
    lines = [f"attempts: {len(ledger)}"]
    for record in ledger:
        target = f" -> {record.target}" if record.target else ""
        detail = f" ({record.detail})" if record.detail else ""
        lines.append(f"  [{record.outcome}] {record.technique}{target}{detail}")
    return "\n".join(lines)


def _require_engagement_store(context: AgentContext) -> EngagementStore:
    raw = context.metadata.get("engagement_store")
    if isinstance(raw, EngagementStore):
        return raw
    msg = "engagement_store is missing from agent context metadata."
    raise RuntimeError(msg)


def _settings_from_context(context: AgentContext) -> Settings:
    raw = context.metadata.get("settings")
    if isinstance(raw, Settings):
        return raw
    return get_settings()
