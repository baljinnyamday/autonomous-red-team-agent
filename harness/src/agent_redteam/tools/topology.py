from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings, get_settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.targets.state import HostRuntime
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import CredentialFinding, ServiceFinding
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

OPERATOR_HOST_ID = "operator"


class ReadTopologyArgs(ToolArgs):
    host: str | None = Field(
        default=None,
        description="Host id to return. Omit scope to return the full topology.",
    )


class UpdateTopologyArgs(ToolArgs):
    host: str = Field(
        description="Unique host id for one machine (e.g. web-10-0-0-12).",
    )
    address: str | None = Field(
        default=None,
        description="Machine IP or hostname. Required when first recording a new remote host.",
    )
    user: str | None = Field(default=None, description="SSH login user for remote hosts.")
    via: list[str] | None = Field(
        default=None,
        description="Jump host ids required to reach this host, in order.",
    )
    discovered_from: str | None = Field(
        default=None,
        description=(
            "Host id this machine was discovered or reached from (provenance). "
            "Must be an existing host. Set once when first recording the host."
        ),
    )
    os: str | None = Field(default=None, description="Operating system fingerprint.")
    hostname: str | None = Field(
        default=None,
        description="Observed system hostname (distinct from host id).",
    )
    arch: str | None = Field(default=None, description="CPU architecture (e.g. x86_64).")
    tags: list[str] = Field(
        default_factory=list,
        description="Role or classification tags (e.g. web, compromised).",
    )
    services: list[ServiceFinding] = Field(
        default_factory=list,
        description="Discovered services or web endpoints on this host.",
    )
    credentials: list[CredentialFinding] = Field(
        default_factory=list,
        description="Discovered credentials, keys, or secrets for this host.",
    )
    note: str | None = Field(default=None, description="Free-form finding note to append.")
    overwrite_connection: bool = Field(
        default=False,
        description="Allow changing address, user, or via on an existing host.",
    )


def read_topology_definition() -> ToolDefinition:
    return ToolDefinition(
        name="read_topology",
        description=(
            "Read the engagement topology: host ids, connection fields, and discovered "
            "findings (services, credentials, tags, notes).\n\n"
            "Usage:\n"
            "- Call before update_topology to avoid duplicate host ids or addresses.\n"
            "- Set host to filter one machine; leave null for the full topology."
        ),
        input_schema=tool_input_schema(ReadTopologyArgs),
        input_model=ReadTopologyArgs,
        parallel_safe=True,
        mutating=False,
    )


def update_topology_definition() -> ToolDefinition:
    return ToolDefinition(
        name="update_topology",
        description=(
            "Record a discovered machine or append findings to a known host. One host id "
            "maps to one machine.\n\n"
            "Usage:\n"
            "- Call read_topology first.\n"
            "- New remote hosts require a unique address (IP). Never reuse a host id for "
            "a different machine.\n"
            "- Existing hosts accept appended tags, services, credentials, and notes only "
            "unless overwrite_connection is true.\n"
            "- Remote execution is inferred from address/user/via; never set transport."
        ),
        input_schema=tool_input_schema(UpdateTopologyArgs),
        input_model=UpdateTopologyArgs,
        parallel_safe=False,
        mutating=True,
    )


async def read_topology_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = ReadTopologyArgs.model_validate(tool_call.arguments or {})
    store = _require_engagement_store(context)
    settings = _settings_from_context(context)
    engagement_id = context.engagement_id or settings.engagement_id
    # Read from SQLite (the source of truth) so the report reflects findings written
    # this session, then refresh the cached state for the system-prompt topology block.
    state = store.load_state(engagement_id)
    context.metadata["engagement_state"] = state
    return state.topology_report(host_id=arguments.host)


async def update_topology_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = UpdateTopologyArgs.model_validate(tool_call.arguments or {})
    store = _require_engagement_store(context)
    settings = _settings_from_context(context)
    engagement_id = context.engagement_id or settings.engagement_id

    _validate_discovered_from(store, engagement_id, arguments)

    exists = store.host_exists(engagement_id, arguments.host)
    if exists:
        _apply_existing_host_update(store, engagement_id, arguments)
    else:
        _create_host(store, engagement_id, arguments)

    if arguments.tags:
        store.add_tags(engagement_id, arguments.host, arguments.tags)
    if arguments.services:
        store.add_services(engagement_id, arguments.host, arguments.services)
    if arguments.credentials:
        store.add_credentials(engagement_id, arguments.host, arguments.credentials)
    if arguments.note:
        store.add_note(engagement_id, arguments.host, arguments.note)

    state = store.load_state(engagement_id)
    context.metadata["engagement_state"] = state
    return (
        f"Recorded topology for {arguments.host}: "
        f"tags={len(arguments.tags)} services={len(arguments.services)} "
        f"credentials={len(arguments.credentials)}" + (" note_added=yes" if arguments.note else "")
    )


def _create_host(store: EngagementStore, engagement_id: str, arguments: UpdateTopologyArgs) -> None:
    if arguments.host != OPERATOR_HOST_ID and not arguments.address:
        msg = (
            f"New host {arguments.host!r} requires address so one host id binds one machine. "
            "Call read_topology and reuse the existing host id if this machine is already recorded."
        )
        raise ConfigurationError(msg)

    if arguments.address:
        existing_id = store.find_host_id_by_address(engagement_id, arguments.address)
        if existing_id:
            msg = (
                f"address {arguments.address!r} is already recorded as host_id {existing_id!r}. "
                f"Use that id to append findings instead of creating {arguments.host!r}."
            )
            raise ConfigurationError(msg)

    store.upsert_host(
        engagement_id,
        arguments.host,
        address=arguments.address,
        user=arguments.user,
        via=arguments.via,
        discovered_from=arguments.discovered_from,
        os=arguments.os,
        hostname=arguments.hostname,
        arch=arguments.arch,
    )


def _validate_discovered_from(
    store: EngagementStore,
    engagement_id: str,
    arguments: UpdateTopologyArgs,
) -> None:
    origin = arguments.discovered_from
    if origin is None:
        return
    if origin == arguments.host:
        msg = f"discovered_from cannot point at the host itself ({origin!r})."
        raise ConfigurationError(msg)
    if not store.host_exists(engagement_id, origin):
        msg = (
            f"discovered_from {origin!r} is not a known host. Record the origin host first, "
            "or use an existing host id you already hold."
        )
        raise ConfigurationError(msg)


def _apply_existing_host_update(
    store: EngagementStore,
    engagement_id: str,
    arguments: UpdateTopologyArgs,
) -> None:
    state = store.load_state(engagement_id)
    existing = state.hosts[arguments.host]

    if arguments.host == OPERATOR_HOST_ID and _connection_fields_provided(arguments):
        msg = "Cannot change operator connection fields via update_topology."
        raise ConfigurationError(msg)

    if arguments.overwrite_connection:
        if arguments.address:
            owner = store.find_host_id_by_address(engagement_id, arguments.address)
            if owner and owner != arguments.host:
                msg = f"address {arguments.address!r} is already recorded as host_id {owner!r}."
                raise ConfigurationError(msg)
        store.upsert_host(
            engagement_id,
            arguments.host,
            address=arguments.address,
            user=arguments.user,
            via=arguments.via,
            discovered_from=arguments.discovered_from,
            os=arguments.os,
            hostname=arguments.hostname,
            arch=arguments.arch,
        )
        return

    conflicts = _connection_conflicts(existing, arguments)
    if conflicts:
        msg = (
            f"Connection fields are immutable for existing host {arguments.host!r}. "
            "Append findings only, or set overwrite_connection=true. "
            f"Conflicts: {', '.join(conflicts)}"
        )
        raise ConfigurationError(msg)

    if arguments.address:
        owner = store.find_host_id_by_address(engagement_id, arguments.address)
        if owner and owner != arguments.host:
            msg = f"address {arguments.address!r} is already recorded as host_id {owner!r}."
            raise ConfigurationError(msg)

    store.fill_missing_host_fields(
        engagement_id,
        arguments.host,
        address=arguments.address,
        user=arguments.user,
        via=arguments.via,
        discovered_from=arguments.discovered_from,
        os=arguments.os,
        hostname=arguments.hostname,
        arch=arguments.arch,
    )


def _connection_fields_provided(arguments: UpdateTopologyArgs) -> bool:
    return any(
        (
            arguments.address is not None,
            arguments.user is not None,
            arguments.via is not None,
        )
    )


def _connection_conflicts(existing: HostRuntime, arguments: UpdateTopologyArgs) -> list[str]:
    conflicts: list[str] = []
    if arguments.address is not None and arguments.address != existing.address:
        conflicts.append(f"address: {existing.address!r} -> {arguments.address!r}")
    if arguments.user is not None and arguments.user != existing.user:
        conflicts.append(f"user: {existing.user!r} -> {arguments.user!r}")
    if arguments.via is not None and arguments.via != existing.via:
        conflicts.append(f"via: {existing.via!r} -> {arguments.via!r}")
    return conflicts


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
