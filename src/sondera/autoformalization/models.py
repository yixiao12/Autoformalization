"""Shared data models for the autoformalization pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    """Normalized MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


@dataclass(frozen=True)
class Requirement:
    """Atomic natural-language policy requirement."""

    id: str
    source: str
    effect: str
    text: str
    target_stages: tuple[str, ...] = ()
    target_tools: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    severity: str = "medium"
    enforceability: str = "direct"


@dataclass(frozen=True)
class EvaluationCase:
    """A labeled Cedar authorization request."""

    id: str
    requirement_id: str
    stage: str
    tool: str
    expected: str
    arguments: dict[str, Any] | None = None
    output: Any = None
    expected_policy_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutoformalizationInput:
    """All grounded inputs supplied to policy generation."""

    agent_id: str
    provider: str
    system_prompt: str
    tools: tuple[ToolDefinition, ...]
    natural_language_policy: str
    requirements: tuple[Requirement, ...]
    cedar_schema: str


@dataclass
class PolicyCandidate:
    """Structured output returned by a policy generator."""

    policies: str
    requirement_mapping: dict[str, list[str]] = field(default_factory=dict)
    unsupported_requirements: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)


@dataclass
class HardFinding:
    """Deterministic validation finding."""

    code: str
    message: str
    severity: str = "error"
    policy_id: str | None = None


@dataclass
class HardEvaluation:
    """Metrics and findings produced by the hard evaluator."""

    syntax_pass: bool = False
    schema_pass: bool = False
    reference_pass: bool = False
    type_pass: bool = False
    non_vacuous_ratio: float = 0.0
    conflict_free: bool = False
    non_redundant_ratio: float = 0.0
    annotation_coverage: float = 0.0
    policy_count: int = 0
    findings: list[HardFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.syntax_pass
            and self.schema_pass
            and self.reference_pass
            and self.type_pass
            and self.non_vacuous_ratio == 1.0
            and self.conflict_free
        )

    def feedback(self) -> str:
        if not self.findings:
            return "Hard evaluation passed with no findings."
        return "\n".join(f"- [{item.code}] {item.message}" for item in self.findings)


@dataclass
class CaseResult:
    """Actual decision for one labeled evaluation case."""

    id: str
    requirement_id: str
    expected: str
    actual: str
    passed: bool
    triggered_policy_ids: list[str] = field(default_factory=list)


@dataclass
class BehavioralEvaluation:
    """Confusion-matrix metrics from deterministic Cedar replay."""

    total: int
    passed_cases: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    violation_recall: float
    safe_specificity: float
    deny_precision: float
    macro_f1: float
    critical_rule_recall: float
    false_block_rate: float
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed_cases == self.total


@dataclass
class SoftFinding:
    """Semantic issue reported by a Judge."""

    finding_id: str
    requirement_id: str | None
    finding_type: str
    severity: str
    source_evidence: str
    cedar_evidence: str
    counterexample: str
    suggestion: str
    dimension: str = "semantic_faithfulness"
    counterexample_case: CounterexampleCase | None = None


@dataclass(frozen=True)
class CounterexampleCase:
    """Structured, replayable counterexample proposed by the Judge."""

    stage: str
    tool: str
    expected: str
    arguments: dict[str, Any] | None = None
    output: Any = None


@dataclass(frozen=True)
class RequirementAssessment:
    """Categorical rubric assessment for one atomic requirement."""

    requirement_id: str
    enforceability: str
    coverage: str
    effect: str
    trigger_scope: str
    condition_completeness: str
    precision: str
    groundedness: str
    rationale: str


@dataclass
class SoftMetrics:
    """The seven core soft-evaluator metrics from the experiment plan."""

    requirement_coverage: float = 0.0
    semantic_faithfulness: float = 0.0
    condition_scope_correctness: float = 0.0
    under_constraint_rate: float = 0.0
    over_constraint_rate: float = 0.0
    hallucination_rate: float = 0.0
    judge_verifier_agreement: float = 0.0

    @property
    def soft_score(self) -> float:
        return (
            0.30 * self.requirement_coverage
            + 0.25 * self.semantic_faithfulness
            + 0.20 * self.condition_scope_correctness
            + 0.10 * (1.0 - self.under_constraint_rate)
            + 0.10 * (1.0 - self.over_constraint_rate)
            + 0.05 * (1.0 - self.hallucination_rate)
        )


@dataclass
class JudgeEvaluation:
    """Raw output from the semantic Judge."""

    metrics: SoftMetrics = field(default_factory=SoftMetrics)
    assessments: list[RequirementAssessment] = field(default_factory=list)
    findings: list[SoftFinding] = field(default_factory=list)


@dataclass
class VerifiedFinding:
    """Verifier decision for a Judge finding."""

    finding_id: str
    verdict: str
    reason: str
    severity: str
    source_entailment: str = "uncertain"
    schema_compatibility: str = "uncertain"
    observability: str = "uncertain"
    evidence_correctness: str = "uncertain"
    replayability: str = "uncertain"


@dataclass
class VerifierEvaluation:
    """Verifier output and accepted feedback."""

    findings: list[VerifiedFinding] = field(default_factory=list)

    @property
    def accepted_ids(self) -> set[str]:
        return {item.finding_id for item in self.findings if item.verdict == "accept"}


@dataclass
class CounterexampleEvaluation:
    """Validation and Cedar-replay evidence for verified counterexamples."""

    accepted_finding_ids: list[str] = field(default_factory=list)
    valid_cases: list[EvaluationCase] = field(default_factory=list)
    invalid_findings: dict[str, str] = field(default_factory=dict)
    behavioral: BehavioralEvaluation | None = None
    confirmed_finding_ids: list[str] = field(default_factory=list)

    @property
    def proposed_count(self) -> int:
        return len(self.accepted_finding_ids)

    @property
    def valid_count(self) -> int:
        return len(self.valid_cases)

    @property
    def confirmed_count(self) -> int:
        return len(self.confirmed_finding_ids)

    @property
    def counterexample_validity_rate(self) -> float:
        return self.valid_count / self.proposed_count if self.proposed_count else 1.0

    @property
    def finding_confirmation_rate(self) -> float:
        return (
            self.confirmed_count / self.proposed_count if self.proposed_count else 1.0
        )


@dataclass
class RoundEvaluation:
    """Complete record of one generator-critic round."""

    round_number: int
    prompt: str
    candidate: PolicyCandidate
    hard: HardEvaluation
    behavioral: BehavioralEvaluation | None = None
    judge: JudgeEvaluation | None = None
    verifier: VerifierEvaluation | None = None
    counterexamples: CounterexampleEvaluation | None = None
    soft_pass: bool = False


@dataclass
class WorkflowReport:
    """Serializable result of the full autoformalization workflow."""

    success: bool
    stop_reason: str
    schema: str
    rounds: list[RoundEvaluation]

    @property
    def final_round(self) -> RoundEvaluation:
        if not self.rounds:
            raise ValueError("workflow report has no rounds")
        return self.rounds[-1]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["aggregate_metrics"] = self.aggregate_metrics()
        return payload

    def aggregate_metrics(self) -> dict[str, Any]:
        """Return experiment-table metrics derived from all repair rounds."""
        if not self.rounds:
            return {}
        first = self.rounds[0]
        within_three = self.rounds[:3]
        final = self.final_round
        metrics: dict[str, Any] = {
            "parse_pass_at_1": first.hard.syntax_pass,
            "parse_pass_at_3": any(item.hard.syntax_pass for item in within_three),
            "schema_pass_at_1": first.hard.schema_pass,
            "schema_pass_at_3": any(item.hard.schema_pass for item in within_three),
            "hard_pass_at_1": first.hard.passed,
            "hard_pass_at_3": any(item.hard.passed for item in within_three),
            "soft_pass_at_1": first.soft_pass,
            "soft_pass_at_3": any(item.soft_pass for item in within_three),
            "mean_hard_errors": sum(
                sum(finding.severity == "error" for finding in item.hard.findings)
                for item in self.rounds
            )
            / len(self.rounds),
            "repair_rounds": max(0, len(self.rounds) - 1),
            "repair_convergence_rate": 1.0 if self.success else 0.0,
            "annotation_coverage": final.hard.annotation_coverage,
            "non_vacuous_policy_ratio": final.hard.non_vacuous_ratio,
            "non_redundant_policy_ratio": final.hard.non_redundant_ratio,
            "conflict_free": final.hard.conflict_free,
        }
        if final.behavioral is not None:
            metrics.update(
                {
                    "cases_passed": final.behavioral.passed_cases,
                    "cases_total": final.behavioral.total,
                    "violation_recall": final.behavioral.violation_recall,
                    "safe_specificity": final.behavioral.safe_specificity,
                    "deny_precision": final.behavioral.deny_precision,
                    "macro_f1": final.behavioral.macro_f1,
                    "critical_rule_recall": final.behavioral.critical_rule_recall,
                    "false_block_rate": final.behavioral.false_block_rate,
                }
            )
        if final.judge is not None:
            soft = final.judge.metrics
            metrics.update(
                {
                    "requirement_coverage": soft.requirement_coverage,
                    "semantic_faithfulness": soft.semantic_faithfulness,
                    "condition_scope_correctness": soft.condition_scope_correctness,
                    "under_constraint_rate": soft.under_constraint_rate,
                    "over_constraint_rate": soft.over_constraint_rate,
                    "hallucination_rate": soft.hallucination_rate,
                    "judge_verifier_agreement": soft.judge_verifier_agreement,
                    "soft_score": soft.soft_score,
                }
            )
        if final.counterexamples is not None:
            metrics.update(
                {
                    "counterexamples_accepted": final.counterexamples.proposed_count,
                    "counterexamples_valid": final.counterexamples.valid_count,
                    "counterexamples_confirmed": final.counterexamples.confirmed_count,
                    "counterexample_validity_rate": (
                        final.counterexamples.counterexample_validity_rate
                    ),
                    "finding_confirmation_rate": (
                        final.counterexamples.finding_confirmation_rate
                    ),
                }
            )
        return metrics
