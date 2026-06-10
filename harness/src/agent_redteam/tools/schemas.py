from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def tool_input_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(by_alias=True)
    _normalize_strict_object_schema(schema)
    return schema


def _normalize_strict_object_schema(node: dict[str, Any]) -> None:
    """Make Pydantic JSON Schema compatible with OpenAI strict function tools.

    Strict mode requires every object to set additionalProperties=false and to
    list all properties in required. Pydantic field defaults are preserved in
    the exported schema so the model sees concrete default values.
    """
    defs = node.get("$defs")
    if isinstance(defs, dict):
        for def_schema in defs.values():
            if isinstance(def_schema, dict):
                _normalize_strict_object_schema(def_schema)

    properties = node.get("properties")
    if node.get("type") == "object" and isinstance(properties, dict):
        node["required"] = list(properties.keys())
        node["additionalProperties"] = False
        for prop_schema in properties.values():
            if isinstance(prop_schema, dict):
                _normalize_strict_object_schema(prop_schema)
