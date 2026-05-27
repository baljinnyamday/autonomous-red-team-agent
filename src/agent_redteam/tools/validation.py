from typing import Any


def validate_json_arguments(arguments: object, schema: dict[str, Any]) -> list[str]:
    """Validate the small JSON Schema subset used by V1 tool definitions."""
    errors: list[str] = []
    _validate_value(arguments, schema, path="$", errors=errors)
    return errors


def _validate_value(value: object, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        errors.append(f"{path} must be {_format_type(expected_type)}")
        return

    enum_values = schema.get("enum")
    if enum_values is not None and value not in enum_values:
        errors.append(f"{path} must be one of {enum_values!r}")
        return

    if expected_type == "object":
        if not isinstance(value, dict):
            return
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}

        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{path}.{key} is required")

        if schema.get("additionalProperties") is False:
            allowed = {key for key in properties if isinstance(key, str)}
            for key in value:
                if key not in allowed:
                    errors.append(f"{path}.{key} is not allowed")

        for key, property_schema in properties.items():
            if key in value and isinstance(property_schema, dict):
                _validate_value(value[key], property_schema, f"{path}.{key}", errors)

    if expected_type == "array":
        if not isinstance(value, list):
            return
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, item_schema, f"{path}[{index}]", errors)


def _matches_type(value: object, expected_type: object) -> bool:
    if isinstance(expected_type, list):
        return any(_matches_type(value, item) for item in expected_type)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _format_type(expected_type: object) -> str:
    if isinstance(expected_type, list):
        return " or ".join(str(item) for item in expected_type)
    return str(expected_type)
