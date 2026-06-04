import shlex

RM_COMMAND_WARNING = "Command blocked: the 'rm' command is not allowed."
SSH_COMMAND_WARNING = (
    "Command blocked: do not invoke ssh in commands. Use exec(host=...) for remote hosts."
)
SHELL_SEPARATORS = {";", "&&", "||", "|", "(", ")"}
SHELL_COMMAND_WRAPPERS = {"command", "exec", "nohup", "time"}
SHELLS_WITH_COMMAND_ARG = {"bash", "sh", "zsh"}


def contains_rm_command(command: str) -> bool:
    tokens = _shell_tokens(command)
    index = 0
    expect_command = True

    while index < len(tokens):
        token = tokens[index]
        if token in SHELL_SEPARATORS:
            expect_command = True
            index += 1
            continue

        if token in {"-exec", "-execdir"} and _next_token_is_rm(tokens, index):
            return True

        if not expect_command:
            index += 1
            continue

        if _is_assignment(token):
            index += 1
            continue

        command_name = _command_name(token)
        if command_name == "rm":
            return True

        wrapper_index = _wrapped_command_index(tokens, index, command_name)
        if wrapper_index != index:
            index = wrapper_index
            continue

        nested_command = _nested_shell_command(tokens, index, command_name)
        if nested_command is not None and contains_rm_command(nested_command):
            return True

        expect_command = False
        index += 1

    return False


def contains_ssh_command(command: str) -> bool:
    tokens = _shell_tokens(command)
    index = 0
    expect_command = True

    while index < len(tokens):
        token = tokens[index]
        if token in SHELL_SEPARATORS:
            expect_command = True
            index += 1
            continue

        if not expect_command:
            index += 1
            continue

        if _is_assignment(token):
            index += 1
            continue

        command_name = _command_name(token)
        if command_name == "ssh":
            return True

        wrapper_index = _wrapped_command_index(tokens, index, command_name)
        if wrapper_index != index:
            index = wrapper_index
            continue

        nested_command = _nested_shell_command(tokens, index, command_name)
        if nested_command is not None and contains_ssh_command(nested_command):
            return True

        expect_command = False
        index += 1

    return False


def _shell_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return command.split()


def _next_token_is_rm(tokens: list[str], index: int) -> bool:
    return index + 1 < len(tokens) and _command_name(tokens[index + 1]) == "rm"


def _command_name(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _is_assignment(token: str) -> bool:
    name, separator, _ = token.partition("=")
    return (
        bool(separator) and bool(name) and name.replace("_", "").isalnum() and not name[0].isdigit()
    )


def _wrapped_command_index(tokens: list[str], index: int, command_name: str) -> int:
    if command_name in SHELL_COMMAND_WRAPPERS:
        return index + 1
    if command_name == "sudo":
        return _skip_sudo_options(tokens, index + 1)
    if command_name == "env":
        return _skip_env_prefix(tokens, index + 1)
    return index


def _skip_sudo_options(tokens: list[str], index: int) -> int:
    options_with_value = {"-C", "-g", "-h", "-p", "-T", "-t", "-U", "-u"}
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if not token.startswith("-"):
            return index
        index += 2 if token in options_with_value else 1
    return index


def _skip_env_prefix(tokens: list[str], index: int) -> int:
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if token.startswith("-") or _is_assignment(token):
            index += 1
            continue
        return index
    return index


def _nested_shell_command(tokens: list[str], index: int, command_name: str) -> str | None:
    if command_name not in SHELLS_WITH_COMMAND_ARG:
        return None

    for token_index in range(index + 1, len(tokens) - 1):
        token = tokens[token_index]
        if token in SHELL_SEPARATORS:
            return None
        if token.startswith("-") and "c" in token:
            return tokens[token_index + 1]
    return None
