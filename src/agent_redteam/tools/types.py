from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

InputMode = Literal["json", "freeform"]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    input_model: type[BaseModel] | None = None
    input_mode: InputMode = "json"
    parallel_safe: bool = True
    mutating: bool = False
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] | None = None
    freeform_input: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    success: bool
    output: str
    error: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
