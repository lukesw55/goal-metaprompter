"""Dependency-free validation for the packaged GoalSpec JSON Schema subset."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .resources import _goal_spec_schema


@dataclass(frozen=True)
class SchemaIssue:
    field: str
    message: str


def _type_matches(value: Any, expected: str) -> bool:
    checks = {
        "array": lambda item: isinstance(item, Sequence) and not isinstance(item, (str, bytes)),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
        "object": lambda item: isinstance(item, Mapping),
        "string": lambda item: isinstance(item, str),
    }
    try:
        return checks[expected](value)
    except KeyError as exc:  # The packaged schema only uses the types above.
        raise RuntimeError(f"unsupported schema type: {expected}") from exc


def _join_path(path: str, part: str) -> str:
    return f"{path}.{part}" if path else part


def _uri_issue(value: str) -> str | None:
    if any(
        character.isspace() or ord(character) < 32 or unicodedata.category(character) == "Cf"
        for character in value
    ):
        return "must not contain whitespace, control, or invisible characters"
    try:
        parsed = urlparse(value)
    except ValueError:
        return "is not a parseable URL"
    try:
        _ = parsed.port
    except ValueError:
        return "must contain a valid port"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "must be an absolute http:// or https:// URL with a hostname"
    if parsed.username is not None or parsed.password is not None:
        # user@host lets a trusted-looking prefix mask the real hostname.
        return "must not contain userinfo before the hostname"
    return None


def _collect(
    value: Any,
    schema: Mapping[str, Any],
    path: str,
    issues: list[SchemaIssue],
    *,
    structural_only: bool,
) -> None:
    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else list(expected)
        if not any(_type_matches(value, item) for item in expected_types):
            label = " or ".join(expected_types)
            issues.append(SchemaIssue(path or "$", f"must be of type {label}"))
            return

    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for name in required:
            if name not in value:
                issues.append(SchemaIssue(_join_path(path, name), "is required"))
        if schema.get("additionalProperties") is False:
            for name in sorted(set(value) - set(properties)):
                issues.append(SchemaIssue(_join_path(path, str(name)), "is not allowed"))
        for name, child_schema in properties.items():
            if name in value:
                _collect(
                    value[name],
                    child_schema,
                    _join_path(path, name),
                    issues,
                    structural_only=structural_only,
                )

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if not structural_only and "minItems" in schema and len(value) < schema["minItems"]:
            issues.append(
                SchemaIssue(path or "$", f"must contain at least {schema['minItems']} item(s)")
            )
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _collect(
                    item,
                    item_schema,
                    f"{path}[{index}]",
                    issues,
                    structural_only=structural_only,
                )

    if structural_only:
        return
    if "const" in schema and value != schema["const"]:
        issues.append(SchemaIssue(path or "$", f"must equal {schema['const']!r}"))
    if "enum" in schema and value not in schema["enum"]:
        choices = ", ".join(repr(item) for item in schema["enum"])
        issues.append(SchemaIssue(path or "$", f"must be one of: {choices}"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            issues.append(
                SchemaIssue(path or "$", f"must contain at least {schema['minLength']} character(s)")
            )
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            issues.append(SchemaIssue(path or "$", f"must match pattern {pattern!r}"))
        if schema.get("format") == "uri":
            message = _uri_issue(value)
            if message:
                issues.append(SchemaIssue(path or "$", message))


def validate_goal_spec_data(
    data: Any,
    *,
    structural_only: bool = False,
) -> tuple[SchemaIssue, ...]:
    """Validate data against the canonical packaged schema.

    ``structural_only`` checks types, required keys, nested objects, and unknown keys.
    It is used while parsing so value-level problems remain reportable by ``validate_spec``.
    """
    issues: list[SchemaIssue] = []
    _collect(
        data,
        _goal_spec_schema(),  # cached instance; _collect never mutates it
        "",
        issues,
        structural_only=structural_only,
    )
    return tuple(issues)


def require_goal_spec_structure(data: Any) -> None:
    """Raise a concise error when raw GoalSpec data cannot be parsed safely."""
    issues = validate_goal_spec_data(data, structural_only=True)
    if issues:
        summary = "; ".join(f"{item.field}: {item.message}" for item in issues)
        raise ValueError(f"Invalid GoalSpec structure: {summary}")
