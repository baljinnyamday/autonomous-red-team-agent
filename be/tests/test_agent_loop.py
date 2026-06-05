import asyncio
import time
from pathlib import Path

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.loop import AgentLoop, AgentLoopLimits
from agent_redteam.llm.fake import FakeProviderHarness
from agent_redteam.llm.types import AgentMessage, ModelEvent
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import Transport
from agent_redteam.tools.bash import bash_definition, bash_tool
from agent_redteam.tools.executor import ToolExecutor
from agent_redteam.tools.fake import build_test_tool_registry, slow_echo, slow_echo_definition
from agent_redteam.tools.registry import ToolRegistry
from agent_redteam.tools.types import ToolCall


def test_loop_executes_tool_then_sends_result_to_next_turn() -> None:
    provider = FakeProviderHarness(
        [
            [
                ModelEvent(
                    event_type="tool_call",
                    tool_call=ToolCall(
                        call_id="call_1",
                        name="echo_json",
                        arguments={"value": "ok"},
                    ),
                )
            ],
            [ModelEvent(event_type="message_done", content="done")],
        ]
    )
    loop = AgentLoop(provider=provider, tool_registry=build_test_tool_registry())

    result = asyncio.run(loop.run(_context(), [AgentMessage(role="user", content="echo")]))

    assert result.success is True
    assert result.final_message == "done"
    assert [tool_result.output for tool_result in result.tool_results] == ['{"value": "ok"}']
    assert provider.requests[1].messages[-1].provider_metadata["call_id"] == "call_1"


def test_tool_executor_preserves_order_and_runs_unsafe_tools_exclusively() -> None:
    executor = ToolExecutor(build_test_tool_registry())
    parallel_calls = [
        ToolCall(
            call_id="call_1",
            name="slow_echo",
            arguments={"message": "first", "delay": 0.1},
        ),
        ToolCall(
            call_id="call_2",
            name="slow_echo",
            arguments={"message": "second", "delay": 0.1},
        ),
    ]

    start = time.perf_counter()
    parallel_results = asyncio.run(executor.execute_batch(_context(), parallel_calls))
    parallel_elapsed = time.perf_counter() - start

    unsafe_registry = ToolRegistry()
    unsafe_registry.register(slow_echo_definition(parallel_safe=False), slow_echo)
    unsafe_executor = ToolExecutor(unsafe_registry)

    start = time.perf_counter()
    unsafe_results = asyncio.run(unsafe_executor.execute_batch(_context(), parallel_calls))
    unsafe_elapsed = time.perf_counter() - start

    assert parallel_elapsed < 0.18
    assert unsafe_elapsed >= 0.18
    assert [result.output for result in parallel_results] == ["first", "second"]
    assert [result.output for result in unsafe_results] == ["first", "second"]


def test_tool_executor_returns_model_visible_errors_and_runs_bash(tmp_path: Path) -> None:
    registry = build_test_tool_registry()
    registry.register(bash_definition(), bash_tool)
    executor = ToolExecutor(registry)

    results = asyncio.run(
        executor.execute_batch(
            _bash_context(tmp_path),
            [
                ToolCall(call_id="call_1", name="missing_tool", arguments={}),
                ToolCall(call_id="call_2", name="echo_json", arguments={}),
                ToolCall(
                    call_id="call_3",
                    name="bash",
                    arguments={"host": "operator", "command": "printf hello"},
                ),
            ],
        )
    )

    assert results[0].error == "unknown_tool"
    assert "not registered" in results[0].output
    assert results[1].error == "validation_error"
    assert "failed validation" in results[1].output
    assert results[2].success is True
    assert "exit_code=0" in results[2].output
    assert "hello" in results[2].output


def test_bash_allows_rm_command(tmp_path: Path) -> None:
    protected_file = tmp_path / "protected.txt"
    protected_file.write_text("keep", encoding="utf-8")

    output = asyncio.run(
        bash_tool(
            _bash_context(tmp_path),
            ToolCall(
                call_id="call_1",
                name="bash",
                arguments={"host": "operator", "command": f"rm {protected_file}"},
            ),
        )
    )

    assert not protected_file.exists()
    assert "exit_code=0" in output


def test_bash_allows_rm_as_plain_text(tmp_path: Path) -> None:
    output = asyncio.run(
        bash_tool(
            _bash_context(tmp_path),
            ToolCall(
                call_id="call_1",
                name="bash",
                arguments={"host": "operator", "command": "printf rm"},
            ),
        )
    )

    assert "exit_code=0" in output
    assert "stdout:\nrm" in output


def test_loop_stops_at_max_iterations() -> None:
    provider = FakeProviderHarness(
        [
            [
                ModelEvent(
                    event_type="tool_call",
                    tool_call=ToolCall(
                        call_id="call_1",
                        name="echo_json",
                        arguments={"value": "one"},
                    ),
                )
            ],
            [
                ModelEvent(
                    event_type="tool_call",
                    tool_call=ToolCall(
                        call_id="call_2",
                        name="echo_json",
                        arguments={"value": "two"},
                    ),
                )
            ],
        ]
    )
    loop = AgentLoop(
        provider=provider,
        tool_registry=build_test_tool_registry(),
        limits=AgentLoopLimits(max_iterations=2),
    )

    result = asyncio.run(loop.run(_context(), [AgentMessage(role="user", content="loop")]))

    assert result.success is False
    assert result.error == "Agent loop exceeded max iterations (2)."


def _context() -> AgentContext:
    return AgentContext(engagement_id="engagement-1", metadata={})


def _bash_context(tmp_path: Path) -> AgentContext:
    from agent_redteam.core.config import Settings
    from agent_redteam.targets.store import EngagementStore

    state = EngagementState(
        engagement_id="engagement-1",
        hosts={"operator": HostRuntime(transport=Transport.LOCAL)},
    )
    db_path = tmp_path / "engagement-loop-test.db"
    store = EngagementStore.connect(db_path)
    store.save_state(state)
    return AgentContext(
        engagement_id="engagement-1",
        metadata={
            "engagement_state": state,
            "settings": Settings(_env_file=None),
            "engagement_store": store,
            "engagement_db_path": str(db_path),
        },
    )
