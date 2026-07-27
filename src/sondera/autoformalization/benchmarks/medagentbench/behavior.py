"""Labeled development-case evaluation with medical replay context."""

from __future__ import annotations

import json
import tempfile

from cedar import PolicySet
from sondera import Event, ToolCall, ToolOutput  # type: ignore[attr-defined]
from sondera.harness.cedar.harness import CedarPolicyHarness
from sondera.harness.trajectory.file_storage import FileTrajectoryStorage

from ...models import (
    BehavioralEvaluation,
    CaseResult,
    EvaluationCase,
    Requirement,
)
from ...spec import AgentSpec, GeneratedSchema
from .context import (
    ReplayContextProvider,
    ReplayState,
    empty_medical_facts,
    empty_session_facts,
)


def _ratio(numerator: int, denominator: int, *, empty: float = 1.0) -> float:
    return numerator / denominator if denominator else empty


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


class MedAgentBenchDevelopmentEvaluator:
    """Evaluate independent labeled calls without using held-out trajectories."""

    async def evaluate(
        self,
        policy_text: str,
        schema: GeneratedSchema,
        spec: AgentSpec,
        cases: tuple[EvaluationCase, ...],
        requirements: tuple[Requirement, ...],
    ) -> BehavioralEvaluation:
        provider = ReplayContextProvider()
        results: list[CaseResult] = []
        severity = {item.id: item.severity for item in requirements}

        with tempfile.TemporaryDirectory(prefix="medagentbench-dev-") as temp:
            harness = CedarPolicyHarness(
                policy_set=PolicySet(policy_text),
                schema=schema.model,
                storage=FileTrajectoryStorage(temp),
                tool_call_context_enricher=provider.enrich_tool_call,
                tool_output_context_enricher=provider.enrich_tool_output,
            )
            for case in cases:
                await harness.initialize(agent=spec.to_agent())
                try:
                    supplied_session = case.context.get("session", {})
                    supplied_medical = case.context.get("medical", {})
                    session = empty_session_facts()
                    medical = empty_medical_facts()
                    if case.stage == "PreToolUse":
                        prepared = ReplayState().prepare_call(
                            case.tool, case.arguments or {}
                        )
                        session.update(prepared.session)
                        medical.update(prepared.medical)
                    session.update(supplied_session)
                    medical.update(supplied_medical)
                    provider.set_context(session=session, medical=medical)

                    if case.stage == "PreToolUse":
                        payload = ToolCall(
                            tool=case.tool,
                            arguments=case.arguments or {},
                        )
                    elif case.stage == "ToolOutput":
                        output = (
                            case.output
                            if isinstance(case.output, str)
                            else json.dumps(case.output, ensure_ascii=False)
                        )
                        payload = ToolOutput.from_success(case.tool, output)
                    else:
                        raise ValueError(f"unsupported evaluation stage: {case.stage}")
                    event = Event(
                        agent=harness.agent,
                        trajectory_id=harness.trajectory_id,
                        event=payload,
                    )
                    adjudicated = await harness.adjudicate(event)
                    actual = str(adjudicated.decision).upper()
                    results.append(
                        CaseResult(
                            id=case.id,
                            requirement_id=case.requirement_id,
                            expected=case.expected,
                            actual=actual,
                            passed=actual == case.expected,
                            triggered_policy_ids=sorted(
                                {item.policy_id for item in adjudicated.metadata or []}
                            ),
                        )
                    )
                finally:
                    await harness.finalize()

        tp = sum(item.expected == "DENY" and item.actual == "DENY" for item in results)
        tn = sum(
            item.expected == "ALLOW" and item.actual == "ALLOW" for item in results
        )
        fp = sum(item.expected == "ALLOW" and item.actual == "DENY" for item in results)
        fn = sum(item.expected == "DENY" and item.actual == "ALLOW" for item in results)
        deny_recall = _ratio(tp, tp + fn)
        deny_precision = _ratio(tp, tp + fp)
        allow_recall = _ratio(tn, tn + fp)
        allow_precision = _ratio(tn, tn + fn)
        critical = [
            item
            for item in results
            if item.expected == "DENY"
            and severity.get(item.requirement_id) == "critical"
        ]
        return BehavioralEvaluation(
            total=len(results),
            passed_cases=sum(item.passed for item in results),
            true_positive=tp,
            true_negative=tn,
            false_positive=fp,
            false_negative=fn,
            violation_recall=deny_recall,
            safe_specificity=allow_recall,
            deny_precision=deny_precision,
            macro_f1=(
                _f1(deny_precision, deny_recall) + _f1(allow_precision, allow_recall)
            )
            / 2,
            critical_rule_recall=_ratio(
                sum(item.actual == "DENY" for item in critical), len(critical)
            ),
            false_block_rate=_ratio(fp, fp + tn, empty=0.0),
            cases=results,
        )
