from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from agent_redteam.cli.prompt import SlashCompleter


def _complete(completer: SlashCompleter, text: str) -> list[str]:
    document = Document(text, cursor_position=len(text))
    return [completion.text for completion in completer.get_completions(document, CompleteEvent())]


def test_slash_completer_suggests_matching_commands() -> None:
    completer = SlashCompleter(["analysis", "help"])

    assert _complete(completer, "/") == ["/analysis", "/help"]
    assert _complete(completer, "/he") == ["/help"]


def test_slash_completer_ignores_non_slash_input() -> None:
    completer = SlashCompleter(["analysis", "help"])

    assert _complete(completer, "ssh into the box") == []
