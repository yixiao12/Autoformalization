"""Agent specification loading and Cedar schema generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cedar.schema import CedarSchema

from cedar import Schema
from sondera.harness.cedar.schema import agent_to_cedar_schema
from sondera.types import (
    Agent,  # pyright: ignore[reportAttributeAccessIssue]
    AgentCard,  # pyright: ignore[reportAttributeAccessIssue]
    Parameter,  # pyright: ignore[reportAttributeAccessIssue]
    ReActAgentCard,  # pyright: ignore[reportAttributeAccessIssue]
    Tool,  # pyright: ignore[reportAttributeAccessIssue]
)

from .models import ToolDefinition
from .normalization import normalized_context_schema


def _parameter_type(schema: dict[str, Any]) -> str:
    value = str(schema.get("type", "string")).lower()
    return {
        "boolean": "boolean",
        "integer": "integer",
        "number": "number",
        "array": "array",
        "object": "object",
    }.get(value, "string")


@dataclass(frozen=True)
class AgentSpec:
    """Framework-independent description of an MCP-enabled Agent."""

    agent_id: str
    provider: str
    system_prompt: str
    tools: tuple[ToolDefinition, ...]

    def to_agent(self) -> Agent:
        """Build the SDK Agent required by schema generation and replay."""
        sdk_tools: list[Tool] = []
        for definition in self.tools:
            properties = definition.input_schema.get("properties", {})
            parameters = [
                Parameter(
                    name,
                    str(shape.get("description", "")),
                    _parameter_type(shape),
                )
                for name, shape in properties.items()
            ]
            sdk_tools.append(
                Tool(
                    definition.name,
                    definition.description,
                    parameters,
                    parameters_json_schema=json.dumps(definition.input_schema),
                    response=str(definition.output_schema.get("type", "object")),
                    response_json_schema=json.dumps(definition.output_schema),
                )
            )

        react_card = ReActAgentCard(
            system_instruction=self.system_prompt,
            tools=sdk_tools,
        )
        return Agent(
            self.agent_id,
            self.provider,
            card=AgentCard.react(react_card),
        )


@dataclass(frozen=True)
class GeneratedSchema:
    """Both model and text forms of a generated Cedar schema."""

    model: CedarSchema
    text: str


class CedarSchemaGenerator:
    """Deterministically generate Cedar schema from MCP tool definitions."""

    def generate(self, spec: AgentSpec) -> GeneratedSchema:
        model = agent_to_cedar_schema(
            spec.to_agent(),
            pre_tool_context_extensions={
                "normalized": normalized_context_schema(),
            },
        )
        native = Schema.from_json(
            model.model_dump_json(exclude_none=True)  # type: ignore[attr-defined]
        )
        return GeneratedSchema(model=model, text=native.to_cedarschema())
