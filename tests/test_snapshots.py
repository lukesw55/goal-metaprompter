from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goal_metaprompter import (  # noqa: E402
    GoalSpec,
    OutputContract,
    Target,
    render_goal_prompt,
)

SNAPSHOTS = Path(__file__).with_name("snapshots")


def snapshot_spec(target: Target) -> GoalSpec:
    return GoalSpec(
        target=target,
        language="pt-BR",
        role="Especialista de teste",
        goal="Entregar X.",
        success_criteria=("X entregue.",),
        context=(),
        inputs=(),
        references=(),
        constraints=("Não alterar Y.",),
        non_goals=(),
        edge_cases=("Entrada vazia gera erro.",),
        output_contract=OutputContract(
            format="Markdown",
            sections=("Resultado",),
            include_explanation=False,
            verbosity="low",
        ),
        assumptions=(),
        blocking_questions=(),
        validation_checks=("Confirmar X.",),
    )


class RendererSnapshotTests(unittest.TestCase):
    def test_renderers_match_reviewed_snapshots(self) -> None:
        for target in Target:
            with self.subTest(target=target.value):
                expected = (SNAPSHOTS / f"{target.value}.txt").read_text(encoding="utf-8")
                self.assertEqual(expected, render_goal_prompt(snapshot_spec(target)))


if __name__ == "__main__":
    unittest.main()
