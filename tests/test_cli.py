from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goal_metaprompter.cli import build_parser, main  # noqa: E402


class CliTests(unittest.TestCase):
    def test_output_preference_and_output_path_are_distinct(self) -> None:
        args = build_parser().parse_args(
            [
                "meta",
                "--target",
                "codex",
                "--prompt",
                "Crie login",
                "--output-preference",
                "Patch pronto para revisão, com testes",
                "--output",
                "meta-prompt.md",
            ]
        )

        self.assertEqual("Patch pronto para revisão, com testes", args.output_preference)
        self.assertEqual("meta-prompt.md", args.output)

    def test_meta_command_writes_requested_file(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "meta.md"
            code = main(
                [
                    "meta",
                    "--target",
                    "codex",
                    "--prompt",
                    "Crie login",
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(0, code)
            self.assertIn("# SYSTEM SKILL", output.read_text(encoding="utf-8"))

    def test_validate_command_emits_machine_readable_report(self) -> None:
        example = ROOT / "examples" / "goal-spec.json"
        stdout = StringIO()

        with redirect_stdout(stdout):
            code = main(["validate", str(example), "--json"])

        self.assertEqual(0, code)
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["valid"])
        self.assertEqual([], report["issues"])


if __name__ == "__main__":
    unittest.main()
