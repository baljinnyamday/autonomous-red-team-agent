from dataclasses import dataclass

MAX_OUTPUT_CHARS = 12_000
POLICY_DENIED_EXIT_CODE = 126


@dataclass(frozen=True)
class CommandResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool


def policy_denied(stderr_message: str) -> CommandResult:
    return CommandResult(
        exit_code=POLICY_DENIED_EXIT_CODE,
        stdout=b"",
        stderr=stderr_message.encode(),
        timed_out=False,
    )


def format_command_result(result: CommandResult) -> str:
    output = "\n".join(
        [
            f"exit_code={result.exit_code}",
            f"timed_out={str(result.timed_out).lower()}",
            "stdout:",
            _decode(result.stdout),
            "stderr:",
            _decode(result.stderr),
        ]
    )
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    return output[:MAX_OUTPUT_CHARS] + "\n...[truncated]"


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace").strip()
