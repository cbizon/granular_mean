from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


TRUE_VALUES = {"1", "true", "yes"}
NESTED_SANDBOX_BYPASS_ENVIRONMENT = (
    "GRANULAR_MEAN_CODEX_BYPASS_NESTED_SANDBOX"
)


def _json_type(value: object) -> str | None:
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return None


def strict_output_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [strict_output_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    converted = {
        key: strict_output_schema(item)
        for key, item in value.items()
        if key != "uniqueItems"
    }
    properties = converted.get("properties")
    if isinstance(properties, dict):
        required = converted.get("required", [])
        required_names = set(required) if isinstance(required, list) else set()
        converted["properties"] = {
            key: item
            for key, item in properties.items()
            if key in required_names
        }
        converted["required"] = [
            key for key in properties if key in required_names
        ]
        converted["additionalProperties"] = False

    if "type" not in converted and "const" in converted:
        inferred = _json_type(converted["const"])
        if inferred is not None:
            converted["type"] = inferred
    if "type" not in converted and isinstance(converted.get("enum"), list):
        inferred_types = {
            inferred
            for item in converted["enum"]
            if (inferred := _json_type(item)) is not None
        }
        if len(inferred_types) == 1:
            converted["type"] = inferred_types.pop()
    return converted


def _prepare_output_schema(arguments: list[str]) -> list[str]:
    try:
        schema_index = arguments.index("--output-schema") + 1
    except ValueError:
        return arguments
    if schema_index >= len(arguments):
        raise RuntimeError("Codex --output-schema argument has no value")

    source = Path(arguments[schema_index])
    schema = json.loads(source.read_text())
    codex_home = Path(os.environ.get("CODEX_HOME", source.parent))
    destination = codex_home / "brunner-strict-output-schema.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(strict_output_schema(schema), indent=2) + "\n"
    )
    arguments[schema_index] = str(destination)
    return arguments


def _bypass_nested_sandbox(arguments: list[str]) -> list[str]:
    prepared: list[str] = []
    sandbox_found = False
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument != "--sandbox":
            prepared.append(argument)
            index += 1
            continue
        if index + 1 >= len(arguments):
            raise RuntimeError("Codex --sandbox argument has no value")
        sandbox_found = True
        index += 2

    if "exec" not in prepared:
        return prepared
    exec_index = prepared.index("exec")
    is_resume = (
        exec_index + 1 < len(prepared)
        and prepared[exec_index + 1] == "resume"
    )
    if not sandbox_found and not is_resume:
        raise RuntimeError("Codex command does not include --sandbox")
    prepared.insert(
        exec_index + 1,
        "--dangerously-bypass-approvals-and-sandbox",
    )
    return prepared


def prepare_arguments(arguments: list[str]) -> list[str]:
    prepared = list(arguments)
    if os.environ.get(
        NESTED_SANDBOX_BYPASS_ENVIRONMENT,
        "false",
    ).lower() in TRUE_VALUES:
        prepared = _bypass_nested_sandbox(prepared)
    return _prepare_output_schema(prepared)


def main() -> None:
    os.execvp(
        "codex",
        ("codex", *prepare_arguments(sys.argv[1:])),
    )


if __name__ == "__main__":
    main()
