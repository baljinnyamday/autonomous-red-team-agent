from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings, get_settings
from agent_redteam.execution.run_on_host import execute_on_host
from agent_redteam.targets.state import EngagementState
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import DefenseFinding
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

DEFAULT_OBSERVE_TIMEOUT_SECONDS = 60.0

# Running-process name -> (category, canonical defense name). Matched as substrings.
_PROC_DEFENSES: dict[str, tuple[str, str]] = {
    "falcon": ("edr", "crowdstrike-falcon"),
    "csagent": ("edr", "crowdstrike-falcon"),
    "cbagent": ("edr", "carbon-black"),
    "sentinel": ("edr", "sentinelone"),
    "mdatp": ("edr", "ms-defender"),
    "wdavdaemon": ("edr", "ms-defender"),
    "osqueryd": ("edr", "osquery"),
    "wazuh": ("hids", "wazuh"),
    "ossec": ("hids", "ossec"),
    "clamd": ("av", "clamav"),
}
# Installed CLI -> (category, canonical defense name).
_TOOL_DEFENSES: dict[str, tuple[str, str]] = {
    "auditctl": ("logging", "auditd"),
    "sysmon": ("logging", "sysmon"),
    "fail2ban-client": ("hids", "fail2ban"),
    "aide": ("hids", "aide"),
    "ufw": ("firewall", "ufw"),
    "nft": ("firewall", "nftables"),
    "iptables": ("firewall", "iptables"),
    "snort": ("nids", "snort"),
    "suricata": ("nids", "suricata"),
}
_MAJOR_CATEGORIES = ("edr", "av", "logging", "firewall", "hids", "nids")
_PROBE_TOOLS = list(_TOOL_DEFENSES)


class ObserveDefensesArgs(ToolArgs):
    host: str = Field(
        description="Topology host id to inspect for defenses (EDR, logging, firewall, HIDS).",
    )
    timeout_seconds: float = Field(
        default=DEFAULT_OBSERVE_TIMEOUT_SECONDS,
        ge=1,
        le=3600,
        description="Wall-clock limit in seconds (1-3600).",
    )


def observe_defenses_definition() -> ToolDefinition:
    return ToolDefinition(
        name="observe_defenses",
        description=(
            "Probe a host for defensive controls (EDR/AV agents, audit/sysmon logging, "
            "firewalls, host IDS) and record them on the topology. Read-only, unprivileged "
            "checks (process list, installed tools, service status).\n\n"
            "Usage:\n"
            "- Run after landing on a host and BEFORE noisy actions, so you can adapt to "
            "what is watching.\n"
            "- Findings persist on the host; absence of a control is itself a signal.\n"
            "- Re-running replaces the prior snapshot for that host."
        ),
        input_schema=tool_input_schema(ObserveDefensesArgs),
        input_model=ObserveDefensesArgs,
        parallel_safe=True,
        mutating=True,
    )


async def observe_defenses_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = ObserveDefensesArgs.model_validate(tool_call.arguments or {})
    state = _require_engagement_state(context)
    store = _require_engagement_store(context)
    settings = _settings_from_context(context)
    engagement_id = context.engagement_id or settings.engagement_id

    result, new_state = await execute_on_host(
        state,
        arguments.host,
        build_probe_command(),
        settings,
        timeout_seconds=arguments.timeout_seconds,
    )
    context.metadata["engagement_state"] = new_state
    if result.timed_out:
        return "Defense probe timed out. Raise timeout_seconds and retry."

    stdout = result.stdout.decode("utf-8", errors="replace")
    defenses = parse_defense_probe(stdout)
    store.replace_defenses(engagement_id, arguments.host, defenses)
    context.metadata["engagement_state"] = store.load_state(engagement_id)
    return _summarize(arguments.host, defenses)


def build_probe_command() -> str:
    tools = " ".join(_PROBE_TOOLS)
    return (
        "echo '==PROCS=='; (ps -eo comm= 2>/dev/null || ps -e 2>/dev/null); "
        f"echo '==TOOLS=='; for c in {tools}; do "
        'command -v "$c" >/dev/null 2>&1 && echo "$c"; done; '
        "echo '==ACTIVE=='; for s in auditd fail2ban; do "
        'printf \'%s=\' "$s"; (systemctl is-active "$s" 2>/dev/null || echo unknown); done'
    )


def parse_defense_probe(output: str) -> list[DefenseFinding]:
    sections = _split_sections(output)
    found: dict[tuple[str, str], DefenseFinding] = {}

    procs = sections.get("PROCS", "").lower()
    for needle, (category, name) in _PROC_DEFENSES.items():
        if needle in procs:
            found[(category, name)] = DefenseFinding(
                category=category, name=name, present=True, detail="process running"
            )

    for tool in sections.get("TOOLS", "").split():
        if tool in _TOOL_DEFENSES:
            category, name = _TOOL_DEFENSES[tool]
            found.setdefault(
                (category, name),
                DefenseFinding(category=category, name=name, present=True, detail="installed"),
            )

    for line in sections.get("ACTIVE", "").splitlines():
        name, _, status = line.partition("=")
        if status.strip() == "active":
            found[("logging" if name == "auditd" else "hids", name)] = DefenseFinding(
                category="logging" if name == "auditd" else "hids",
                name=name,
                present=True,
                detail="service active",
            )

    return list(found.values())


def _split_sections(output: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in output.splitlines():
        if line.startswith("==") and line.endswith("=="):
            if current is not None:
                sections[current] = "\n".join(buffer)
            current = line.strip("= ")
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer)
    return sections


def _summarize(host: str, defenses: list[DefenseFinding]) -> str:
    if not defenses:
        return (
            f"{host}: no EDR/logging/firewall/HIDS controls detected on unprivileged probe. "
            "Treat as lightly defended, but deeper controls may need root to see."
        )
    present_categories = {d.category for d in defenses if d.present and d.category}
    detected = ", ".join(f"{d.name} ({d.category})" for d in defenses if d.present)
    absent = [c for c in _MAJOR_CATEGORIES if c not in present_categories]
    absent_note = f" No: {', '.join(absent)}." if absent else ""
    return f"{host} defenses — detected: {detected}.{absent_note}"


def _require_engagement_state(context: AgentContext) -> EngagementState:
    raw = context.metadata.get("engagement_state")
    if isinstance(raw, EngagementState):
        return raw
    msg = "engagement_state is missing from agent context metadata."
    raise RuntimeError(msg)


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
