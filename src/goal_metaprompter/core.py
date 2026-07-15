"""Metaprompt builder, GoalSpec validation, and target renderers."""

from __future__ import annotations

import json
from html import escape

from .models import GoalRequest, GoalSpec, Target, ValidationIssue, ValidationReport
from .resources import get_metaprompt_template
from .schema import validate_goal_spec_data

TARGET_GUIDANCE: dict[Target, str] = {
    Target.CLAUDE_CODE: (
        "Renderização futura em XML consistente; separar instruções, contexto, inputs, "
        "restrições, política de ferramentas e validação; solicitar planejamento interno "
        "sem expor chain-of-thought."
    ),
    Target.CODEX: (
        "Renderização futura em Markdown compacto; objetivo primeiro; explicitar caminhos/URLs, "
        "escopo, contratos, testes, preservação de mudanças existentes e handoff conciso."
    ),
    Target.CURSOR: (
        "Renderização futura em Markdown compacto; respeitar regras do projeto; declarar arquivos "
        "em escopo, convenções, contratos e verificações; manter instruções temporárias fora das regras persistentes."
    ),
    Target.GEMINI: (
        "Renderização futura em Markdown hierárquico; unificar contexto longo ou multimodal; "
        "colocar limites críticos cedo, a tarefa depois dos dados e usar structured output quando aplicável."
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
    template = get_metaprompt_template()
    replacements = (
        ("{{TARGET}}", request.target.value),
        ("{{TARGET_GUIDANCE}}", TARGET_GUIDANCE[request.target]),
        ("{{GOAL_SPEC_SHAPE}}", shape),
        ("{{TARGET_JSON}}", json.dumps(request.target.value)),
        ("{{LANGUAGE_JSON}}", json.dumps(request.language, ensure_ascii=False)),
        ("{{SOURCE_REQUEST}}", source),
    )
    for token, value in replacements:
        template = template.replace(token, value)
    return template.rstrip() + "\n"


def validate_spec(spec: GoalSpec) -> ValidationReport:
    """Validate structural quality gates that do not require domain semantics."""
    issues = [
        ValidationIssue(item.field, item.message)
        for item in validate_goal_spec_data(spec.to_dict())
    ]

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

    return ValidationReport(tuple(issues))


def _md_list(values: tuple[str, ...], empty: str = "- Nenhum item aplicável.") -> str:
    return "\n".join(f"- {value}" for value in values) if values else empty


def _references_md(spec: GoalSpec) -> str:
    if not spec.references:
        return "- Nenhuma URL fornecida. Não invente fontes; sinalize se uma for necessária."
    return "\n".join(
        f"- [{item.label}]({item.url}) — {item.purpose}"
        + (" (obrigatória)" if item.required else " (opcional)")
        for item in spec.references
    )


def _output_md(spec: GoalSpec) -> str:
    contract = spec.output_contract
    details = [
        f"- Idioma obrigatório da resposta: {spec.language}",
        f"- Formato: {contract.format}",
        f"- Verbosidade: {contract.verbosity}",
        f"- Explicações: {'incluir' if contract.include_explanation else 'omitir'}",
    ]
    if contract.sections:
        details.append(f"- Seções: {', '.join(contract.sections)}")
    if contract.machine_schema is not None:
        details.append(
            "- Schema de máquina:\n```json\n"
            + json.dumps(contract.machine_schema, ensure_ascii=False, indent=2)
            + "\n```"
        )
    if contract.notes:
        details.append(f"- Observações: {contract.notes}")
    return "\n".join(details)


def _clarification_md(spec: GoalSpec) -> str:
    if not spec.blocking_questions:
        return "- Não há perguntas bloqueantes registradas. Faça hipóteses reversíveis já declaradas e avance."
    return (
        "Antes de executar mudanças materiais, obtenha resposta somente para estas perguntas:\n"
        + _md_list(spec.blocking_questions)
    )


def _render_codex_like(spec: GoalSpec, cursor: bool = False) -> str:
    environment_rules = (
        "Leia e respeite as regras do projeto e do Cursor aplicáveis aos arquivos em escopo. "
        "Mantenha instruções temporárias neste trabalho; não crie regras persistentes sem solicitação explícita."
        if cursor
        else
        "Inspecione primeiro o workspace e as instruções aplicáveis. Preserve mudanças existentes e não relacionadas."
    )
    label = "Cursor" if cursor else "Codex"
    return f"""# Objetivo

{spec.goal}

## Papel

{spec.role}

## Contexto do workspace

{_md_list(spec.context)}

## Inputs

{_md_list(spec.inputs)}

## Fontes de verdade

{_references_md(spec)}

## Critérios de sucesso

{_md_list(spec.success_criteria)}

## Restrições

{_md_list(spec.constraints)}
- {environment_rules}
- Use os caminhos e URLs completos fornecidos; não invente referências ausentes.
- Faça mudanças delimitadas e verificáveis. Evite refatorações ou dependências fora do objetivo.

## Fora de escopo

{_md_list(spec.non_goals)}

## Casos de borda

{_md_list(spec.edge_cases)}

## Hipóteses declaradas

{_md_list(spec.assumptions)}

## Política de esclarecimento

{_clarification_md(spec)}

## Entregável

{_output_md(spec)}

## Validação final

Planeje internamente, execute e corrija silenciosamente violações encontradas. Não exponha chain-of-thought. Antes de concluir:

{_md_list(spec.validation_checks)}
- Compare o resultado com todos os critérios de sucesso e restrições.
- Execute verificações proporcionais ao risco e informe comandos/resultados relevantes.

No handoff ao usuário, comece pelo resultado. Para {label}, mantenha o relato conciso e inclua somente arquivos/artefatos alterados, verificações executadas e limitações reais.
"""


def _xml_items(tag: str, values: tuple[str, ...], empty_text: str = "None specified.") -> str:
    if not values:
        return f"<{tag}>{escape(empty_text)}</{tag}>"
    singular = tag[:-1] if tag.endswith("s") else "item"
    body = "\n".join(f"  <{singular}>{escape(value)}</{singular}>" for value in values)
    return f"<{tag}>\n{body}\n</{tag}>"


def _render_claude(spec: GoalSpec) -> str:
    references = (
        "\n".join(
            f"  <reference required=\"{str(item.required).lower()}\"><label>{escape(item.label)}</label><url>{escape(item.url)}</url><purpose>{escape(item.purpose)}</purpose></reference>"
            for item in spec.references
        )
        or "  <reference>None provided. Do not invent a source.</reference>"
    )
    output = escape(json.dumps(spec.output_contract.to_dict(), ensure_ascii=False, indent=2))
    questions = (
        "Ask only the blocking questions below before material action."
        if spec.blocking_questions
        else "No blocking questions are registered. Proceed using the declared reversible assumptions."
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
  <rule>{escape(questions)}</rule>
{_xml_items('blocking_questions', spec.blocking_questions)}
</clarification_policy>

<output_contract>{output}</output_contract>

<final_validation>
{_xml_items('checks', spec.validation_checks)}
  <check>Compare the result with every success criterion and constraint.</check>
  <check>Correct detected violations before returning the final answer.</check>
</final_validation>
"""


def _render_gemini(spec: GoalSpec) -> str:
    return f"""# Instruções críticas

- Atue como {spec.role}.
- Use apenas fatos e fontes identificados abaixo; não invente URLs nem requisitos.
- Planeje e valide internamente. Não exponha chain-of-thought; apresente somente resultado, evidências, decisões relevantes e limitações.
- Respeite todas as restrições e o contrato de saída.

# Contexto unificado

## Fatos e dependências

{_md_list(spec.context)}

## Inputs e modalidades

{_md_list(spec.inputs)}

## Fontes de verdade

{_references_md(spec)}

## Hipóteses declaradas

{_md_list(spec.assumptions)}

# Limites

## Restrições

{_md_list(spec.constraints)}

## Fora de escopo

{_md_list(spec.non_goals)}

## Casos de borda

{_md_list(spec.edge_cases)}

# Tarefa

{spec.goal}

## Critérios de sucesso

{_md_list(spec.success_criteria)}

## Política de esclarecimento

{_clarification_md(spec)}

# Formato de saída

{_output_md(spec)}

# Verificação antes da resposta

{_md_list(spec.validation_checks)}
- Compare o resultado com cada critério de sucesso, restrição e caso de borda aplicável.
- Corrija silenciosamente violações encontradas antes de responder.
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
