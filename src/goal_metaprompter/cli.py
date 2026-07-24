"""Command-line interface for Goal Metaprompter."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .core import build_metaprompt, render_goal_prompt, validate_goal_spec
from .models import GoalRequest, GoalSpec, Target


def _configure_stdio() -> None:
    """Force UTF-8 on the standard streams.

    On Windows, redirected/piped stdio falls back to the locale codepage
    (e.g. cp1252), which silently corrupts pt-BR text or crashes on encode.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _read_json(path: str) -> dict[str, Any]:
    if path == "-":
        buffer = getattr(sys.stdin, "buffer", None)
        if buffer is not None:
            raw = buffer.read().decode("utf-8-sig")
        else:
            raw = sys.stdin.read().lstrip("﻿")
    else:
        # utf-8-sig transparently strips the BOM that PowerShell's
        # `Out-File -Encoding utf8` and many Windows editors prepend.
        raw = Path(path).read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _write(text: str, output: str | None) -> None:
    if output:
        # newline="\n" keeps file output byte-identical to stdout output
        # (and to the committed snapshots) on Windows.
        Path(output).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
        if text and not text.endswith("\n"):
            sys.stdout.write("\n")


def _parse_target(value: str) -> Target:
    try:
        return Target.parse(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _request_from_args(args: argparse.Namespace) -> GoalRequest:
    if args.request:
        overridden = [
            flag
            for flag, given in (
                ("--prompt", args.prompt),
                ("--target", args.target),
                ("--language", args.language != "pt-BR"),
                ("--context", args.context),
                ("--reference", args.reference),
                ("--constraint", args.constraint),
                ("--audience", args.audience),
                ("--output-preference", args.output_preference),
            )
            if given
        ]
        if overridden:
            raise ValueError(f"--request cannot be combined with {', '.join(overridden)}")
        return GoalRequest.from_dict(_read_json(args.request))
    if not args.prompt or not args.target:
        raise ValueError("meta requires --request or both --prompt and --target")
    return GoalRequest(
        vague_prompt=args.prompt,
        target=args.target,
        language=args.language,
        context=tuple(args.context),
        references=tuple(args.reference),
        constraints=tuple(args.constraint),
        audience=args.audience,
        output_preference=args.output_preference,
    )


def _lenient_spec_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce raw data into a structurally parseable GoalSpec payload.

    Used by ``render --allow-invalid``: unknown keys are dropped and missing
    optional structure is defaulted so value-level problems (the ones the
    flag exists to bypass) do not abort the render. Reported validation
    errors are unaffected; only the parse becomes forgiving.
    """
    strings = {"version": "1.0", "language": "pt-BR", "role": "", "goal": ""}
    arrays = (
        "success_criteria",
        "context",
        "inputs",
        "constraints",
        "non_goals",
        "edge_cases",
        "assumptions",
        "blocking_questions",
        "validation_checks",
    )
    result: dict[str, Any] = {"target": data.get("target")}
    for name, default in strings.items():
        value = data.get(name)
        result[name] = value if isinstance(value, str) else default
    for name in arrays:
        value = data.get(name)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            result[name] = [item for item in value if isinstance(item, str) and item.strip()]
        else:
            result[name] = []

    references = data.get("references")
    result["references"] = []
    if isinstance(references, Sequence) and not isinstance(references, (str, bytes)):
        for item in references:
            if isinstance(item, Mapping) and all(
                isinstance(item.get(key), str) and item.get(key) for key in ("label", "url", "purpose")
            ):
                entry = {key: item[key] for key in ("label", "url", "purpose")}
                entry["required"] = item.get("required") is not False
                result["references"].append(entry)

    contract = data.get("output_contract")
    contract = contract if isinstance(contract, Mapping) else {}
    sections = contract.get("sections")
    if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
        sections = [item for item in sections if isinstance(item, str) and item.strip()]
    else:
        sections = []
    result["output_contract"] = {
        "format": contract.get("format") if isinstance(contract.get("format"), str) else "Markdown",
        "sections": sections,
        "include_explanation": contract.get("include_explanation") is not False,
        "verbosity": contract.get("verbosity") if isinstance(contract.get("verbosity"), str) else "medium",
        "machine_schema": dict(contract["machine_schema"])
        if isinstance(contract.get("machine_schema"), Mapping)
        else None,
        "notes": contract.get("notes") if isinstance(contract.get("notes"), str) else "",
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goal-metaprompter",
        description="Normalize vague requests into validated, target-adapted Goal prompts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    meta = subparsers.add_parser("meta", help="build the metaprompt that requests a GoalSpec")
    meta.add_argument("--request", help="request JSON file, or - for stdin")
    meta.add_argument("--prompt", help="vague source request")
    meta.add_argument(
        "--target",
        type=_parse_target,
        metavar="{claude-code,codex,cursor,gemini}",
        help="destination agent (aliases such as 'claude' are accepted)",
    )
    meta.add_argument("--language", default="pt-BR")
    meta.add_argument("--context", action="append", default=[])
    meta.add_argument(
        "--reference",
        action="append",
        default=[],
        help="source URL or textual hint as a plain string (repeatable)",
    )
    meta.add_argument("--constraint", action="append", default=[])
    meta.add_argument("--audience", default="")
    meta.add_argument(
        "--output-preference",
        default="",
        help="desired deliverable described in the GoalSpec (not a file format)",
    )
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
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "meta":
            _write(build_metaprompt(_request_from_args(args)), args.output)
            return 0

        data = _read_json(args.spec)
        report = validate_goal_spec(data)

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
            if report.valid:
                spec = GoalSpec.from_dict(data)
            else:
                spec = GoalSpec.from_dict(_lenient_spec_data(data))
            _write(render_goal_prompt(spec, validate=False), args.output)
            return 0

        raise AssertionError(f"Unhandled command: {args.command}")
    except (OSError, RecursionError, TypeError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
