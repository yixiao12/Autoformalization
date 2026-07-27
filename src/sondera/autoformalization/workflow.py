"""Generator-critic workflow orchestration."""

from __future__ import annotations

from typing import Protocol

from cedar import PolicySet

from .behavior import CedarBehavioralEvaluator
from .generator import PolicyGenerator
from .hard import CedarHardEvaluator
from .models import (
    AutoformalizationInput,
    BehavioralEvaluation,
    CounterexampleEvaluation,
    EvaluationCase,
    JudgeEvaluation,
    PolicyCandidate,
    RoundEvaluation,
    VerifierEvaluation,
    WorkflowReport,
)
from .prompt import HierarchicalPromptBuilder
from .soft import (
    calculate_soft_metrics,
    confirm_counterexamples,
    prepare_counterexamples,
    verified_feedback,
)
from .spec import AgentSpec, GeneratedSchema


class SoftJudge(Protocol):
    def evaluate(
        self,
        grounded: AutoformalizationInput,
        candidate: PolicyCandidate,
        behavioral: BehavioralEvaluation,
    ) -> JudgeEvaluation: ...


class SoftVerifier(Protocol):
    def verify(
        self,
        grounded: AutoformalizationInput,
        candidate: PolicyCandidate,
        judge: JudgeEvaluation,
        behavioral: BehavioralEvaluation | None = None,
    ) -> VerifierEvaluation: ...


class AutoformalizationWorkflow:
    """Run the paper-style generator → hard → Judge → Verifier loop."""

    def __init__(
        self,
        *,
        generator: PolicyGenerator,
        hard_evaluator: CedarHardEvaluator,
        behavioral_evaluator: CedarBehavioralEvaluator,
        judge: SoftJudge,
        verifier: SoftVerifier,
        prompt_builder: HierarchicalPromptBuilder | None = None,
        max_rounds: int = 3,
        soft_score_threshold: float = 0.85,
    ):
        if max_rounds < 1:
            raise ValueError("max_rounds must be at least one")
        self.generator = generator
        self.hard_evaluator = hard_evaluator
        self.behavioral_evaluator = behavioral_evaluator
        self.judge = judge
        self.verifier = verifier
        self.prompt_builder = prompt_builder or HierarchicalPromptBuilder()
        self.max_rounds = max_rounds
        self.soft_score_threshold = soft_score_threshold

    @staticmethod
    def _critical_coverage(
        grounded: AutoformalizationInput,
        candidate: PolicyCandidate,
    ) -> float:
        critical_sources = {
            item.source for item in grounded.requirements if item.severity == "critical"
        }
        if not critical_sources:
            return 1.0
        policy_sources = {
            policy.annotations().get("source", "")
            for policy in PolicySet(candidate.policies).policies()
        }
        return len(critical_sources & policy_sources) / len(critical_sources)

    def _soft_pass(
        self,
        grounded: AutoformalizationInput,
        candidate: PolicyCandidate,
        behavioral: BehavioralEvaluation,
        judge: JudgeEvaluation,
        verifier: VerifierEvaluation,
        counterexamples: CounterexampleEvaluation,
    ) -> bool:
        confirmed = set(counterexamples.confirmed_finding_ids)
        accepted_critical = any(
            item.finding_id in confirmed and item.severity == "critical"
            for item in verifier.findings
        )
        return (
            behavioral.all_passed
            and judge.metrics.soft_score >= self.soft_score_threshold
            and self._critical_coverage(grounded, candidate) == 1.0
            and not accepted_critical
        )

    async def run(
        self,
        grounded: AutoformalizationInput,
        *,
        schema: GeneratedSchema,
        spec: AgentSpec,
        cases: tuple[EvaluationCase, ...],
    ) -> WorkflowReport:
        rounds: list[RoundEvaluation] = []
        previous: PolicyCandidate | None = None
        hard_feedback = ""
        soft_feedback = ""

        for round_number in range(1, self.max_rounds + 1):
            prompt = self.prompt_builder.build(
                grounded,
                round_number=round_number,
                previous_candidate=previous,
                hard_feedback=hard_feedback,
                soft_feedback=soft_feedback,
            )
            candidate = self.generator.generate(
                grounded,
                prompt,
                round_number=round_number,
            )
            hard = self.hard_evaluator.evaluate(
                candidate.policies,
                schema.text,
                grounded.requirements,
            )
            record = RoundEvaluation(
                round_number=round_number,
                prompt=prompt,
                candidate=candidate,
                hard=hard,
            )
            rounds.append(record)
            previous = candidate

            if not hard.passed:
                hard_feedback = hard.feedback()
                soft_feedback = ""
                continue

            behavioral = await self.behavioral_evaluator.evaluate(
                candidate.policies,
                schema,
                spec,
                cases,
                grounded.requirements,
            )
            judge = self.judge.evaluate(grounded, candidate, behavioral)
            verifier = self.verifier.verify(grounded, candidate, judge, behavioral)
            counterexamples = prepare_counterexamples(
                grounded, candidate, judge, verifier
            )
            if counterexamples.valid_cases:
                counterexamples.behavioral = await self.behavioral_evaluator.evaluate(
                    candidate.policies,
                    schema,
                    spec,
                    tuple(counterexamples.valid_cases),
                    grounded.requirements,
                )
                confirm_counterexamples(counterexamples)
            judge.metrics = calculate_soft_metrics(
                grounded,
                candidate,
                behavioral,
                judge,
                verifier,
                counterexamples,
            )
            soft_pass = self._soft_pass(
                grounded,
                candidate,
                behavioral,
                judge,
                verifier,
                counterexamples,
            )
            record.behavioral = behavioral
            record.judge = judge
            record.verifier = verifier
            record.counterexamples = counterexamples
            record.soft_pass = soft_pass

            if soft_pass:
                return WorkflowReport(
                    success=True,
                    stop_reason="hard and soft evaluators passed",
                    schema=schema.text,
                    rounds=rounds,
                )

            hard_feedback = "Hard evaluation passed."
            soft_feedback = verified_feedback(judge, verifier, counterexamples)

        return WorkflowReport(
            success=False,
            stop_reason=f"maximum repair rounds reached ({self.max_rounds})",
            schema=schema.text,
            rounds=rounds,
        )
