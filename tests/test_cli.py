from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goal_metaprompter.cli import build_parser, main  # noqa: E402

EXAMPLE_SPEC = ROOT / "examples" / "goal-spec.json"
EXAMPLE_REQUEST = ROOT / "examples" / "vague-request.json"


def example_data() -> dict[str, object]:
    return json.loads(EXAMPLE_SPEC.read_text(encoding="utf-8"))


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

    def test_meta_accepts_target_alias(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "meta.md"
            code = main(["meta", "--target", "claude", "--prompt", "Crie login", "--output", str(output)])

            self.assertEqual(0, code)
            self.assertIn("claude-code", output.read_text(encoding="utf-8"))

    def test_meta_output_preference_reaches_metaprompt(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "meta.md"
            code = main(
                [
                    "meta",
                    "--target",
                    "codex",
                    "--prompt",
                    "Crie login",
                    "--output-preference",
                    "Patch pronto para revisão",
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(0, code)
            self.assertIn("Patch pronto para revisão", output.read_text(encoding="utf-8"))

    def test_meta_request_file_rejects_conflicting_flags(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            code = main(["meta", "--request", str(EXAMPLE_REQUEST), "--language", "en-US"])

        self.assertEqual(2, code)
        self.assertIn("--language", stderr.getvalue())

    def test_meta_request_file_alone_succeeds(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "meta.md"
            code = main(["meta", "--request", str(EXAMPLE_REQUEST), "--output", str(output)])

            self.assertEqual(0, code)
            self.assertIn("Crie uma função de login", output.read_text(encoding="utf-8"))

    def test_validate_command_emits_machine_readable_report(self) -> None:
        stdout = StringIO()

        with redirect_stdout(stdout):
            code = main(["validate", str(EXAMPLE_SPEC), "--json"])

        self.assertEqual(0, code)
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["valid"])
        self.assertEqual([], report["issues"])

    def test_validate_returns_1_and_report_for_value_level_errors(self) -> None:
        data = example_data()
        data["constraints"] = []
        with TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.json"
            spec.write_text(json.dumps(data), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = main(["validate", str(spec)])

        self.assertEqual(1, code)
        self.assertIn("ERROR constraints", stdout.getvalue())

    def test_validate_returns_1_and_report_for_structural_errors(self) -> None:
        data = example_data()
        del data["edge_cases"]
        data["reasoning"] = "unexpected"
        with TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.json"
            spec.write_text(json.dumps(data), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                json_code = main(["validate", str(spec), "--json"])
            report = json.loads(stdout.getvalue())

        self.assertEqual(1, json_code)
        self.assertFalse(report["valid"])
        fields = {issue["field"] for issue in report["issues"]}
        self.assertIn("edge_cases", fields)
        self.assertIn("reasoning", fields)

    def test_validate_warnings_keep_exit_zero(self) -> None:
        data = example_data()
        data["blocking_questions"] = ["Qual mecanismo de sessão usar?"]
        with TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.json"
            spec.write_text(json.dumps(data), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = main(["validate", str(spec)])

        self.assertEqual(0, code)
        self.assertIn("WARNING blocking_questions", stdout.getvalue())

    def test_validate_accepts_bom_prefixed_file(self) -> None:
        with TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.json"
            spec.write_text(EXAMPLE_SPEC.read_text(encoding="utf-8"), encoding="utf-8-sig")
            with redirect_stdout(StringIO()):
                code = main(["validate", str(spec)])

        self.assertEqual(0, code)

    def test_render_writes_lf_only_output_file(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "prompt.md"
            code = main(["render", str(EXAMPLE_SPEC), "--output", str(output)])

            self.assertEqual(0, code)
            raw = output.read_bytes()
            self.assertIn(b"\n", raw)
            self.assertNotIn(b"\r\n", raw)

    def test_render_invalid_spec_exits_2(self) -> None:
        data = example_data()
        data["constraints"] = []
        with TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.json"
            spec.write_text(json.dumps(data), encoding="utf-8")
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = main(["render", str(spec)])

        self.assertEqual(2, code)
        self.assertIn("constraints", stderr.getvalue())

    def test_render_allow_invalid_bypasses_structural_errors(self) -> None:
        data = example_data()
        del data["edge_cases"]
        data["annotation"] = "extra key that should be tolerated"
        with TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.json"
            spec.write_text(json.dumps(data), encoding="utf-8")
            output = Path(directory) / "prompt.md"
            code = main(["render", str(spec), "--allow-invalid", "--output", str(output)])

            self.assertEqual(0, code)
            self.assertIn("# Objetivo", output.read_text(encoding="utf-8"))

    def test_render_reads_stdin_as_utf8_regardless_of_console_encoding(self) -> None:
        payload = EXAMPLE_SPEC.read_bytes()
        original = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(payload), encoding="cp1252")
        try:
            with TemporaryDirectory() as directory:
                output = Path(directory) / "prompt.md"
                code = main(["render", "-", "--output", str(output)])

                self.assertEqual(0, code)
                self.assertIn("sênior", output.read_text(encoding="utf-8"))
        finally:
            sys.stdin = original

    def test_malformed_json_exits_2(self) -> None:
        with TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.json"
            spec.write_text("{not json", encoding="utf-8")
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = main(["validate", str(spec)])

        self.assertEqual(2, code)
        self.assertIn("error:", stderr.getvalue())

    def test_missing_file_exits_2(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            code = main(["validate", "does-not-exist.json"])

        self.assertEqual(2, code)
        self.assertIn("error:", stderr.getvalue())

    def test_deeply_nested_json_exits_2(self) -> None:
        with TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.json"
            spec.write_text("[" * 100_000, encoding="utf-8")
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = main(["validate", str(spec)])

        self.assertEqual(2, code)

    def test_meta_without_prompt_or_request_exits_2(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            code = main(["meta", "--target", "codex"])

        self.assertEqual(2, code)
        self.assertIn("meta requires", stderr.getvalue())

    def test_unknown_target_flag_reports_choices(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                build_parser().parse_args(["meta", "--target", "gpt", "--prompt", "x"])

        self.assertEqual(2, caught.exception.code)
        self.assertIn("claude-code", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
