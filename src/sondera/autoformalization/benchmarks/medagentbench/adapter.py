"""Convert saved MedAgentBench chat logs into Cedar replay events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import ReplayState
from .models import RecordedTrajectory, ReplayEvent

EXPERIMENT_FILES: dict[str, tuple[str, str]] = {
    "eval_results_ori_raw.json": ("Original", "Raw"),
    "eval_results_ori_golden.json": ("Original", "Baseline"),
    "eval_results_ori_full.json": ("Original", "Guardrail"),
    "eval_results_safety_raw.json": ("Adversarial", "Raw"),
    "eval_results_safety_golden.json": ("Adversarial", "Baseline"),
    "eval_results_safety_full.json": ("Adversarial", "Guardrail"),
}


class MedAgentBenchTrajectoryAdapter:
    """Adapter for the OpenAI-style trajectories stored by the source repo."""

    def load_file(
        self,
        path: str | Path,
        *,
        dataset: str | None = None,
        condition: str | None = None,
    ) -> tuple[RecordedTrajectory, ...]:
        source = Path(path)
        inferred = EXPERIMENT_FILES.get(source.name)
        if inferred:
            dataset = dataset or inferred[0]
            condition = condition or inferred[1]
        if not dataset or not condition:
            raise ValueError(f"cannot infer dataset/condition from {source.name}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        raw_trajectories = payload.get("full_trajectory")
        if not isinstance(raw_trajectories, list):
            raise ValueError(f"{source} has no full_trajectory list")
        return tuple(
            self.adapt(item, dataset=dataset, condition=condition)
            for item in raw_trajectories
        )

    def load_experiment_directory(
        self, root: str | Path
    ) -> dict[str, tuple[RecordedTrajectory, ...]]:
        directory = Path(root)
        missing = [name for name in EXPERIMENT_FILES if not (directory / name).exists()]
        if missing:
            raise FileNotFoundError(f"missing MedAgentBench result files: {missing}")
        return {name: self.load_file(directory / name) for name in EXPERIMENT_FILES}

    def adapt(
        self,
        raw: dict[str, Any],
        *,
        dataset: str,
        condition: str,
    ) -> RecordedTrajectory:
        trajectory_id = str(raw.get("id", ""))
        messages = raw.get("trajectory")
        if not trajectory_id or not isinstance(messages, list):
            raise ValueError("invalid MedAgentBench trajectory record")

        state = ReplayState()
        events: list[ReplayEvent] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role == "user" and isinstance(content, str):
                state.observe_user(content)
            elif role == "assistant" and isinstance(content, str):
                state.observe_assistant(content)

            calls = message.get("tool_calls")
            if isinstance(calls, list):
                for index, call in enumerate(calls):
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function")
                    if not isinstance(function, dict):
                        continue
                    tool = str(function.get("name", ""))
                    if not tool:
                        continue
                    prepared = state.prepare_call(tool, function.get("arguments"))
                    call_id = str(
                        call.get("id") or f"{trajectory_id}:call:{len(events)}:{index}"
                    )
                    state.register_call(call_id, prepared)
                    events.append(
                        ReplayEvent(
                            stage="PreToolUse",
                            tool=tool,
                            arguments=prepared.arguments,
                            session=prepared.session,
                            medical=prepared.medical,
                            is_post=prepared.is_post,
                        )
                    )

            if role == "tool":
                call_id = str(message.get("tool_call_id", ""))
                output = content if isinstance(content, str) else json.dumps(content)
                prepared = state.pending.get(call_id)
                tool = prepared.tool if prepared else "unknown_tool"
                events.append(
                    ReplayEvent(
                        stage="ToolOutput",
                        tool=tool,
                        output=output,
                        session=state.session_snapshot(),
                    )
                )
                state.observe_output(call_id, output)

        return RecordedTrajectory(
            id=trajectory_id,
            dataset=dataset,
            condition=condition,
            events=tuple(events),
        )
