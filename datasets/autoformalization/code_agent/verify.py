# ruff: noqa: E402, I001, S101
"""Validate and replay the Stage A Code Agent dataset."""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARCHETYPES_SRC = ROOT / "examples" / "archetypes" / "src"
sys.path.insert(0, str(ARCHETYPES_SRC))

from archetypes.coding.naive import agent  # noqa: E402
from cedar import PolicySet, Schema  # noqa: E402
from sondera import Decision, Event, ToolCall, ToolOutput  # noqa: E402
from sondera.harness.cedar.harness import CedarPolicyHarness  # noqa: E402
from sondera.harness.cedar.schema import agent_to_cedar_schema  # noqa: E402
from sondera.harness.trajectory.file_storage import FileTrajectoryStorage  # noqa: E402

DATASET_DIR = Path(__file__).parent


def _event(harness: CedarPolicyHarness, payload: ToolCall | ToolOutput) -> Event:
    return Event(
        agent=harness.agent,
        trajectory_id=harness.trajectory_id,
        event=payload,
    )


async def main() -> None:
    tool_spec = json.loads((DATASET_DIR / "tools.json").read_text())
    requirements = json.loads((DATASET_DIR / "requirements.json").read_text())
    cases = json.loads((DATASET_DIR / "cases.json").read_text())
    policy_text = (DATASET_DIR / "gold.cedar").read_text()

    requirement_ids = {item["id"] for item in requirements}
    assert len(requirements) == 20
    assert len(requirement_ids) == 20
    assert len(cases) == 40
    assert {case["requirement_id"] for case in cases} == requirement_ids

    actual_tools = {tool.name: tool for tool in agent.card.react_card.tools}
    assert {tool["name"] for tool in tool_spec["tools"]} == set(actual_tools)
    for expected_tool in tool_spec["tools"]:
        actual_tool = actual_tools[expected_tool["name"]]
        assert expected_tool["description"] == actual_tool.description
        assert expected_tool["inputSchema"] == json.loads(
            actual_tool.parameters_json_schema
        )
        assert expected_tool["outputSchema"] == json.loads(
            actual_tool.response_json_schema
        )

    policy_set = PolicySet(policy_text)
    policies = list(policy_set.policies())
    assert len(policies) == 23
    policy_sources = {
        policy.annotations().get("source")
        for policy in policies
        if policy.annotations().get("source", "").startswith("policy.md#")
    }
    assert policy_sources == {f"policy.md#{item}" for item in requirement_ids}

    schema_model = agent_to_cedar_schema(agent)
    schema = Schema.from_json(schema_model.model_dump_json(exclude_none=True))
    expected_schema_text = (DATASET_DIR / "expected.cedarschema").read_text()
    Schema.from_cedarschema(expected_schema_text)
    assert schema.to_cedarschema().strip() == expected_schema_text.strip()
    schema.validate_policyset(policy_set)

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="code-agent-dataset-") as temp_dir:
        harness = CedarPolicyHarness(
            policy_set=policy_set,
            schema=schema_model,
            storage=FileTrajectoryStorage(temp_dir),
        )
        await harness.initialize(agent=agent)

        for case in cases:
            if case["stage"] == "PreToolUse":
                payload = ToolCall(tool=case["tool"], arguments=case["arguments"])
            else:
                payload = ToolOutput.from_success(case["tool"], case["output"])

            result = await harness.adjudicate(_event(harness, payload))
            expected = Decision(case["expected"].lower())
            if result.decision != expected:
                failures.append(
                    f"{case['id']}: expected {expected}, got {result.decision}"
                )
                continue

            expected_policy_id = case.get("expected_policy_id")
            actual_policy_ids = {item.policy_id for item in result.metadata or []}
            if expected_policy_id and expected_policy_id not in actual_policy_ids:
                failures.append(
                    f"{case['id']}: expected policy {expected_policy_id}, "
                    f"got {sorted(actual_policy_ids)}"
                )

        await harness.finalize()

    if failures:
        raise AssertionError("\n".join(failures))

    print("Validated 20 requirements, 23 Cedar policies, and 40 replay cases.")


if __name__ == "__main__":
    asyncio.run(main())
