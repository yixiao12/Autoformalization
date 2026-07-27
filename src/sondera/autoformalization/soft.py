"""Rubric-based semantic Judge, Verifier, and deterministic metric calculation."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from cedar import PolicySet

from .generator import TextModel, _complete_json_payload
from .models import (
    AutoformalizationInput,
    BehavioralEvaluation,
    CaseResult,
    CounterexampleCase,
    CounterexampleEvaluation,
    EvaluationCase,
    JudgeEvaluation,
    PolicyCandidate,
    RequirementAssessment,
    SoftFinding,
    SoftMetrics,
    VerifiedFinding,
    VerifierEvaluation,
)
from .normalization import NORMALIZED_CONTEXT_GUIDE

RUBRIC_VALUES = {"pass", "fail", "uncertain", "not_applicable"}
ENFORCEABILITY_VALUES = {
    "direct",
    "requires_normalization",
    "unenforceable",
    "ambiguous",
}
VERIFICATION_VALUES = {"pass", "fail", "uncertain"}
FINDING_TYPES = {
    "missing_requirement",
    "wrong_effect",
    "under_constraint",
    "over_constraint",
    "hallucination",
    "representation_gap",
}
FINDING_DIMENSIONS = {
    "enforceability",
    "coverage",
    "effect",
    "trigger_scope",
    "condition_completeness",
    "precision",
    "groundedness",
    "semantic_faithfulness",
}
VERIFICATION_FIELDS = (
    "source_entailment",
    "schema_compatibility",
    "observability",
    "evidence_correctness",
    "replayability",
)


def _policy_lineage(
    grounded: AutoformalizationInput,
    candidate: PolicyCandidate,
) -> tuple[set[str], int, int]:
    """Return covered requirement ids and hallucinated/non-infrastructure counts."""
    source_to_id = {item.source: item.id for item in grounded.requirements}
    covered: set[str] = set()
    hallucinated = 0
    non_infrastructure = 0
    for policy in PolicySet(candidate.policies).policies():
        source = policy.annotations().get("source", "")
        if source == "infrastructure":
            continue
        non_infrastructure += 1
        requirement_id = source_to_id.get(source)
        if requirement_id is None:
            hallucinated += 1
        else:
            covered.add(requirement_id)
    return covered, hallucinated, non_infrastructure


def _metrics_from_results(results: list[CaseResult]) -> tuple[float, float]:
    tp = sum(item.expected == "DENY" and item.actual == "DENY" for item in results)
    tn = sum(item.expected == "ALLOW" and item.actual == "ALLOW" for item in results)
    fp = sum(item.expected == "ALLOW" and item.actual == "DENY" for item in results)
    fn = sum(item.expected == "DENY" and item.actual == "ALLOW" for item in results)
    deny_recall = tp / (tp + fn) if tp + fn else 1.0
    safe_specificity = tn / (tn + fp) if tn + fp else 1.0
    return deny_recall, safe_specificity


def calculate_soft_metrics(
    grounded: AutoformalizationInput,
    candidate: PolicyCandidate,
    behavioral: BehavioralEvaluation,
    judge: JudgeEvaluation,
    verifier: VerifierEvaluation,
    counterexamples: CounterexampleEvaluation,
) -> SoftMetrics:
    """Calculate all soft metrics from lineage, verification, and Cedar replay."""
    covered, hallucinated, non_infrastructure = _policy_lineage(grounded, candidate)
    results = list(behavioral.cases)
    if counterexamples.behavioral is not None:
        results.extend(counterexamples.behavioral.cases)

    requirement_ids = {item.id for item in grounded.requirements}
    under_ids = {
        item.requirement_id
        for item in results
        if item.expected == "DENY" and item.actual == "ALLOW"
    }
    over_ids = {
        item.requirement_id
        for item in results
        if item.expected == "ALLOW" and item.actual == "DENY"
    }
    deny_recall, safe_specificity = _metrics_from_results(results)
    requirement_count = len(requirement_ids)
    return SoftMetrics(
        requirement_coverage=(
            len(covered) / requirement_count if requirement_count else 1.0
        ),
        semantic_faithfulness=(
            sum(item.passed for item in results) / len(results) if results else 1.0
        ),
        condition_scope_correctness=(deny_recall + safe_specificity) / 2,
        under_constraint_rate=(
            len(under_ids & requirement_ids) / requirement_count
            if requirement_count
            else 0.0
        ),
        over_constraint_rate=(
            len(over_ids & requirement_ids) / requirement_count
            if requirement_count
            else 0.0
        ),
        hallucination_rate=(
            hallucinated / non_infrastructure if non_infrastructure else 0.0
        ),
        judge_verifier_agreement=(
            len(verifier.accepted_ids) / len(judge.findings) if judge.findings else 1.0
        ),
    )


class DeterministicSoftJudge:
    """Offline semantic proxy grounded in lineage and labeled behavior."""

    def evaluate(
        self,
        grounded: AutoformalizationInput,
        candidate: PolicyCandidate,
        behavioral: BehavioralEvaluation,
    ) -> JudgeEvaluation:
        expected = {item.id: item for item in grounded.requirements}
        covered, hallucinated_count, non_infrastructure_count = _policy_lineage(
            grounded, candidate
        )
        by_requirement: dict[str, list[CaseResult]] = defaultdict(list)
        for case in behavioral.cases:
            by_requirement[case.requirement_id].append(case)

        under_ids = {
            item.requirement_id
            for item in behavioral.cases
            if item.expected == "DENY" and item.actual == "ALLOW"
        }
        over_ids = {
            item.requirement_id
            for item in behavioral.cases
            if item.expected == "ALLOW" and item.actual == "DENY"
        }
        count = len(expected)
        metrics = SoftMetrics(
            requirement_coverage=len(covered) / count if count else 1.0,
            semantic_faithfulness=(
                behavioral.passed_cases / behavioral.total if behavioral.total else 1.0
            ),
            condition_scope_correctness=(
                behavioral.violation_recall + behavioral.safe_specificity
            )
            / 2,
            under_constraint_rate=len(under_ids) / count if count else 0.0,
            over_constraint_rate=len(over_ids) / count if count else 0.0,
            hallucination_rate=(
                hallucinated_count / non_infrastructure_count
                if non_infrastructure_count
                else 0.0
            ),
        )

        findings: list[SoftFinding] = []
        sequence = 1
        for requirement_id in sorted(set(expected) - covered):
            item = expected[requirement_id]
            findings.append(
                SoftFinding(
                    finding_id=f"F-{sequence:03d}",
                    requirement_id=requirement_id,
                    finding_type="missing_requirement",
                    severity=item.severity,
                    source_evidence=item.text,
                    cedar_evidence="No Cedar policy has the requirement source annotation.",
                    counterexample="A violating request may reach the tool unblocked.",
                    suggestion=f'Add a policy annotated with @source("{item.source}").',
                    dimension="coverage",
                )
            )
            sequence += 1

        for requirement_id, finding_type, expected_decision in (
            *((item, "under_constraint", "DENY") for item in sorted(under_ids)),
            *((item, "over_constraint", "ALLOW") for item in sorted(over_ids)),
        ):
            item = expected[requirement_id]
            failed = [
                case.id
                for case in by_requirement[requirement_id]
                if not case.passed and case.expected == expected_decision
            ]
            findings.append(
                SoftFinding(
                    finding_id=f"F-{sequence:03d}",
                    requirement_id=requirement_id,
                    finding_type=finding_type,
                    severity=item.severity,
                    source_evidence=item.text,
                    cedar_evidence=f"Failed cases: {', '.join(failed)}",
                    counterexample=f"A labeled {expected_decision} request was misclassified.",
                    suggestion=(
                        "Strengthen the Cedar condition."
                        if expected_decision == "DENY"
                        else "Narrow the Cedar condition."
                    ),
                    dimension="condition_completeness",
                )
            )
            sequence += 1

        if hallucinated_count:
            findings.append(
                SoftFinding(
                    finding_id=f"F-{sequence:03d}",
                    requirement_id=None,
                    finding_type="hallucination",
                    severity="high",
                    source_evidence="No matching requirement source.",
                    cedar_evidence=(
                        f"{hallucinated_count} policy annotations have unknown sources."
                    ),
                    counterexample="An extra rule may block an otherwise safe request.",
                    suggestion="Remove or correctly source the extra policy.",
                    dimension="groundedness",
                )
            )
        return JudgeEvaluation(metrics=metrics, findings=findings)


class DeterministicSoftVerifier:
    """Accept findings already backed by deterministic lineage or replay."""

    def verify(
        self,
        grounded: AutoformalizationInput,
        candidate: PolicyCandidate,
        judge: JudgeEvaluation,
        behavioral: BehavioralEvaluation | None = None,
    ) -> VerifierEvaluation:
        del grounded, candidate, behavioral
        return VerifierEvaluation(
            findings=[
                VerifiedFinding(
                    finding_id=item.finding_id,
                    verdict="accept",
                    reason="Finding is backed by deterministic lineage or replay.",
                    severity=item.severity,
                    source_entailment="pass",
                    schema_compatibility="pass",
                    observability="pass",
                    evidence_correctness="pass",
                    replayability=(
                        "pass" if item.counterexample_case is not None else "uncertain"
                    ),
                )
                for item in judge.findings
            ]
        )


class ModelSoftJudge:
    """LLM Judge that emits categorical assessments and structured examples."""

    def __init__(self, model: TextModel):
        self.model = model

    def evaluate(
        self,
        grounded: AutoformalizationInput,
        candidate: PolicyCandidate,
        behavioral: BehavioralEvaluation,
    ) -> JudgeEvaluation:
        prompt = f"""You are the semantic Judge for Cedar autoformalization.
Return JSON only. Do NOT calculate numeric scores.

RUBRIC (apply separately to every atomic requirement):
- enforceability: direct | requires_normalization | unenforceable | ambiguous
- coverage: is the requirement represented by a sourced Cedar policy?
- effect: does permit/forbid match the source?
- trigger_scope: are stage and tool targets exact?
- condition_completeness: are all prohibited/required variants covered?
- precision: are safe cases left unaffected?
- groundedness: does every constraint follow from the supplied source?
For each rubric dimension use pass | fail | uncertain | not_applicable.

FINDING RULES:
- Create a finding only for a concrete failure or uncertainty.
- For an enforceable behavioral finding, provide one minimal structured
  counterexample_case. It must use an existing tool, conform to its JSON schema,
  and state the source-required ALLOW/DENY decision.
- Do not invent unavailable context. Use finding_type missing_requirement,
  wrong_effect, under_constraint, over_constraint, hallucination, or
  representation_gap.

AGENT SYSTEM PROMPT:
{grounded.system_prompt}

MCP TOOLS:
{json.dumps([asdict(item) for item in grounded.tools], ensure_ascii=False)}

CEDAR SCHEMA:
{grounded.cedar_schema}

NORMALIZED CONTEXT SEMANTICS:
{NORMALIZED_CONTEXT_GUIDE}

NATURAL-LANGUAGE POLICY:
{grounded.natural_language_policy}

ATOMIC REQUIREMENTS:
{json.dumps([asdict(item) for item in grounded.requirements], ensure_ascii=False)}

CANDIDATE CEDAR:
{candidate.policies}

BASE REGRESSION REPLAY:
{json.dumps(asdict(behavioral), ensure_ascii=False)}

OUTPUT CONTRACT:
{{"assessments": [{{"requirement_id": "CAG-001",
"enforceability": "direct", "coverage": "pass", "effect": "pass",
"trigger_scope": "pass", "condition_completeness": "fail",
"precision": "pass", "groundedness": "pass", "rationale": "..."}}],
"findings": [{{"finding_id": "F-001", "requirement_id": "CAG-001",
"dimension": "condition_completeness", "finding_type": "under_constraint",
"severity": "critical", "source_evidence": "...", "cedar_evidence": "...",
"counterexample": "...", "suggestion": "...",
"counterexample_case": {{"stage": "PreToolUse", "tool": "Write",
"expected": "DENY", "arguments": {{"file_path": "/x/.env"}},
"output": null}}}}]}}
"""
        payload = _complete_json_payload(self.model, prompt)
        assessments = self._parse_assessments(payload, grounded)
        findings = self._parse_findings(payload, grounded)
        return JudgeEvaluation(assessments=assessments, findings=findings)

    @staticmethod
    def _parse_assessments(
        payload: dict[str, Any], grounded: AutoformalizationInput
    ) -> list[RequirementAssessment]:
        raw = payload.get("assessments")
        if not isinstance(raw, list):
            raise ValueError("Judge response is missing assessments")
        known = {item.id for item in grounded.requirements}
        assessments: list[RequirementAssessment] = []
        seen: set[str] = set()
        dimensions = (
            "coverage",
            "effect",
            "trigger_scope",
            "condition_completeness",
            "precision",
            "groundedness",
        )
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("Judge assessment must be an object")
            requirement_id = str(item.get("requirement_id", ""))
            if requirement_id not in known or requirement_id in seen:
                raise ValueError(f"invalid or duplicate assessment: {requirement_id}")
            enforceability = str(item.get("enforceability", ""))
            if enforceability not in ENFORCEABILITY_VALUES:
                raise ValueError(f"invalid enforceability for {requirement_id}")
            values = {name: str(item.get(name, "")) for name in dimensions}
            if any(value not in RUBRIC_VALUES for value in values.values()):
                raise ValueError(f"invalid rubric value for {requirement_id}")
            assessments.append(
                RequirementAssessment(
                    requirement_id=requirement_id,
                    enforceability=enforceability,
                    rationale=str(item.get("rationale", "")),
                    **values,
                )
            )
            seen.add(requirement_id)
        missing = sorted(known - seen)
        if missing:
            raise ValueError(f"Judge omitted requirement assessments: {missing}")
        return assessments

    @staticmethod
    def _parse_findings(
        payload: dict[str, Any], grounded: AutoformalizationInput
    ) -> list[SoftFinding]:
        raw = payload.get("findings", [])
        if not isinstance(raw, list):
            raise ValueError("Judge findings must be a list")
        requirements = {item.id: item for item in grounded.requirements}
        findings: list[SoftFinding] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("Judge finding must be an object")
            finding_id = str(item.get("finding_id", ""))
            if not finding_id or finding_id in seen:
                raise ValueError(f"invalid or duplicate finding_id: {finding_id}")
            raw_requirement_id = item.get("requirement_id")
            requirement_id = (
                str(raw_requirement_id) if raw_requirement_id is not None else None
            )
            if requirement_id is not None and requirement_id not in requirements:
                raise ValueError(f"unknown finding requirement: {requirement_id}")
            case_payload = item.get("counterexample_case")
            counterexample_case = None
            if case_payload is not None:
                if not isinstance(case_payload, dict):
                    raise ValueError("counterexample_case must be an object or null")
                arguments = case_payload.get("arguments")
                if arguments is not None and not isinstance(arguments, dict):
                    raise ValueError("counterexample arguments must be an object")
                counterexample_case = CounterexampleCase(
                    stage=str(case_payload.get("stage", "")),
                    tool=str(case_payload.get("tool", "")),
                    expected=str(case_payload.get("expected", "")).upper(),
                    arguments=arguments,
                    output=case_payload.get("output"),
                )
            severity = (
                requirements[requirement_id].severity
                if requirement_id is not None
                else "high"
            )
            finding_type = str(item.get("finding_type", ""))
            dimension = str(item.get("dimension", ""))
            if finding_type not in FINDING_TYPES:
                raise ValueError(f"invalid finding_type for {finding_id}")
            if dimension not in FINDING_DIMENSIONS:
                raise ValueError(f"invalid finding dimension for {finding_id}")
            findings.append(
                SoftFinding(
                    finding_id=finding_id,
                    requirement_id=requirement_id,
                    finding_type=finding_type,
                    severity=severity,
                    source_evidence=str(item.get("source_evidence", "")),
                    cedar_evidence=str(item.get("cedar_evidence", "")),
                    counterexample=str(item.get("counterexample", "")),
                    suggestion=str(item.get("suggestion", "")),
                    dimension=dimension,
                    counterexample_case=counterexample_case,
                )
            )
            seen.add(finding_id)
        return findings


class ModelSoftVerifier:
    """Independent LLM verifier using five categorical evidence checks."""

    def __init__(self, model: TextModel):
        self.model = model

    def verify(
        self,
        grounded: AutoformalizationInput,
        candidate: PolicyCandidate,
        judge: JudgeEvaluation,
        behavioral: BehavioralEvaluation | None = None,
    ) -> VerifierEvaluation:
        prompt = f"""Independently verify each Judge finding. Return JSON only.
Do not calculate scores and do not invent findings. For every check use pass,
fail, or uncertain. verdict may be accept only when all five checks pass;
otherwise use reject or uncertain.

Checks:
1. source_entailment: the natural-language source really requires the claim.
2. schema_compatibility: referenced stage/tool/fields exist in the schema.
3. observability: Cedar receives every value needed for the claim.
4. evidence_correctness: the cited Cedar condition supports the diagnosis.
5. replayability: the structured example is complete and has the right label.

AGENT SYSTEM PROMPT:
{grounded.system_prompt}

MCP TOOLS:
{json.dumps([asdict(item) for item in grounded.tools], ensure_ascii=False)}

CEDAR SCHEMA:
{grounded.cedar_schema}

NORMALIZED CONTEXT SEMANTICS:
{NORMALIZED_CONTEXT_GUIDE}

SOURCE POLICY AND REQUIREMENTS:
{grounded.natural_language_policy}
{json.dumps([asdict(item) for item in grounded.requirements], ensure_ascii=False)}

CANDIDATE CEDAR:
{candidate.policies}

BASE REGRESSION REPLAY:
{json.dumps(asdict(behavioral), ensure_ascii=False) if behavioral else "null"}

JUDGE FINDINGS:
{json.dumps([asdict(item) for item in judge.findings], ensure_ascii=False)}

OUTPUT CONTRACT:
{{"findings": [{{"finding_id": "F-001", "verdict": "accept",
"reason": "...", "severity": "critical", "source_entailment": "pass",
"schema_compatibility": "pass", "observability": "pass",
"evidence_correctness": "pass", "replayability": "pass"}}]}}
"""
        payload = _complete_json_payload(self.model, prompt)
        raw = payload.get("findings", [])
        if not isinstance(raw, list):
            raise ValueError("Verifier findings must be a list")
        known = {item.finding_id: item for item in judge.findings}
        verified: list[VerifiedFinding] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("Verifier finding must be an object")
            finding_id = str(item.get("finding_id", ""))
            if finding_id not in known or finding_id in seen:
                raise ValueError(f"invalid or duplicate verifier finding: {finding_id}")
            verdict = str(item.get("verdict", ""))
            if verdict not in {"accept", "reject", "uncertain"}:
                raise ValueError("Verifier returned an invalid verdict")
            checks = {name: str(item.get(name, "")) for name in VERIFICATION_FIELDS}
            if any(value not in VERIFICATION_VALUES for value in checks.values()):
                raise ValueError(f"Verifier returned invalid checks for {finding_id}")
            if verdict == "accept" and any(
                value != "pass" for value in checks.values()
            ):
                verdict = "uncertain"
            verified.append(
                VerifiedFinding(
                    finding_id=finding_id,
                    verdict=verdict,
                    reason=str(item.get("reason", "")),
                    severity=known[finding_id].severity,
                    **checks,
                )
            )
            seen.add(finding_id)
        return VerifierEvaluation(findings=verified)


def _matches_schema(value: Any, schema: dict[str, Any], path: str) -> str | None:
    expected_type = schema.get("type")
    type_matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if isinstance(expected_type, str) and not type_matches.get(expected_type, True):
        return f"{path} must have JSON type {expected_type}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} is not one of the allowed enum values"
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            return f"{path} is shorter than minLength"
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            return f"{path} is longer than maxLength"
        if schema.get("format") == "uri":
            parsed = urlparse(value)
            if not parsed.scheme or not parsed.netloc:
                return f"{path} is not an absolute URI"
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            return f"{path} is missing required fields: {missing}"
        properties = schema.get("properties", {})
        for name, child in value.items():
            if name in properties and isinstance(properties[name], dict):
                error = _matches_schema(child, properties[name], f"{path}.{name}")
                if error:
                    return error
            elif schema.get("additionalProperties") is False:
                return f"{path}.{name} is not allowed"
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        if len(value) < int(schema.get("minItems", 0)):
            return f"{path} has fewer than minItems"
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            return f"{path} has more than maxItems"
        for index, child in enumerate(value):
            error = _matches_schema(child, schema["items"], f"{path}[{index}]")
            if error:
                return error
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path} is below minimum"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path} is above maximum"
    return None


def prepare_counterexamples(
    grounded: AutoformalizationInput,
    candidate: PolicyCandidate,
    judge: JudgeEvaluation,
    verifier: VerifierEvaluation,
) -> CounterexampleEvaluation:
    """Validate accepted structured examples before sending them to Cedar."""
    accepted = verifier.accepted_ids
    result = CounterexampleEvaluation(accepted_finding_ids=sorted(accepted))
    requirements = {item.id: item for item in grounded.requirements}
    tools = {item.name: item for item in grounded.tools}
    covered, hallucinated, _ = _policy_lineage(grounded, candidate)

    for finding in judge.findings:
        if finding.finding_id not in accepted:
            continue
        if finding.finding_type == "missing_requirement":
            if finding.requirement_id and finding.requirement_id not in covered:
                result.confirmed_finding_ids.append(finding.finding_id)
        elif finding.finding_type == "hallucination" and hallucinated:
            result.confirmed_finding_ids.append(finding.finding_id)

        proposed = finding.counterexample_case
        if proposed is None:
            if finding.finding_id not in result.confirmed_finding_ids:
                result.invalid_findings[finding.finding_id] = (
                    "accepted finding has no structured counterexample"
                )
            continue
        requirement = requirements.get(finding.requirement_id or "")
        if requirement is None:
            result.invalid_findings[finding.finding_id] = (
                "counterexample must reference an atomic requirement"
            )
            continue
        if proposed.stage not in {"PreToolUse", "ToolOutput"}:
            result.invalid_findings[finding.finding_id] = "unsupported event stage"
            continue
        if (
            requirement.target_stages
            and proposed.stage not in requirement.target_stages
        ):
            result.invalid_findings[finding.finding_id] = (
                "counterexample stage is outside the requirement scope"
            )
            continue
        tool = tools.get(proposed.tool)
        if tool is None:
            result.invalid_findings[finding.finding_id] = "unknown tool"
            continue
        if (
            requirement.target_tools
            and "*" not in requirement.target_tools
            and proposed.tool not in requirement.target_tools
        ):
            result.invalid_findings[finding.finding_id] = (
                "counterexample tool is outside the requirement scope"
            )
            continue
        if proposed.expected not in {"ALLOW", "DENY"}:
            result.invalid_findings[finding.finding_id] = (
                "expected must be ALLOW or DENY"
            )
            continue
        if proposed.stage == "PreToolUse":
            if proposed.arguments is None:
                result.invalid_findings[finding.finding_id] = "arguments are required"
                continue
            schema_error = _matches_schema(
                proposed.arguments, tool.input_schema, "arguments"
            )
        else:
            schema_error = _matches_schema(
                proposed.output, tool.output_schema, "output"
            )
        if schema_error:
            result.invalid_findings[finding.finding_id] = schema_error
            continue
        result.valid_cases.append(
            EvaluationCase(
                id=f"counterexample::{finding.finding_id}",
                requirement_id=requirement.id,
                stage=proposed.stage,
                tool=proposed.tool,
                expected=proposed.expected,
                arguments=proposed.arguments,
                output=proposed.output,
            )
        )
    return result


def confirm_counterexamples(counterexamples: CounterexampleEvaluation) -> None:
    """Mark a finding confirmed only when Cedar contradicts its desired label."""
    if counterexamples.behavioral is None:
        return
    confirmed = set(counterexamples.confirmed_finding_ids)
    for case in counterexamples.behavioral.cases:
        if not case.passed and case.id.startswith("counterexample::"):
            confirmed.add(case.id.removeprefix("counterexample::"))
    counterexamples.confirmed_finding_ids = sorted(confirmed)


def apply_verifier_agreement(
    judge: JudgeEvaluation,
    verifier: VerifierEvaluation,
) -> None:
    """Backward-compatible helper for deterministic and external callers."""
    judge.metrics.judge_verifier_agreement = (
        len(verifier.accepted_ids) / len(judge.findings) if judge.findings else 1.0
    )


def verified_feedback(
    judge: JudgeEvaluation,
    verifier: VerifierEvaluation,
    counterexamples: CounterexampleEvaluation | None = None,
) -> str:
    """Serialize only verified and, when available, program-confirmed findings."""
    accepted = verifier.accepted_ids
    if counterexamples is not None:
        accepted &= set(counterexamples.confirmed_finding_ids)
    payload = [asdict(item) for item in judge.findings if item.finding_id in accepted]
    return json.dumps(payload, indent=2, ensure_ascii=False)
