from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goal_metaprompter import GoalSpec, Target, render_goal_prompt  # noqa: E402

SNAPSHOTS = Path(__file__).with_name("snapshots")
DATA = Path(__file__).with_name("data")
SPEC_NAMES = ("minimal", "populated")


def load_spec(name: str, target: Target) -> GoalSpec:
    data = json.loads((DATA / f"{name}-spec.json").read_text(encoding="utf-8"))
    return GoalSpec.from_dict({**data, "target": target.value})


class RendererSnapshotTests(unittest.TestCase):
    def test_renderers_match_reviewed_snapshots(self) -> None:
        for name in SPEC_NAMES:
            for target in Target:
                with self.subTest(spec=name, target=target.value):
                    expected = (SNAPSHOTS / f"{name}-{target.value}.txt").read_text(encoding="utf-8")
                    self.assertEqual(expected, render_goal_prompt(load_spec(name, target)))

    def test_populated_claude_snapshot_escapes_hostile_content(self) -> None:
        result = render_goal_prompt(load_spec("populated", Target.CLAUDE_CODE))

        self.assertIn("&lt;daily&gt;", result)
        self.assertIn("&amp;", result)
        self.assertNotIn("<daily>", result)


if __name__ == "__main__":
    unittest.main()
