from agent_redteam.llm.claude import ClaudeMessagesHarness
from agent_redteam.llm.openai import OpenAIResponsesHarness
from agent_redteam.tools.patch import apply_patch_tool_definition


def test_provider_fixtures_normalize_tool_calls() -> None:
    openai_events = OpenAIResponsesHarness(model="gpt-test").normalize_output_items(
        [
            {
                "type": "function_call",
                "call_id": "call_openai",
                "name": "echo_json",
                "arguments": '{"value": "ok"}',
            }
        ]
    )
    claude_events = ClaudeMessagesHarness(model="claude-test").normalize_message(
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "echo_json",
                    "input": {"value": "one"},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "slow_echo",
                    "input": {"message": "two", "delay": 0},
                },
            ],
        }
    )

    assert openai_events[0].tool_call is not None
    assert openai_events[0].tool_call.call_id == "call_openai"
    assert openai_events[0].tool_call.arguments == {"value": "ok"}

    claude_tool_calls = [
        event.tool_call for event in claude_events if event.event_type == "tool_call"
    ]
    assert [tool_call.call_id for tool_call in claude_tool_calls if tool_call is not None] == [
        "toolu_1",
        "toolu_2",
    ]


def test_patch_tool_rendering_without_execution() -> None:
    patch_tool = apply_patch_tool_definition("freeform")

    openai_function_tool = OpenAIResponsesHarness(
        model="gpt-test",
        apply_patch_mode="function",
    ).render_tools([patch_tool])[0]
    openai_freeform_tool = OpenAIResponsesHarness(
        model="gpt-test",
        apply_patch_mode="freeform",
    ).render_tools([patch_tool])[0]
    claude_tool = ClaudeMessagesHarness(model="claude-test").render_tools([patch_tool])[0]

    assert openai_function_tool["type"] == "function"
    assert openai_function_tool["parameters"]["properties"]["patchText"]["type"] == "string"
    assert openai_function_tool["strict"] is True
    assert "metadata" not in openai_function_tool
    assert openai_freeform_tool["type"] == "custom"
    assert "metadata" not in openai_freeform_tool
    assert "parameters" not in openai_freeform_tool
    assert set(claude_tool.keys()) == {"name", "description", "input_schema"}
    assert claude_tool["input_schema"]["properties"]["patchText"]["type"] == "string"
