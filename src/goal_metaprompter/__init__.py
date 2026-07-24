"""Public API for Goal Metaprompter."""

from .core import build_metaprompt, render_goal_prompt, validate_goal_spec, validate_spec
from .models import (
    GoalRequest,
    GoalSpec,
    OutputContract,
    Reference,
    Target,
    ValidationIssue,
    ValidationReport,
)
from .resources import get_goal_spec_schema, get_metaprompt_template
from .schema import SchemaIssue, validate_goal_spec_data

__all__ = [
    "GoalRequest",
    "GoalSpec",
    "OutputContract",
    "Reference",
    "Target",
    "ValidationIssue",
    "ValidationReport",
    "SchemaIssue",
    "build_metaprompt",
    "get_goal_spec_schema",
    "get_metaprompt_template",
    "render_goal_prompt",
    "validate_goal_spec",
    "validate_goal_spec_data",
    "validate_spec",
]

__version__ = "0.2.0"
