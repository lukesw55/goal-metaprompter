"""Metaprompt builder, GoalSpec validation, and target renderers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

from .models import (
    GoalRequest,
    GoalSpec,
    OutputContract,
    Target,
    ValidationIssue,
    ValidationReport,
)
from .resources import get_metaprompt_template
from .schema import validate_goal_spec_data

TARGET_GUIDANCE: dict[Target, str] = {
    Target.CLAUDE_CODE: (
        "O renderizador final já aplica a estrutura XML e a política de raciocínio interno. "
        "Concentre-se no conteúdo dos campos: contexto com caminhos completos, critérios de "
        "sucesso inspecionáveis e política de ferramentas em constraints somente quando "
        "específica do domínio."
    ),
    Target.CODEX: (
        "O prompt final é goal-first em Markdown compacto. Escreva goal como resultado "
        "observável em uma frase; explicite em context/inputs os caminhos, URLs e contratos a "
        "preservar; registre em validation_checks os testes e evidências esperados."
    ),
    Target.CURSOR: (
        "O prompt final é Markdown compacto executado dentro do editor. Declare em context os "
        "arquivos em escopo e as convenções do repositório; não recrie regras persistentes do "
        "projeto em constraints; prefira mudanças pequenas e verificáveis."
    ),
    Target.GEMINI: (
        "O prompt final unifica contexto longo ou multimodal antes da tarefa. Inventarie em "
        "inputs cada documento ou modalidade; coloque limites críticos em constraints; preencha "
        "output_contract.machine_schema quando a saída for consumida por máquina."
    ),
}


GOAL_SPEC_SHAPE = {
    "version": "1.0",
    "target": "claude-code | codex | cursor | gemini",
    "language": "idioma da saída",
    "role": "especialidade específica",
    "goal": "estado final observável",
    "success_criteria": ["critério verificável"],
    "context": ["fato, dependência ou caminho conhecido"],
    "inputs": ["input com tipo/semântica quando conhecidos"],
    "references": [
        {
            "label": "fonte",
            "url": "https://url-absoluta.example/path",
            "purpose": "uso da fonte",
            "required": True,
        }
    ],
    "constraints": ["limite real"],
    "non_goals": ["fora de escopo"],
    "edge_cases": ["condição e comportamento esperado"],
    "output_contract": {
        "format": "formato consumível",
        "sections": ["seção obrigatória"],
        "include_explanation": True,
        "verbosity": "low | medium | high",
        "machine_schema": None,
        "notes": "observações",
    },
    "assumptions": ["hipótese reversível"],
    "blocking_questions": ["pergunta indispensável"],
    "validation_checks": ["verificação final observável"],
}


def build_metaprompt(request: GoalRequest) -> str:
    """Build a provider-neutral metaprompt that requests a normalized GoalSpec JSON."""
    source = escape(
        json.dumps(request.to_dict(), ensure_ascii=False, indent=2),
        quote=False,
    )
    shape = json.dumps(GOAL_SPEC_SHAPE, ensure_ascii=False, indent=2)
    replacements = {
        "TARGET": request.target.value,
        "TARGET_GUIDANCE": TARGET_GUIDANCE[request.target],
        "GOAL_SPEC_SHAPE": shape,
        "TARGET_JSON": json.dumps(request.target.value),
        "LANGUAGE_JSON": json.dumps(request.language, ensure_ascii=False),
        "SOURCE_REQUEST": source,
    }
    # Single-pass substitution: request values containing a literal token
    # (e.g. language="{{SOURCE_REQUEST}}") must never be expanded themselves.
    template = re.sub(
        r"\{\{(" + "|".join(replacements) + r")\}\}",
        lambda match: replacements[match.group(1)],
        get_metaprompt_template(),
    )
    return template.rstrip() + "\n"


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def _control_character_issues(data: Any, path: str = "") -> list[ValidationIssue]:
    """Reject line breaks and control characters in GoalSpec string values.

    Values are single-line by contract; embedded newlines silently break the
    deterministic structure of the rendered Markdown/XML documents.
    ``machine_schema`` is exempt: its contents are re-serialized as JSON.
    """
    issues: list[ValidationIssue] = []
    if isinstance(data, str):
        if _CONTROL_CHARACTERS.search(data):
            issues.append(
                ValidationIssue(
                    path or "$",
                    "must not contain line breaks or control characters",
                )
            )
    elif isinstance(data, Mapping):
        for key, value in data.items():
            if key == "machine_schema":
                continue
            issues.extend(_control_character_issues(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        for index, item in enumerate(data):
            issues.extend(_control_character_issues(item, f"{path}[{index}]"))
    return issues


def _quality_issues(spec: GoalSpec) -> list[ValidationIssue]:
    """Warning-level quality gates that do not require domain semantics."""
    issues: list[ValidationIssue] = []
    if not spec.context and not spec.inputs:
        issues.append(
            ValidationIssue(
                "context",
                "both context and inputs are empty; confirm the task is genuinely context-free",
                "warning",
            )
        )
    if spec.blocking_questions:
        issues.append(
            ValidationIssue(
                "blocking_questions",
                "the final executor may need answers before it can safely complete the goal",
                "warning",
            )
        )
    if not spec.output_contract.sections and spec.output_contract.format.lower() in {"markdown", "document", "report"}:
        issues.append(
            ValidationIssue(
                "output_contract.sections",
                "a structured text format normally benefits from explicit sections",
                "warning",
            )
        )
    return issues


def validate_spec(spec: GoalSpec) -> ValidationReport:
    """Validate an already-parsed GoalSpec against the schema and quality gates."""
    data = spec.to_dict()
    issues = [
        ValidationIssue(item.field, item.message)
        for item in validate_goal_spec_data(data)
    ]
    issues.extend(_control_character_issues(data))
    issues.extend(_quality_issues(spec))
    return ValidationReport(tuple(issues))


def validate_goal_spec(data: Any) -> ValidationReport:
    """Validate raw GoalSpec data (e.g. LLM output) without raising.

    Unlike ``GoalSpec.from_dict``, this never crashes on malformed payloads:
    every schema violation — structural or value-level — is reported as an
    error issue, and the quality-gate warnings are added when the data can
    be parsed. A ``target`` alias accepted by ``Target.parse`` (e.g.
    ``"claude"``) is normalized before validation.
    """
    normalized = data
    if isinstance(data, Mapping):
        target = data.get("target")
        if isinstance(target, str):
            try:
                canonical = Target.parse(target).value
            except ValueError:
                canonical = target
            if canonical != target:
                normalized = {**data, "target": canonical}

    issues = [
        ValidationIssue(item.field, item.message)
        for item in validate_goal_spec_data(normalized)
    ]
    # Check the original payload: alias normalization strips the target,
    # which would otherwise launder control characters in that one field.
    issues.extend(_control_character_issues(data))
    try:
        spec = GoalSpec.from_dict(normalized)
    except (TypeError, ValueError) as exc:
        if not issues:
            issues.append(ValidationIssue("$", str(exc)))
        return ValidationReport(tuple(issues))
    # Parsing strips string values, so re-validate the canonical form: a raw
    # value like " " satisfies minLength but strips to empty.
    seen = {(issue.field, issue.message) for issue in issues}
    for item in validate_goal_spec_data(spec.to_dict()):
        if (item.field, item.message) not in seen:
            issues.append(ValidationIssue(item.field, item.message))
    issues.extend(_quality_issues(spec))
    return ValidationReport(tuple(issues))


_MD_TEXT: dict[str, dict[str, str]] = {
    "pt": {
        "empty_item": "- Nenhum item aplicável.",
        "no_references": "- Nenhuma URL fornecida. Não invente fontes; sinalize se uma for necessária.",
        "reference_required": "obrigatória",
        "reference_optional": "opcional",
        "language_label": "Idioma obrigatório da resposta",
        "format_label": "Formato",
        "verbosity_label": "Verbosidade",
        "explanations_label": "Explicações",
        "explanations_include": "incluir",
        "explanations_omit": "omitir",
        "sections_label": "Seções",
        "machine_schema_label": "Schema de máquina",
        "notes_label": "Observações",
        "no_blocking_questions": (
            "- Não há perguntas bloqueantes. Prossiga com base nas hipóteses declaradas; "
            "registre qualquer nova hipótese no relato final."
        ),
        "blocking_intro": "Antes de executar mudanças materiais, obtenha resposta somente para estas perguntas:",
        "blocking_fallback": (
            "Se não for possível obter respostas neste ambiente, pare antes de mudanças materiais "
            "e entregue somente: as perguntas, a análise realizada e as opções com trade-offs."
        ),
        "h_goal": "# Objetivo",
        "h_role": "## Papel",
        "h_workspace": "## Contexto do workspace",
        "h_inputs": "## Inputs",
        "h_sources": "## Fontes de verdade",
        "h_success": "## Critérios de sucesso",
        "h_constraints": "## Restrições",
        "h_non_goals": "## Fora de escopo",
        "h_edge_cases": "## Casos de borda",
        "h_assumptions": "## Hipóteses declaradas",
        "h_clarification": "## Política de esclarecimento",
        "h_deliverable": "## Entregável",
        "h_final_validation": "## Validação final",
        "codex_env_rule": (
            "Inspecione primeiro o workspace e as instruções aplicáveis. "
            "Preserve mudanças existentes e não relacionadas."
        ),
        "cursor_env_rule": (
            "Leia e respeite as regras do projeto e do Cursor aplicáveis aos arquivos em escopo. "
            "Mantenha instruções temporárias neste trabalho; não crie regras persistentes sem "
            "solicitação explícita."
        ),
        "use_full_paths": "Use os caminhos e URLs completos fornecidos; não invente referências ausentes.",
        "bounded_changes": (
            "Faça mudanças delimitadas e verificáveis. Evite refatorações ou dependências fora do objetivo."
        ),
        "final_validation_intro": (
            "Planeje internamente, execute e corrija silenciosamente violações encontradas. "
            "Não exponha chain-of-thought. Antes de concluir:"
        ),
        "check_compare": "- Compare o resultado com todos os critérios de sucesso e restrições.",
        "check_proportional": "- Execute verificações proporcionais ao risco e informe comandos/resultados relevantes.",
        "handoff": (
            "No handoff ao usuário, comece pelo resultado. Para {label}, mantenha o relato conciso e "
            "inclua somente arquivos/artefatos alterados, verificações executadas e limitações reais."
        ),
        "handoff_blocked": (
            "Se as perguntas bloqueantes impedirem a execução, o handoff deve começar pelas perguntas "
            "e pelo estado da análise, sem mudanças materiais."
        ),
        "g_critical": "# Instruções críticas",
        "g_act_as": "- Atue como {role}.",
        "g_respond_in": "- Responda em {language}.",
        "g_facts_only": "- Use apenas fatos e fontes identificados abaixo; não invente URLs nem requisitos.",
        "g_internal": (
            "- Planeje e valide internamente. Não exponha chain-of-thought; apresente somente "
            "resultado, evidências, decisões relevantes e limitações."
        ),
        "g_respect": "- Respeite todas as restrições e o contrato de saída.",
        "g_context": "# Contexto unificado",
        "g_facts": "## Fatos e dependências",
        "g_inputs": "## Inputs e modalidades",
        "g_sources": "## Fontes de verdade",
        "g_assumptions": "## Hipóteses declaradas",
        "g_limits": "# Limites",
        "g_constraints": "## Restrições",
        "g_non_goals": "## Fora de escopo",
        "g_edge_cases": "## Casos de borda",
        "g_task": "# Tarefa",
        "g_success": "## Critérios de sucesso",
        "g_clarification": "## Política de esclarecimento",
        "g_output": "# Formato de saída",
        "g_verify": "# Verificação antes da resposta",
        "g_check_compare": "- Compare o resultado com cada critério de sucesso, restrição e caso de borda aplicável.",
        "g_check_fix": "- Corrija silenciosamente violações encontradas antes de responder.",
    },
    "en": {
        "empty_item": "- No applicable items.",
        "no_references": "- No URLs provided. Do not invent sources; flag it if one is needed.",
        "reference_required": "required",
        "reference_optional": "optional",
        "language_label": "Required response language",
        "format_label": "Format",
        "verbosity_label": "Verbosity",
        "explanations_label": "Explanations",
        "explanations_include": "include",
        "explanations_omit": "omit",
        "sections_label": "Sections",
        "machine_schema_label": "Machine schema",
        "notes_label": "Notes",
        "no_blocking_questions": (
            "- There are no blocking questions. Proceed based on the declared assumptions; "
            "record any new assumption in the final report."
        ),
        "blocking_intro": "Before making material changes, obtain answers only to these questions:",
        "blocking_fallback": (
            "If answers cannot be obtained in this environment, stop before material changes and "
            "deliver only: the questions, the analysis performed, and the options with trade-offs."
        ),
        "h_goal": "# Goal",
        "h_role": "## Role",
        "h_workspace": "## Workspace context",
        "h_inputs": "## Inputs",
        "h_sources": "## Sources of truth",
        "h_success": "## Success criteria",
        "h_constraints": "## Constraints",
        "h_non_goals": "## Out of scope",
        "h_edge_cases": "## Edge cases",
        "h_assumptions": "## Declared assumptions",
        "h_clarification": "## Clarification policy",
        "h_deliverable": "## Deliverable",
        "h_final_validation": "## Final validation",
        "codex_env_rule": (
            "Inspect the workspace and any applicable instructions first. "
            "Preserve existing, unrelated changes."
        ),
        "cursor_env_rule": (
            "Read and respect the project and Cursor rules that apply to the files in scope. "
            "Keep temporary instructions within this task; do not create persistent rules without "
            "an explicit request."
        ),
        "use_full_paths": "Use the complete paths and URLs provided; do not invent missing references.",
        "bounded_changes": (
            "Make bounded, verifiable changes. Avoid refactors or dependencies outside the goal."
        ),
        "final_validation_intro": (
            "Plan internally, execute, and silently correct any violations found. "
            "Do not expose chain-of-thought. Before finishing:"
        ),
        "check_compare": "- Compare the result with every success criterion and constraint.",
        "check_proportional": "- Run checks proportional to the risk and report relevant commands/results.",
        "handoff": (
            "In the user handoff, start with the result. For {label}, keep the report concise and "
            "include only changed files/artifacts, checks executed, and real limitations."
        ),
        "handoff_blocked": (
            "If the blocking questions prevent execution, the handoff must start with the questions "
            "and the state of the analysis, with no material changes."
        ),
        "g_critical": "# Critical instructions",
        "g_act_as": "- Act as {role}.",
        "g_respond_in": "- Respond in {language}.",
        "g_facts_only": "- Use only the facts and sources identified below; do not invent URLs or requirements.",
        "g_internal": (
            "- Plan and validate internally. Do not expose chain-of-thought; present only the "
            "result, evidence, relevant decisions, and limitations."
        ),
        "g_respect": "- Respect every constraint and the output contract.",
        "g_context": "# Unified context",
        "g_facts": "## Facts and dependencies",
        "g_inputs": "## Inputs and modalities",
        "g_sources": "## Sources of truth",
        "g_assumptions": "## Declared assumptions",
        "g_limits": "# Limits",
        "g_constraints": "## Constraints",
        "g_non_goals": "## Out of scope",
        "g_edge_cases": "## Edge cases",
        "g_task": "# Task",
        "g_success": "## Success criteria",
        "g_clarification": "## Clarification policy",
        "g_output": "# Output format",
        "g_verify": "# Verification before answering",
        "g_check_compare": "- Compare the result with every applicable success criterion, constraint, and edge case.",
        "g_check_fix": "- Silently fix any violations found before answering.",
    },
}


def _md_text(language: str) -> dict[str, str]:
    """Scaffolding strings matching the response language (English fallback)."""
    key = "pt" if language.strip().lower().startswith("pt") else "en"
    return _MD_TEXT[key]


def _md_list(values: tuple[str, ...], text: dict[str, str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else text["empty_item"]


def _references_md(spec: GoalSpec, text: dict[str, str]) -> str:
    if not spec.references:
        return text["no_references"]
    # Plain text on purpose: Markdown link syntax would let a hostile label
    # rewrite the link target and bypass the URL validation.
    return "\n".join(
        f"- {item.label} "
        f"({text['reference_required'] if item.required else text['reference_optional']}): "
        f"{item.url} — {item.purpose}"
        for item in spec.references
    )


def _output_md(spec: GoalSpec, text: dict[str, str]) -> str:
    contract = spec.output_contract
    details = [
        f"- {text['language_label']}: {spec.language}",
        f"- {text['format_label']}: {contract.format}",
        f"- {text['verbosity_label']}: {contract.verbosity}",
        f"- {text['explanations_label']}: "
        f"{text['explanations_include'] if contract.include_explanation else text['explanations_omit']}",
    ]
    if contract.sections:
        details.append(f"- {text['sections_label']}: {', '.join(contract.sections)}")
    if contract.machine_schema is not None:
        details.append(
            f"- {text['machine_schema_label']}:\n```json\n"
            + json.dumps(contract.machine_schema, ensure_ascii=False, indent=2)
            + "\n```"
        )
    if contract.notes:
        details.append(f"- {text['notes_label']}: {contract.notes}")
    return "\n".join(details)


def _clarification_md(spec: GoalSpec, text: dict[str, str]) -> str:
    if not spec.blocking_questions:
        return text["no_blocking_questions"]
    return (
        text["blocking_intro"]
        + "\n"
        + _md_list(spec.blocking_questions, text)
        + "\n\n"
        + text["blocking_fallback"]
    )


def _render_codex_like(spec: GoalSpec, cursor: bool = False) -> str:
    text = _md_text(spec.language)
    environment_rule = text["cursor_env_rule"] if cursor else text["codex_env_rule"]
    label = "Cursor" if cursor else "Codex"
    handoff = text["handoff"].format(label=label)
    if spec.blocking_questions:
        handoff += "\n\n" + text["handoff_blocked"]
    return f"""{text["h_goal"]}

{spec.goal}

{text["h_role"]}

{spec.role}

{text["h_workspace"]}

{_md_list(spec.context, text)}

{text["h_inputs"]}

{_md_list(spec.inputs, text)}

{text["h_sources"]}

{_references_md(spec, text)}

{text["h_success"]}

{_md_list(spec.success_criteria, text)}

{text["h_constraints"]}

{_md_list(spec.constraints, text)}
- {environment_rule}
- {text["use_full_paths"]}
- {text["bounded_changes"]}

{text["h_non_goals"]}

{_md_list(spec.non_goals, text)}

{text["h_edge_cases"]}

{_md_list(spec.edge_cases, text)}

{text["h_assumptions"]}

{_md_list(spec.assumptions, text)}

{text["h_clarification"]}

{_clarification_md(spec, text)}

{text["h_deliverable"]}

{_output_md(spec, text)}

{text["h_final_validation"]}

{text["final_validation_intro"]}

{_md_list(spec.validation_checks, text)}
{text["check_compare"]}
{text["check_proportional"]}

{handoff}
"""


_XML_SINGULAR = {"success_criteria": "criterion"}


def _xml_items(tag: str, values: tuple[str, ...]) -> str:
    if not values:
        return f'<{tag} none="true" />'
    singular = _XML_SINGULAR.get(tag, tag[:-1] if tag.endswith("s") else "item")
    body = "\n".join(f"  <{singular}>{escape(value)}</{singular}>" for value in values)
    return f"<{tag}>\n{body}\n</{tag}>"


def _output_contract_xml(contract: OutputContract) -> str:
    lines = [f"  <format>{escape(contract.format)}</format>"]
    if contract.sections:
        body = "\n".join(f"    <section>{escape(item)}</section>" for item in contract.sections)
        lines.append(f"  <sections>\n{body}\n  </sections>")
    else:
        lines.append('  <sections none="true" />')
    lines.append(
        f"  <include_explanation>{str(contract.include_explanation).lower()}</include_explanation>"
    )
    lines.append(f"  <verbosity>{escape(contract.verbosity)}</verbosity>")
    if contract.machine_schema is not None:
        schema_json = escape(
            json.dumps(contract.machine_schema, ensure_ascii=False, indent=2),
            quote=False,
        )
        lines.append(f"  <machine_schema>\n{schema_json}\n  </machine_schema>")
    if contract.notes:
        lines.append(f"  <notes>{escape(contract.notes)}</notes>")
    return "<output_contract>\n" + "\n".join(lines) + "\n</output_contract>"


def _render_claude(spec: GoalSpec) -> str:
    references = (
        "\n".join(
            f"  <reference required=\"{str(item.required).lower()}\"><label>{escape(item.label)}</label><url>{escape(item.url)}</url><purpose>{escape(item.purpose)}</purpose></reference>"
            for item in spec.references
        )
        or "  <reference>None provided. Do not invent a source.</reference>"
    )
    if spec.blocking_questions:
        rule = (
            "Ask only the blocking questions below before material action. If answers cannot be "
            "obtained in this environment, stop before material changes and deliver only: the "
            "questions, the analysis performed, and the options with trade-offs."
        )
        clarification = f"  <rule>{escape(rule)}</rule>\n{_xml_items('blocking_questions', spec.blocking_questions)}"
    else:
        rule = "No blocking questions are registered. Proceed using the declared reversible assumptions."
        clarification = f"  <rule>{escape(rule)}</rule>"
    checks = spec.validation_checks + (
        "Compare the result with every success criterion and constraint.",
        "Correct detected violations before returning the final answer.",
    )
    return f"""<role>{escape(spec.role)}</role>

<response_language>{escape(spec.language)}</response_language>

<context>
{_xml_items('facts', spec.context)}
{_xml_items('inputs', spec.inputs)}
<references>
{references}
</references>
</context>

<goal>{escape(spec.goal)}</goal>

{_xml_items('success_criteria', spec.success_criteria)}

<instructions>
  <execution>Inspect relevant context and applicable repository instructions before acting. Make the smallest complete change that achieves the goal.</execution>
  <reasoning>Plan and check internally. Do not reveal private chain-of-thought; report only decisions, evidence, results, and genuine limitations.</reasoning>
  <sources>Use complete paths and URLs supplied in context. Never invent missing references.</sources>
  <tools>Use available tools when they materially improve correctness. Verify state after consequential actions.</tools>
</instructions>

{_xml_items('constraints', spec.constraints)}
{_xml_items('non_goals', spec.non_goals)}
{_xml_items('edge_cases', spec.edge_cases)}
{_xml_items('assumptions', spec.assumptions)}

<clarification_policy>
{clarification}
</clarification_policy>

{_output_contract_xml(spec.output_contract)}

<final_validation>
{_xml_items('checks', checks)}
</final_validation>
"""


def _render_gemini(spec: GoalSpec) -> str:
    text = _md_text(spec.language)
    return f"""{text["g_critical"]}

{text["g_act_as"].format(role=spec.role)}
{text["g_respond_in"].format(language=spec.language)}
{text["g_facts_only"]}
{text["g_internal"]}
{text["g_respect"]}

{text["g_context"]}

{text["g_facts"]}

{_md_list(spec.context, text)}

{text["g_inputs"]}

{_md_list(spec.inputs, text)}

{text["g_sources"]}

{_references_md(spec, text)}

{text["g_assumptions"]}

{_md_list(spec.assumptions, text)}

{text["g_limits"]}

{text["g_constraints"]}

{_md_list(spec.constraints, text)}

{text["g_non_goals"]}

{_md_list(spec.non_goals, text)}

{text["g_edge_cases"]}

{_md_list(spec.edge_cases, text)}

{text["g_task"]}

{spec.goal}

{text["g_success"]}

{_md_list(spec.success_criteria, text)}

{text["g_clarification"]}

{_clarification_md(spec, text)}

{text["g_output"]}

{_output_md(spec, text)}

{text["g_verify"]}

{_md_list(spec.validation_checks, text)}
{text["g_check_compare"]}
{text["g_check_fix"]}
"""


def render_goal_prompt(spec: GoalSpec, *, validate: bool = True) -> str:
    """Render a GoalSpec as a target-optimized prompt."""
    if validate:
        validate_spec(spec).raise_for_errors()
    if spec.target is Target.CLAUDE_CODE:
        return _render_claude(spec).strip() + "\n"
    if spec.target is Target.CODEX:
        return _render_codex_like(spec).strip() + "\n"
    if spec.target is Target.CURSOR:
        return _render_codex_like(spec, cursor=True).strip() + "\n"
    if spec.target is Target.GEMINI:
        return _render_gemini(spec).strip() + "\n"
    raise AssertionError(f"Unhandled target: {spec.target}")
