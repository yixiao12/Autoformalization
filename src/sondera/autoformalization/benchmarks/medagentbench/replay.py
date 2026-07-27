"""Offline Cedar replay and paper-compatible block-rate aggregation."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cedar import PolicySet
from sondera import Event, ToolCall, ToolOutput  # type: ignore[attr-defined]
from sondera.harness.cedar.harness import CedarPolicyHarness
from sondera.harness.trajectory.file_storage import FileTrajectoryStorage

from ...spec import AgentSpec, GeneratedSchema
from .adapter import EXPERIMENT_FILES, MedAgentBenchTrajectoryAdapter
from .context import ReplayContextProvider
from .models import (
    RecordedTrajectory,
    ReplayEventResult,
    ReplayGroupResult,
    TrajectoryReplayResult,
)


class MedAgentBenchReplayEvaluator:
    """Replay saved agent actions without invoking an Agent or FHIR server."""

    def __init__(self, adapter: MedAgentBenchTrajectoryAdapter | None = None):
        self.adapter = adapter or MedAgentBenchTrajectoryAdapter()

    async def replay_group(
        self,
        policy_text: str,
        schema: GeneratedSchema,
        spec: AgentSpec,
        trajectories: Iterable[RecordedTrajectory],
        *,
        source_file: str,
    ) -> ReplayGroupResult:
        items = list(trajectories)
        if not items:
            raise ValueError("cannot replay an empty trajectory group")
        group = ReplayGroupResult(
            dataset=items[0].dataset,
            condition=items[0].condition,
            source_file=source_file,
        )
        provider = ReplayContextProvider()

        with tempfile.TemporaryDirectory(prefix="medagentbench-replay-") as temp:
            harness = CedarPolicyHarness(
                policy_set=PolicySet(policy_text),
                schema=schema.model,
                storage=FileTrajectoryStorage(temp),
                tool_call_context_enricher=provider.enrich_tool_call,
                tool_output_context_enricher=provider.enrich_tool_output,
            )
            for trajectory in items:
                await harness.initialize(agent=spec.to_agent())
                event_results: list[ReplayEventResult] = []
                try:
                    for adapted in trajectory.events:
                        provider.set_context(
                            session=adapted.session,
                            medical=adapted.medical,
                        )
                        if adapted.stage == "PreToolUse":
                            payload = ToolCall(
                                tool=adapted.tool,
                                arguments=adapted.arguments or {},
                            )
                        elif adapted.stage == "ToolOutput":
                            payload = ToolOutput.from_success(
                                adapted.tool, adapted.output or ""
                            )
                        else:
                            raise ValueError(
                                f"unsupported replay stage: {adapted.stage}"
                            )
                        event = Event(
                            agent=harness.agent,
                            trajectory_id=harness.trajectory_id,
                            event=payload,
                        )
                        adjudicated = await harness.adjudicate(event)
                        decision = str(adjudicated.decision).upper()
                        policy_ids = tuple(
                            sorted(
                                {item.policy_id for item in adjudicated.metadata or []}
                            )
                        )
                        event_results.append(
                            ReplayEventResult(
                                stage=adapted.stage,
                                tool=adapted.tool,
                                decision=decision,
                                policy_ids=policy_ids,
                            )
                        )
                finally:
                    await harness.finalize()

                group.trajectories.append(
                    TrajectoryReplayResult(
                        id=trajectory.id,
                        dataset=trajectory.dataset,
                        condition=trajectory.condition,
                        has_post=trajectory.has_post,
                        blocked=any(
                            result.decision == "DENY" for result in event_results
                        ),
                        events=tuple(event_results),
                    )
                )
        return group

    async def replay_experiment(
        self,
        policy_text: str,
        schema: GeneratedSchema,
        spec: AgentSpec,
        experiment_root: str | Path,
    ) -> dict[str, Any]:
        directory = Path(experiment_root)
        groups: list[ReplayGroupResult] = []
        for filename in EXPERIMENT_FILES:
            trajectories = self.adapter.load_file(directory / filename)
            groups.append(
                await self.replay_group(
                    policy_text,
                    schema,
                    spec,
                    trajectories,
                    source_file=str(directory / filename),
                )
            )
        return {
            "metric_definition": {
                "trajectory_block_rate": (
                    "trajectories with at least one Cedar DENY / all trajectories"
                ),
                "post_trajectory_block_rate": (
                    "blocked trajectories / trajectories containing at least one "
                    "post_request or post_* call"
                ),
            },
            "groups": [group.to_dict() for group in groups],
        }


def markdown_report(report: dict[str, Any]) -> str:
    groups = report["groups"]
    lines = [
        "# MedAgentBench Cedar Replay",
        "",
        "## All trajectories",
        "",
        "| Dataset | Condition | Blocked | Total | Block rate |",
        "|---|---|---:|---:|---:|",
    ]
    for group in groups:
        metric = group["all_trajectories"]
        lines.append(
            f"| {group['dataset']} | {group['condition']} | "
            f"{metric['blocked']} | {metric['total']} | "
            f"{metric['block_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Trajectories containing POST",
            "",
            "| Dataset | Condition | Blocked | With POST | Block rate |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for group in groups:
        metric = group["trajectories_with_post"]
        lines.append(
            f"| {group['dataset']} | {group['condition']} | "
            f"{metric['blocked']} | {metric['total']} | "
            f"{metric['block_rate']:.1%} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], output: str | Path) -> None:
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "replay_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "replay_report.md").write_text(
        markdown_report(report), encoding="utf-8"
    )
