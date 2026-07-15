"""Command-line interface for Goal Metaprompter."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .core import build_metaprompt, render_goal_prompt, validate_spec
from .models import GoalRequest, GoalSpec, Target


def _read_json(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _write(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
        if text and not text.endswith("\n"):
            sys.stdout.write("\n")


def _request_from_args(args: argparse.Namespace) -> GoalRequest:
    if args.request:
        if args.prompt or args.target:
            raise ValueError("--request cannot be combined with --prompt or --target")
        return GoalRequest.from_dict(_read_json(args.request))
    if not args.prompt or not args.target:
        raise ValueError("meta requires --request or both --prompt and --target")
    return GoalRequest(
        vague_prompt=args.prompt,
        target=Target.parse(args.target),
        language=args.language,
        context=tuple(args.context),
        references=tuple(args.reference),
        constraints=tuple(args.constraint),
        audience=args.audience,
        output_preference=args.output_preference,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goal-metaprompter",
        description="Normalize vague requests into validated, target-adapted Goal prompts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    meta = subparsers.add_parser("meta", help="build the metaprompt that requests a GoalSpec")
    meta.add_argument("--request", help="request JSON file, or - for stdin")
    meta.add_argument("--prompt", help="vague source request")
    meta.add_argument("--target", choices=[item.value for item in Target])
    meta.add_argument("--language", default="pt-BR")
    meta.add_argument("--context", action="append", default=[])
    meta.add_argument("--reference", action="append", default=[])
    meta.add_argument("--constraint", action="append", default=[])
    meta.add_argument("--audience", default="")
    meta.add_argument("--output-preference", "--output-format", dest="output_preference", default="")
    meta.add_argument("--output", help="write output to a file")

    validate = subparsers.add_parser("validate", help="validate a GoalSpec JSON")
    validate.add_argument("spec", help="GoalSpec JSON file, or - for stdin")
    validate.add_argument("--json", action="store_true", help="emit the report as JSON")

    render = subparsers.add_parser("render", help="render a GoalSpec for its target")
    render.add_argument("spec", help="GoalSpec JSON file, or - for stdin")
    render.add_argument("--output", help="write output to a file")
    render.add_argument("--allow-invalid", action="store_true", help="render despite validation errors")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "meta":
            _write(build_metaprompt(_request_from_args(args)), args.output)
            return 0

        spec = GoalSpec.from_dict(_read_json(args.spec))
        report = validate_spec(spec)

        if args.command == "validate":
            if args.json:
                _write(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), None)
            elif report.issues:
                for issue in report.issues:
                    sys.stdout.write(f"{issue.severity.upper()} {issue.field}: {issue.message}\n")
            else:
                sys.stdout.write("GoalSpec valid.\n")
            return 0 if report.valid else 1

        if args.command == "render":
            if not report.valid and not args.allow_invalid:
                report.raise_for_errors()
            _write(render_goal_prompt(spec, validate=not args.allow_invalid), args.output)
            return 0

        parser.error(f"unknown command: {args.command}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
