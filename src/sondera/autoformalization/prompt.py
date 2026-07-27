"""Hierarchical policy-generator prompt assembly."""

from __future__ import annotations

import json

from .models import AutoformalizationInput, PolicyCandidate
from .normalization import NORMALIZED_CONTEXT_GUIDE

GENERATOR_INSTRUCTION = """You are a Cedar policy compiler.
Translate the grounded natural-language requirements into a complete Cedar policy set.

Non-negotiable constraints:
1. Use only entities, actions, context fields, and types declared in CEDAR_SCHEMA.
2. Do not invent tools, fields, state, or exceptions.
3. Guard optional fields with `has` before reading them.
4. Add a unique @id annotation and an exact @source annotation to every policy.
5. Include default permit policies for Prompt, PreToolUse, and ToolOutput; forbids override them.
6. Report requirements that cannot be expressed instead of guessing.
7. Return JSON only, using the output contract at the end of this prompt.
8. Prefer trusted `context.normalized` fields over raw-string `like` patterns.
9. Annotate the three default permit policies with @source("infrastructure").
10. Return top-level Cedar policies only; never wrap policies in a `namespace` block.
11. Use fully qualified action names exactly as shown in CEDAR_SCHEMA, for example
    `coding_agent::Action::"PreToolUse"`, not unqualified `Action::"PreToolUse"`.
"""


def _candidate_json(candidate: PolicyCandidate | None) -> str:
    if candidate is None:
        return "null"
    return json.dumps(
        {
            "policies": candidate.policies,
            "requirement_mapping": candidate.requirement_mapping,
            "unsupported_requirements": candidate.unsupported_requirements,
            "assumptions": candidate.assumptions,
            "changes": candidate.changes,
        },
        indent=2,
        ensure_ascii=False,
    )


class HierarchicalPromptBuilder:
    """Compose all grounding and critic feedback into one stable prompt."""

    def build(
        self,
        grounded: AutoformalizationInput,
        *,
        round_number: int,
        previous_candidate: PolicyCandidate | None = None,
        hard_feedback: str = "",
        soft_feedback: str = "",
    ) -> str:
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "outputSchema": tool.output_schema,
            }
            for tool in grounded.tools
        ]
        requirements = [
            {
                "id": item.id,
                "source": item.source,
                "effect": item.effect,
                "text": item.text,
                "target_stages": list(item.target_stages),
                "target_tools": list(item.target_tools),
                "required_context": list(item.required_context),
                "severity": item.severity,
                "enforceability": item.enforceability,
            }
            for item in grounded.requirements
        ]
        return f"""<LEVEL_1_GENERATOR_INSTRUCTION>
{GENERATOR_INSTRUCTION.strip()}
</LEVEL_1_GENERATOR_INSTRUCTION>

<LEVEL_2_SYSTEM_PROMPT>
{grounded.system_prompt}
</LEVEL_2_SYSTEM_PROMPT>

<LEVEL_3_TOOL_DEFINITIONS>
{json.dumps(tools, indent=2, ensure_ascii=False)}
</LEVEL_3_TOOL_DEFINITIONS>

<LEVEL_4_CEDAR_SCHEMA>
{grounded.cedar_schema}
</LEVEL_4_CEDAR_SCHEMA>

<LEVEL_4_NORMALIZED_CONTEXT_SEMANTICS>
{NORMALIZED_CONTEXT_GUIDE.strip()}
</LEVEL_4_NORMALIZED_CONTEXT_SEMANTICS>

<LEVEL_5_NATURAL_LANGUAGE_POLICY>
{grounded.natural_language_policy}
</LEVEL_5_NATURAL_LANGUAGE_POLICY>

<LEVEL_5_REQUIREMENT_IR>
{json.dumps(requirements, indent=2, ensure_ascii=False)}
</LEVEL_5_REQUIREMENT_IR>

<LEVEL_6_REPAIR_CONTEXT round="{round_number}">
<PREVIOUS_CANDIDATE>
{_candidate_json(previous_candidate)}
</PREVIOUS_CANDIDATE>
<HARD_FEEDBACK>
{hard_feedback or "No hard feedback for this round."}
</HARD_FEEDBACK>
<VERIFIED_SOFT_FEEDBACK>
{soft_feedback or "No verified soft feedback for this round."}
</VERIFIED_SOFT_FEEDBACK>
</LEVEL_6_REPAIR_CONTEXT>

<LEVEL_7_OUTPUT_CONTRACT>
{{
  "policies": "complete Cedar policy set",
  "requirement_mapping": {{"requirement-id": ["policy-id"]}},
  "unsupported_requirements": [],
  "assumptions": [],
  "changes": []
}}
</LEVEL_7_OUTPUT_CONTRACT>
"""
