from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goal_metaprompter import (  # noqa: E402
    GoalSpec,
    get_goal_spec_schema,
    get_metaprompt_template,
    validate_goal_spec_data,
)


def example_data() -> dict[str, object]:
    return json.loads((ROOT / "examples" / "goal-spec.json").read_text(encoding="utf-8"))


class SchemaAndResourceTests(unittest.TestCase):
    def test_schema_properties_match_serialized_model(self) -> None:
        schema = get_goal_spec_schema()
        data = GoalSpec.from_dict(example_data()).to_dict()

        self.assertEqual(set(schema["properties"]), set(data))
        self.assertEqual(set(schema["required"]), set(data))

    def test_canonical_schema_drives_value_validation(self) -> None:
        mutations = {
            "version": "2.0",
            "language": "x",
            "constraints": [],
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                data = example_data()
                data[field] = value
                issues = validate_goal_spec_data(data)
                self.assertIn(field, {item.field for item in issues})

    def test_packaged_template_is_the_builder_source(self) -> None:
        template = get_metaprompt_template()

        self.assertIn("{{SOURCE_REQUEST}}", template)
        self.assertIn("{{GOAL_SPEC_SHAPE}}", template)
        self.assertIn('encoding="xml-escaped-json"', template)


if __name__ == "__main__":
    unittest.main()
