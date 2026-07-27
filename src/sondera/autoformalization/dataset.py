"""Dataset loading for reproducible autoformalization experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    AutoformalizationInput,
    EvaluationCase,
    Requirement,
    ToolDefinition,
)
from .spec import AgentSpec, GeneratedSchema


def _tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value or [])


@dataclass(frozen=True)
class DatasetBundle:
    """All files required to run one experiment dataset."""

    root: Path
    spec: AgentSpec
    natural_language_policy: str
    requirements: tuple[Requirement, ...]
    cases: tuple[EvaluationCase, ...]
    expected_schema: str | None = None
    gold_policy: str | None = None

    @classmethod
    def load(
        cls,
        root: str | Path,
        *,
        agent_id: str = "coding_agent",
        provider: str = "custom",
    ) -> DatasetBundle:
        directory = Path(root)
        tool_payload = json.loads(
            (directory / "tools.json").read_text(encoding="utf-8")
        )
        tools = tuple(
            ToolDefinition(
                name=str(item["name"]),
                description=str(item.get("description", "")),
                input_schema=dict(item.get("inputSchema", {})),
                output_schema=dict(item.get("outputSchema", {})),
            )
            for item in tool_payload["tools"]
        )
        raw_requirements = json.loads(
            (directory / "requirements.json").read_text(encoding="utf-8")
        )
        requirements = tuple(
            Requirement(
                id=str(item["id"]),
                source=str(item["source"]),
                effect=str(item["effect"]),
                text=str(item["text"]),
                target_stages=_tuple(item.get("target_stages")),
                target_tools=_tuple(item.get("target_tools")),
                required_context=_tuple(item.get("required_context")),
                severity=str(item.get("severity", "medium")),
                enforceability=str(item.get("enforceability", "direct")),
            )
            for item in raw_requirements
        )
        raw_cases = json.loads((directory / "cases.json").read_text(encoding="utf-8"))
        cases = tuple(
            EvaluationCase(
                id=str(item["id"]),
                requirement_id=str(item["requirement_id"]),
                stage=str(item["stage"]),
                tool=str(item["tool"]),
                expected=str(item["expected"]).upper(),
                arguments=(dict(item["arguments"]) if "arguments" in item else None),
                output=item.get("output"),
                expected_policy_id=item.get("expected_policy_id"),
                context=dict(item.get("context", {})),
            )
            for item in raw_cases
        )
        expected_schema_path = directory / "expected.cedarschema"
        gold_path = directory / "gold.cedar"
        system_prompt = (directory / "system_prompt.txt").read_text(encoding="utf-8")
        return cls(
            root=directory,
            spec=AgentSpec(
                agent_id=agent_id,
                provider=provider,
                system_prompt=system_prompt,
                tools=tools,
            ),
            natural_language_policy=(directory / "policy.md").read_text(
                encoding="utf-8"
            ),
            requirements=requirements,
            cases=cases,
            expected_schema=(
                expected_schema_path.read_text(encoding="utf-8")
                if expected_schema_path.exists()
                else None
            ),
            gold_policy=(
                gold_path.read_text(encoding="utf-8") if gold_path.exists() else None
            ),
        )

    def grounded(self, schema: GeneratedSchema) -> AutoformalizationInput:
        return AutoformalizationInput(
            agent_id=self.spec.agent_id,
            provider=self.spec.provider,
            system_prompt=self.spec.system_prompt,
            tools=self.spec.tools,
            natural_language_policy=self.natural_language_policy,
            requirements=self.requirements,
            cedar_schema=schema.text,
        )
