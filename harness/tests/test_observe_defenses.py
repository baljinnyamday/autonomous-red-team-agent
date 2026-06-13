from agent_redteam.tools.observe_defenses import (
    build_probe_command,
    observe_defenses_definition,
    parse_defense_probe,
)

_PROBE_OUTPUT = """==PROCS==
sshd
falcon-sensor
bash
==TOOLS==
auditctl
ufw
==ACTIVE==
auditd=active
fail2ban=inactive
"""


def test_observe_defenses_schema_is_strict_openai_compatible() -> None:
    schema = observe_defenses_definition().input_schema
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(properties.keys())
    assert "default" not in properties["host"]


def test_parse_defense_probe_detects_edr_logging_and_firewall() -> None:
    defenses = parse_defense_probe(_PROBE_OUTPUT)
    detected = {(d.category, d.name) for d in defenses if d.present}
    assert detected == {
        ("edr", "crowdstrike-falcon"),
        ("logging", "auditd"),
        ("firewall", "ufw"),
    }
    # active service status wins over mere installation
    auditd = next(d for d in defenses if d.name == "auditd")
    assert auditd.detail == "service active"


def test_parse_defense_probe_empty_when_nothing_runs() -> None:
    assert parse_defense_probe("==PROCS==\nbash\n==TOOLS==\n==ACTIVE==\n") == []


def test_build_probe_command_is_unprivileged_and_sectioned() -> None:
    command = build_probe_command()
    assert "==PROCS==" in command and "==TOOLS==" in command and "==ACTIVE==" in command
    assert "ps -eo comm=" in command
    assert "sudo" not in command
