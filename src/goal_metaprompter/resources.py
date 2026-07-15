"""Load the canonical, packaged metaprompt and GoalSpec schema."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

_ASSETS = "goal_metaprompter.assets"


def get_metaprompt_template() -> str:
    """Return the canonical metaprompt template with internal replacement tokens."""
    return files(_ASSETS).joinpath("metaprompt.md").read_text(encoding="utf-8")


def get_goal_spec_schema() -> dict[str, Any]:
    """Return a fresh copy of the canonical GoalSpec JSON Schema."""
    raw = files(_ASSETS).joinpath("goal-spec.schema.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):  # Defensive check for a corrupted package asset.
        raise RuntimeError("packaged GoalSpec schema must contain a JSON object")
    return data
