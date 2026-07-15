"""Data contracts used by the metaprompt and deterministic renderers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from .schema import require_goal_spec_structure


class Target(str, Enum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    CURSOR = "cursor"
    GEMINI = "gemini"

    @classmethod
    def parse(cls, value: str | Target) -> Target:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("target must be a string")
        normalized = value.strip().lower().replace("_", "-")
        aliases = {
            "claude": cls.CLAUDE_CODE,
            "claude-code": cls.CLAUDE_CODE,
            "codex": cls.CODEX,
            "openai-codex": cls.CODEX,
            "cursor": cls.CURSOR,
            "gemini": cls.GEMINI,
            "google-gemini": cls.GEMINI,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            supported = ", ".join(item.value for item in cls)
            raise ValueError(f"Unsupported target {value!r}. Choose one of: {supported}") from exc


def _string(value: Any, field_name: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    result = value.strip()
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _strings(
    value: Iterable[Any] | None,
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        raise TypeError(f"{field_name} must be an array of strings")
    try:
        items = tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an array of strings") from exc
    if any(not isinstance(item, str) for item in items):
        raise TypeError(f"{field_name} must contain only strings")
    result = tuple(item.strip() for item in items)
    if not allow_empty and any(not item for item in result):
        raise ValueError(f"{field_name} cannot contain empty values")
    return result


def _check_keys(
    data: Mapping[str, Any],
    *,
    field_name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - set(data)
    if missing:
        raise ValueError(f"{field_name} is missing required keys: {', '.join(sorted(missing))}")
    unknown = set(data) - required - optional
    if unknown:
        raise ValueError(f"{field_name} has unknown keys: {', '.join(sorted(unknown))}")


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value


@dataclass(frozen=True)
class Reference:
    label: str
    url: str
    purpose: str
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _string(self.label, "reference.label"))
        object.__setattr__(self, "url", _string(self.url, "reference.url"))
        object.__setattr__(self, "purpose", _string(self.purpose, "reference.purpose"))
        object.__setattr__(self, "required", _boolean(self.required, "reference.required"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Reference:
        if not isinstance(data, Mapping):
            raise TypeError("each reference must be an object")
        _check_keys(
            data,
            field_name="reference",
            required={"label", "url", "purpose"},
            optional={"required"},
        )
        return cls(
            label=_string(data.get("label"), "reference.label"),
            url=_string(data.get("url"), "reference.url"),
            purpose=_string(data.get("purpose"), "reference.purpose"),
            required=_boolean(data.get("required", True), "reference.required"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "url": self.url,
            "purpose": self.purpose,
            "required": self.required,
        }


@dataclass(frozen=True)
class OutputContract:
    format: str
    sections: tuple[str, ...] = ()
    include_explanation: bool = True
    verbosity: str = "medium"
    machine_schema: Mapping[str, Any] | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "format", _string(self.format, "output_contract.format"))
        object.__setattr__(
            self,
            "sections",
            _strings(self.sections, "output_contract.sections", allow_empty=True),
        )
        object.__setattr__(
            self,
            "include_explanation",
            _boolean(self.include_explanation, "output_contract.include_explanation"),
        )
        object.__setattr__(self, "verbosity", _string(self.verbosity, "output_contract.verbosity"))
        if self.machine_schema is not None and not isinstance(self.machine_schema, Mapping):
            raise TypeError("output_contract.machine_schema must be an object or null")
        if self.machine_schema is not None:
            object.__setattr__(self, "machine_schema", dict(self.machine_schema))
        object.__setattr__(self, "notes", _string(self.notes, "output_contract.notes"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OutputContract:
        if not isinstance(data, Mapping):
            raise TypeError("output_contract must be an object")
        _check_keys(
            data,
            field_name="output_contract",
            required={"format", "sections", "include_explanation", "verbosity"},
            optional={"machine_schema", "notes"},
        )
        schema = data.get("machine_schema")
        if schema is not None and not isinstance(schema, Mapping):
            raise TypeError("output_contract.machine_schema must be an object or null")
        return cls(
            format=_string(data.get("format"), "output_contract.format"),
            sections=_strings(
                data.get("sections"),
                "output_contract.sections",
                allow_empty=True,
            ),
            include_explanation=_boolean(
                data.get("include_explanation"),
                "output_contract.include_explanation",
            ),
            verbosity=_string(data.get("verbosity"), "output_contract.verbosity"),
            machine_schema=dict(schema) if schema is not None else None,
            notes=_string(data.get("notes", ""), "output_contract.notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "sections": list(self.sections),
            "include_explanation": self.include_explanation,
            "verbosity": self.verbosity,
            "machine_schema": dict(self.machine_schema) if self.machine_schema is not None else None,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class GoalRequest:
    vague_prompt: str
    target: Target
    language: str = "pt-BR"
    context: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    audience: str = ""
    output_preference: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", Target.parse(self.target))
        object.__setattr__(
            self,
            "vague_prompt",
            _string(self.vague_prompt, "vague_prompt", allow_empty=False),
        )
        object.__setattr__(
            self,
            "language",
            _string(self.language, "language", allow_empty=False),
        )
        object.__setattr__(self, "context", _strings(self.context, "context"))
        object.__setattr__(self, "references", _strings(self.references, "references"))
        object.__setattr__(self, "constraints", _strings(self.constraints, "constraints"))
        object.__setattr__(self, "audience", _string(self.audience, "audience"))
        object.__setattr__(
            self,
            "output_preference",
            _string(self.output_preference, "output_preference"),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GoalRequest:
        _check_keys(
            data,
            field_name="request",
            required={"vague_prompt", "target"},
            optional={
                "language",
                "context",
                "references",
                "constraints",
                "audience",
                "output_preference",
            },
        )
        target = _string(data.get("target"), "target", allow_empty=False)
        return cls(
            vague_prompt=_string(data.get("vague_prompt"), "vague_prompt", allow_empty=False),
            target=Target.parse(target),
            language=_string(data.get("language", "pt-BR"), "language", allow_empty=False),
            context=_strings(data.get("context"), "context"),
            references=_strings(data.get("references"), "references"),
            constraints=_strings(data.get("constraints"), "constraints"),
            audience=_string(data.get("audience", ""), "audience"),
            output_preference=_string(
                data.get("output_preference", ""),
                "output_preference",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vague_prompt": self.vague_prompt,
            "target": self.target.value,
            "language": self.language,
            "context": list(self.context),
            "references": list(self.references),
            "constraints": list(self.constraints),
            "audience": self.audience,
            "output_preference": self.output_preference,
        }


@dataclass(frozen=True)
class GoalSpec:
    target: Target
    language: str
    role: str
    goal: str
    success_criteria: tuple[str, ...]
    context: tuple[str, ...]
    inputs: tuple[str, ...]
    references: tuple[Reference, ...]
    constraints: tuple[str, ...]
    non_goals: tuple[str, ...]
    edge_cases: tuple[str, ...]
    output_contract: OutputContract
    assumptions: tuple[str, ...]
    blocking_questions: tuple[str, ...]
    validation_checks: tuple[str, ...]
    version: str = "1.0"

    def __post_init__(self) -> None:
        if isinstance(self.target, Target):
            target = self.target
        elif isinstance(self.target, str):
            target = Target(self.target)
        else:
            raise TypeError("target must be a string")
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "version", _string(self.version, "version"))
        object.__setattr__(self, "language", _string(self.language, "language"))
        object.__setattr__(self, "role", _string(self.role, "role"))
        object.__setattr__(self, "goal", _string(self.goal, "goal"))
        for field_name in (
            "success_criteria",
            "context",
            "inputs",
            "constraints",
            "non_goals",
            "edge_cases",
            "assumptions",
            "blocking_questions",
            "validation_checks",
        ):
            object.__setattr__(
                self,
                field_name,
                _strings(getattr(self, field_name), field_name, allow_empty=True),
            )
        if isinstance(self.references, (str, bytes, Mapping)):
            raise TypeError("references must be an array of objects")
        try:
            references = tuple(self.references)
        except TypeError as exc:
            raise TypeError("references must be an array of objects") from exc
        if any(not isinstance(item, Reference) for item in references):
            raise TypeError("references must contain only Reference objects")
        object.__setattr__(self, "references", references)
        if not isinstance(self.output_contract, OutputContract):
            raise TypeError("output_contract must be an OutputContract")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GoalSpec:
        require_goal_spec_structure(data)
        references_data = data.get("references", ())
        output_data = cast(Mapping[str, Any], data.get("output_contract"))
        return cls(
            version=_string(data.get("version"), "version"),
            target=Target(_string(data.get("target"), "target")),
            language=_string(data.get("language"), "language"),
            role=_string(data.get("role"), "role"),
            goal=_string(data.get("goal"), "goal"),
            success_criteria=_strings(
                data.get("success_criteria"),
                "success_criteria",
                allow_empty=True,
            ),
            context=_strings(data.get("context"), "context", allow_empty=True),
            inputs=_strings(data.get("inputs"), "inputs", allow_empty=True),
            references=tuple(Reference.from_dict(item) for item in references_data),
            constraints=_strings(data.get("constraints"), "constraints", allow_empty=True),
            non_goals=_strings(data.get("non_goals"), "non_goals", allow_empty=True),
            edge_cases=_strings(data.get("edge_cases"), "edge_cases", allow_empty=True),
            output_contract=OutputContract.from_dict(output_data),
            assumptions=_strings(data.get("assumptions"), "assumptions", allow_empty=True),
            blocking_questions=_strings(
                data.get("blocking_questions"),
                "blocking_questions",
                allow_empty=True,
            ),
            validation_checks=_strings(
                data.get("validation_checks"),
                "validation_checks",
                allow_empty=True,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "target": self.target.value,
            "language": self.language,
            "role": self.role,
            "goal": self.goal,
            "success_criteria": list(self.success_criteria),
            "context": list(self.context),
            "inputs": list(self.inputs),
            "references": [item.to_dict() for item in self.references],
            "constraints": list(self.constraints),
            "non_goals": list(self.non_goals),
            "edge_cases": list(self.edge_cases),
            "output_contract": self.output_contract.to_dict(),
            "assumptions": list(self.assumptions),
            "blocking_questions": list(self.blocking_questions),
            "validation_checks": list(self.validation_checks),
        }


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message, "severity": self.severity}


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def valid(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            summary = "; ".join(f"{issue.field}: {issue.message}" for issue in self.errors)
            raise ValueError(f"Invalid GoalSpec: {summary}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
        }
