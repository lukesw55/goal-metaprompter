"""Regenerate the renderer snapshots from the specs in tests/data.

Run after an intentional renderer change, then review the diff:

    python tests/update_snapshots.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goal_metaprompter import GoalSpec, Target, render_goal_prompt  # noqa: E402

TESTS = ROOT / "tests"
SPEC_NAMES = ("minimal", "populated")


def main() -> None:
    for name in SPEC_NAMES:
        data = json.loads((TESTS / "data" / f"{name}-spec.json").read_text(encoding="utf-8"))
        for target in Target:
            spec = GoalSpec.from_dict({**data, "target": target.value})
            path = TESTS / "snapshots" / f"{name}-{target.value}.txt"
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(render_goal_prompt(spec))
            print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
