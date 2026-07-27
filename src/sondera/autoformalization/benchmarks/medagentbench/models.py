"""Data models for replaying MedAgentBench conversation traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReplayEvent:
    """One Cedar-replayable event derived from a recorded chat message."""

    stage: str
    tool: str
    arguments: dict[str, Any] | None = None
    output: str | None = None
    session: dict[str, object] = field(default_factory=dict)
    medical: dict[str, object] = field(default_factory=dict)
    is_post: bool = False


@dataclass(frozen=True)
class RecordedTrajectory:
    """A complete benchmark task trajectory in Cedar event form."""

    id: str
    dataset: str
    condition: str
    events: tuple[ReplayEvent, ...]

    @property
    def has_post(self) -> bool:
        return any(
            event.stage == "PreToolUse" and event.is_post for event in self.events
        )


@dataclass(frozen=True)
class ReplayEventResult:
    """Cedar decision for one adapted event."""

    stage: str
    tool: str
    decision: str
    policy_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrajectoryReplayResult:
    """Aggregate Cedar result for one recorded trajectory."""

    id: str
    dataset: str
    condition: str
    has_post: bool
    blocked: bool
    events: tuple[ReplayEventResult, ...]


@dataclass
class ReplayGroupResult:
    """Paper-compatible block-rate metrics for one dataset/condition group."""

    dataset: str
    condition: str
    source_file: str
    trajectories: list[TrajectoryReplayResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.trajectories)

    @property
    def blocked(self) -> int:
        return sum(item.blocked for item in self.trajectories)

    @property
    def block_rate(self) -> float:
        return self.blocked / self.total if self.total else 0.0

    @property
    def post_total(self) -> int:
        return sum(item.has_post for item in self.trajectories)

    @property
    def post_blocked(self) -> int:
        return sum(item.has_post and item.blocked for item in self.trajectories)

    @property
    def post_block_rate(self) -> float:
        return self.post_blocked / self.post_total if self.post_total else 0.0

    def policy_firings(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for trajectory in self.trajectories:
            for event in trajectory.events:
                for policy_id in event.policy_ids:
                    counts[policy_id] = counts.get(policy_id, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def to_dict(self, *, include_trajectories: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "dataset": self.dataset,
            "condition": self.condition,
            "source_file": self.source_file,
            "all_trajectories": {
                "blocked": self.blocked,
                "total": self.total,
                "block_rate": self.block_rate,
            },
            "trajectories_with_post": {
                "blocked": self.post_blocked,
                "total": self.post_total,
                "block_rate": self.post_block_rate,
            },
            "policy_firings": self.policy_firings(),
        }
        if include_trajectories:
            payload["trajectories"] = [asdict(item) for item in self.trajectories]
        return payload
