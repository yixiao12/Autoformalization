"""Tests for the low-intrusion MedAgentBench benchmark adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sondera.autoformalization.benchmarks.medagentbench.adapter import (
    MedAgentBenchTrajectoryAdapter,
)
from sondera.autoformalization.benchmarks.medagentbench.replay import (
    MedAgentBenchReplayEvaluator,
)
from sondera.autoformalization.benchmarks.medagentbench.schema import (
    MedAgentBenchSchemaGenerator,
)
from sondera.autoformalization.dataset import DatasetBundle

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "datasets" / "autoformalization" / "medagentbench"


def _message_trajectory(
    trajectory_id: str,
    tool: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    return {
        "id": trajectory_id,
        "golden_hist": [],
        "trajectory": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "retrieve the patient record"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{trajectory_id}",
                        "type": "function",
                        "function": {
                            "name": tool,
                            "arguments": json.dumps(arguments),
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": f"call-{trajectory_id}",
                "content": '{"result": []}',
            },
        ],
    }


def test_adapter_normalizes_raw_post_and_tracks_post_subset(tmp_path: Path) -> None:
    source = tmp_path / "custom.json"
    source.write_text(
        json.dumps(
            {
                "full_trajectory": [
                    _message_trajectory(
                        "task-post",
                        "post_request",
                        {
                            "url": "http://localhost:8080/fhir/Observation",
                            "payload": json.dumps(
                                {
                                    "resourceType": "Observation",
                                    "subject": {"reference": "Patient/S1234567"},
                                }
                            ),
                        },
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    trajectory = MedAgentBenchTrajectoryAdapter().load_file(
        source, dataset="Synthetic", condition="Raw"
    )[0]
    call = trajectory.events[0]
    assert trajectory.has_post
    assert call.medical["canonical_tool"] == "post_observation"
    assert call.medical["current_patient_id"] == "S1234567"
    assert call.session["current_call_patient_unseen"] is True


def test_medagent_schema_declares_portable_context_extensions() -> None:
    dataset = DatasetBundle.load(DATASET, agent_id="medagentbench_agent")
    schema = MedAgentBenchSchemaGenerator().generate(dataset.spec).text
    assert "medical?:" in schema
    assert "session?:" in schema
    assert "current_call_is_duplicate" in schema
    assert "canonical_tool" in schema


@pytest.mark.asyncio
async def test_replay_calculates_all_and_post_block_rates(tmp_path: Path) -> None:
    source = tmp_path / "custom.json"
    source.write_text(
        json.dumps(
            {
                "full_trajectory": [
                    _message_trajectory(
                        "task-get",
                        "get_patient",
                        {"patient_id": "S1234567"},
                    ),
                    _message_trajectory(
                        "task-post",
                        "post_observation",
                        {
                            "observation": {
                                "resourceType": "Observation",
                                "subject": {"reference": "Patient/S1234567"},
                            }
                        },
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )
    dataset = DatasetBundle.load(DATASET, agent_id="medagentbench_agent")
    schema = MedAgentBenchSchemaGenerator().generate(dataset.spec)
    policy = """
@id("default-pre") @source("infrastructure")
permit(principal, action == medagentbench_agent::Action::"PreToolUse", resource);
@id("default-output") @source("infrastructure")
permit(principal, action == medagentbench_agent::Action::"ToolOutput", resource);
@id("block-writes") @source("test")
forbid(principal, action == medagentbench_agent::Action::"PreToolUse", resource)
when { context has medical && context.medical.is_write };
"""
    trajectories = MedAgentBenchTrajectoryAdapter().load_file(
        source, dataset="Synthetic", condition="Typed"
    )
    result = await MedAgentBenchReplayEvaluator().replay_group(
        policy,
        schema,
        dataset.spec,
        trajectories,
        source_file=str(source),
    )
    assert (result.blocked, result.total, result.block_rate) == (1, 2, 0.5)
    assert (result.post_blocked, result.post_total, result.post_block_rate) == (
        1,
        1,
        1.0,
    )
    assert result.policy_firings() == {"block-writes": 1}
