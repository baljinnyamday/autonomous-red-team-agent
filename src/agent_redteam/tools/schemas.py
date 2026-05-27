from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def tool_input_schema(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema(by_alias=True)
