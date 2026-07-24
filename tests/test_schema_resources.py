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

    def test_uri_validation_edge_cases(self) -> None:
        cases = {
            "https://[::1": "is not a parseable URL",
            "http://host:99999x": "must contain a valid port",
            "ftp://example.com/x": "must be an absolute http:// or https:// URL",
            "https:///path": "must be an absolute http:// or https:// URL",
            "https://user@example.com/x": "must not contain userinfo",
            "https://example.com/​path": "invisible characters",
            "https://example.com/\x00path": "invisible characters",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                data = example_data()
                references = data["references"]
                assert isinstance(references, list)
                references[0]["url"] = url
                issues = validate_goal_spec_data(data)
                messages = {item.field: item.message for item in issues}
                self.assertIn("references[0].url", messages)
                self.assertIn(expected, messages["references[0].url"])

    def test_schema_copies_are_isolated(self) -> None:
        first = get_goal_spec_schema()
        first["properties"]["language"]["minLength"] = 99

        second = get_goal_spec_schema()

        self.assertEqual(2, second["properties"]["language"]["minLength"])

    def test_uri_validation_accepts_common_valid_urls(self) -> None:
        for url in (
            "https://owasp.org/path",
            "http://localhost:8080/x",
            "https://[::1]:8080/x",
        ):
            with self.subTest(url=url):
                data = example_data()
                references = data["references"]
                assert isinstance(references, list)
                references[0]["url"] = url
                issues = validate_goal_spec_data(data)
                self.assertNotIn("references[0].url", {item.field for item in issues})


if __name__ == "__main__":
    unittest.main()
