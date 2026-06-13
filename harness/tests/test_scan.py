from agent_redteam.tools.scan import build_scan_command, parse_nmap_grep, scan_definition

_GREP_OUTPUT = """# Nmap 7.94 scan
Host: 10.0.0.10 ()	Status: Up
Host: 10.0.0.10 ()	Ports: 22/open/tcp//ssh//, 80/open/tcp//http//, 443/closed/tcp//https//
# Nmap done
"""


def test_scan_schema_is_strict_openai_compatible() -> None:
    schema = scan_definition().input_schema
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(properties.keys())
    assert properties["host"]["default"] == "operator"
    assert "default" not in properties["target"]


def test_parse_nmap_grep_keeps_only_open_ports() -> None:
    services = parse_nmap_grep(_GREP_OUTPUT)
    assert [(s.port, s.product) for s in services] == [(22, "ssh"), (80, "http")]
    assert all(s.notes == "discovered by scan" for s in services)


def test_build_scan_command_includes_ports_and_falls_back() -> None:
    from agent_redteam.tools.scan import ScanArgs

    command = build_scan_command(ScanArgs(target="10.0.0.10", ports="22,80"))
    assert "nmap -Pn -sV --open -oG - -p 22,80 10.0.0.10" in command
    assert "NMAP_MISSING" in command
