import re
import shlex

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings, get_settings
from agent_redteam.execution.run_on_host import execute_on_host
from agent_redteam.targets.graph import OPERATOR_HOST_ID
from agent_redteam.targets.state import EngagementState
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import ServiceFinding
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

DEFAULT_SCAN_TIMEOUT_SECONDS = 300.0

# nmap greppable line: "Host: 10.0.0.5 ()\tPorts: 22/open/tcp//ssh//, 80/open/tcp//http//"
_PORTS_FIELD = re.compile(r"Ports:\s*(.+?)(?:\tIgnored|$)")
_NMAP_MISSING = "NMAP_MISSING"


class ScanArgs(ToolArgs):
    host: str = Field(
        default=OPERATOR_HOST_ID,
        description="Topology host id to scan FROM (the vantage point). Defaults to operator.",
    )
    target: str = Field(
        description="IP or hostname to scan.",
    )
    ports: str | None = Field(
        default=None,
        description='Port spec passed to nmap -p (e.g. "22,80,443" or "1-1024"). '
        "Omit for nmap's default top ports.",
    )
    timeout_seconds: float = Field(
        default=DEFAULT_SCAN_TIMEOUT_SECONDS,
        ge=1,
        le=86400,
        description="Wall-clock limit in seconds (1-86400).",
    )


def scan_definition() -> ToolDefinition:
    return ToolDefinition(
        name="scan",
        description=(
            "Port/service scan a target with nmap and record the discovered services into "
            "the engagement topology in one step.\n\n"
            "Usage:\n"
            "- Set host to the vantage point (operator or a foothold) and target to the IP "
            "to scan.\n"
            "- Discovered services attach to the topology host that owns target's address; "
            "record the host with update_topology first if it is new.\n"
            "- Use this instead of bash nmap so findings are never dropped."
        ),
        input_schema=tool_input_schema(ScanArgs),
        input_model=ScanArgs,
        parallel_safe=True,
        mutating=True,
    )


async def scan_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = ScanArgs.model_validate(tool_call.arguments or {})
    state = _require_engagement_state(context)
    store = _require_engagement_store(context)
    settings = _settings_from_context(context)
    engagement_id = context.engagement_id or settings.engagement_id

    command = build_scan_command(arguments)
    result, _state = await execute_on_host(
        state,
        arguments.host,
        command,
        settings,
        timeout_seconds=arguments.timeout_seconds,
    )

    if result.timed_out:
        return "Scan timed out. Narrow ports or raise timeout_seconds."
    stdout = result.stdout.decode("utf-8", errors="replace")
    if _NMAP_MISSING in stdout:
        return "nmap is not installed on the scan host. Install it or fall back to bash."

    services = parse_nmap_grep(stdout)
    if not services:
        return f"Scan of {arguments.target}: no open services found."

    owner = store.find_host_id_by_address(engagement_id, arguments.target)
    if owner is None:
        listing = ", ".join(_describe(service) for service in services)
        return (
            f"Scan of {arguments.target} found {len(services)} service(s): {listing}. "
            "Not recorded: no topology host owns this address. "
            "Record it with update_topology, then scan again."
        )

    store.add_services(engagement_id, owner, services)
    edge_added = _record_scan_provenance(store, engagement_id, owner=owner, vantage=arguments.host)
    context.metadata["engagement_state"] = store.load_state(engagement_id)

    listing = ", ".join(_describe(service) for service in services)
    message = f"Recorded {len(services)} service(s) on {owner} ({arguments.target}): {listing}"
    if edge_added:
        message += f". Graph edge: {arguments.host} -> {owner} (discovered)"
    return message


def build_scan_command(arguments: ScanArgs) -> str:
    port_flag = f"-p {shlex.quote(arguments.ports)}" if arguments.ports else ""
    target = shlex.quote(arguments.target)
    parts = ("nmap", "-Pn", "-sV", "--open", "-oG", "-", port_flag, target)
    nmap = " ".join(part for part in parts if part)
    return f"if command -v nmap >/dev/null 2>&1; then {nmap}; else echo {_NMAP_MISSING}; fi"


def parse_nmap_grep(output: str) -> list[ServiceFinding]:
    services: list[ServiceFinding] = []
    for line in output.splitlines():
        match = _PORTS_FIELD.search(line)
        if not match:
            continue
        for entry in match.group(1).split(","):
            service = _parse_port_entry(entry.strip())
            if service is not None:
                services.append(service)
    return services


def _parse_port_entry(entry: str) -> ServiceFinding | None:
    # greppable port tuple: port/state/proto/owner/service/method/version
    # e.g. "22/open/tcp//ssh//OpenSSH 8.9" -> port=22 service=ssh version="OpenSSH 8.9"
    fields = entry.split("/")
    if len(fields) < 5 or fields[1] != "open":
        return None
    port = int(fields[0]) if fields[0].isdigit() else None
    version = fields[6].strip() if len(fields) > 6 and fields[6].strip() else None
    notes = "discovered by scan" if version is None else f"discovered by scan: {version}"
    return ServiceFinding(
        port=port,
        protocol=fields[2] or None,
        product=fields[4] or None,
        notes=notes,
    )


def _record_scan_provenance(
    store: EngagementStore,
    engagement_id: str,
    *,
    owner: str,
    vantage: str,
) -> bool:
    if owner in (vantage, OPERATOR_HOST_ID):
        return False
    store.fill_missing_host_fields(engagement_id, owner, discovered_from=vantage)
    return True


def _describe(service: ServiceFinding) -> str:
    return f"{service.port}/{service.protocol or '?'} {service.product or 'unknown'}"


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
