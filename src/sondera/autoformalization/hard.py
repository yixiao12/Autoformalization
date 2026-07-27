"""Deterministic Cedar hard evaluator backed by the official Cedar CLI."""

from __future__ import annotations

import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from cedar import PolicySet

from .cedar_cli import CedarCli, CedarCliError, CedarCliResult
from .models import HardEvaluation, HardFinding, Requirement

_ANNOTATION_LINE = re.compile(r'^\s*@\w+\("(?:[^"\\]|\\.)*"\)\s*$', re.MULTILINE)
_WHITESPACE = re.compile(r"\s+")


def _normalized_policy(policy_text: str, *, ignore_effect: bool = False) -> str:
    text = _ANNOTATION_LINE.sub("", policy_text)
    text = _WHITESPACE.sub(" ", text).strip()
    if ignore_effect:
        text = re.sub(r"^(permit|forbid)\b", "effect", text)
    return text


def _is_obviously_vacuous(policy_text: str) -> bool:
    compact = _WHITESPACE.sub(" ", policy_text)
    return bool(
        re.search(r"\bwhen\s*\{\s*false\s*\}", compact)
        or re.search(r"\bunless\s*\{\s*true\s*\}", compact)
    )


class CedarHardEvaluator:
    """Parse, validate, and conservatively analyze a Cedar policy set.

    The official Cedar CLI performs policy/schema parsing and strict schema/type
    validation. ``cedar-python`` is used only after those gates pass to inspect
    policies for lineage, redundancy, vacuity, and exact conflicts.
    """

    def __init__(
        self,
        cedar_cli: str | Path | CedarCli | None = None,
        *,
        cli_timeout_seconds: float = 15.0,
    ):
        self.cli = (
            cedar_cli
            if isinstance(cedar_cli, CedarCli)
            else CedarCli(cedar_cli, timeout_seconds=cli_timeout_seconds)
        )

    @staticmethod
    def _diagnostic(check: CedarCliResult) -> str:
        return check.output or f"Cedar CLI exited with code {check.returncode}"

    def evaluate(
        self,
        policy_text: str,
        schema_text: str,
        requirements: tuple[Requirement, ...],
    ) -> HardEvaluation:
        result = HardEvaluation()
        try:
            with tempfile.TemporaryDirectory(prefix="autoformalization-cedar-") as temp:
                directory = Path(temp)
                policy_path = directory / "candidate.cedar"
                schema_path = directory / "generated.cedarschema"
                policy_path.write_text(policy_text, encoding="utf-8")
                schema_path.write_text(schema_text, encoding="utf-8")

                policy_check = self.cli.check_policy(policy_path)
                if not policy_check.passed:
                    result.findings.append(
                        HardFinding("CEDAR_PARSE", self._diagnostic(policy_check))
                    )
                    return result
                result.syntax_pass = True

                schema_check = self.cli.check_schema(schema_path)
                if not schema_check.passed:
                    result.findings.append(
                        HardFinding(
                            "CEDAR_SCHEMA_PARSE", self._diagnostic(schema_check)
                        )
                    )
                    return result

                validation = self.cli.validate(policy_path, schema_path)
                if not validation.passed:
                    result.findings.append(
                        HardFinding(
                            "CEDAR_SCHEMA",
                            self._diagnostic(validation),
                            severity="error",
                        )
                    )
                    return result
        except CedarCliError as exc:
            result.findings.append(HardFinding(exc.code, str(exc)))
            return result

        result.schema_pass = True
        result.reference_pass = True
        result.type_pass = True

        try:
            policy_set = PolicySet(policy_text)
        except Exception as exc:
            result.reference_pass = False
            result.findings.append(
                HardFinding(
                    "CEDAR_ANALYSIS_BINDING",
                    "Cedar CLI accepted the policy, but local structural analysis "
                    f"could not load it: {exc}",
                )
            )
            return result

        policies = list(policy_set.policies())
        result.policy_count = len(policies)
        if not policies:
            result.findings.append(
                HardFinding("EMPTY_POLICY_SET", "candidate contains no Cedar policies")
            )
            return result

        ids: list[str] = []
        observed_sources: set[str] = set()
        bodies: list[str] = []
        scope_effects: dict[str, set[str]] = defaultdict(set)
        vacuous = 0

        for policy in policies:
            annotations = policy.annotations()
            policy_id = annotations.get("id")
            source = annotations.get("source")
            if policy_id:
                ids.append(policy_id)
            else:
                result.findings.append(
                    HardFinding(
                        "MISSING_ID",
                        f"Cedar policy {policy.id()} is missing @id",
                        policy_id=policy.id(),
                    )
                )
            if source:
                observed_sources.add(source)
            else:
                result.findings.append(
                    HardFinding(
                        "MISSING_SOURCE",
                        f"policy {policy_id or policy.id()} is missing @source",
                        policy_id=policy_id or policy.id(),
                    )
                )

            cedar = policy.to_cedar()
            normalized = _normalized_policy(cedar)
            bodies.append(normalized)
            scope_effects[_normalized_policy(cedar, ignore_effect=True)].add(
                str(policy.effect()).lower()
            )
            if _is_obviously_vacuous(cedar):
                vacuous += 1
                result.findings.append(
                    HardFinding(
                        "VACUOUS_POLICY",
                        f"policy {policy_id or policy.id()} has an always-false condition",
                        policy_id=policy_id or policy.id(),
                    )
                )

        duplicate_ids = sorted(key for key, count in Counter(ids).items() if count > 1)
        for policy_id in duplicate_ids:
            result.findings.append(
                HardFinding("DUPLICATE_ID", f"duplicate @id annotation: {policy_id}")
            )

        duplicate_bodies = sum(
            count - 1 for count in Counter(bodies).values() if count > 1
        )
        if duplicate_bodies:
            result.findings.append(
                HardFinding(
                    "REDUNDANT_POLICY",
                    f"found {duplicate_bodies} exact duplicate policy bodies",
                    severity="warning",
                )
            )

        conflicts = [key for key, effects in scope_effects.items() if len(effects) > 1]
        if conflicts:
            result.findings.append(
                HardFinding(
                    "EXACT_CONFLICT",
                    f"found {len(conflicts)} identical scopes with opposite effects",
                )
            )

        expected_sources = {item.source for item in requirements}
        covered_sources = expected_sources & observed_sources
        result.annotation_coverage = (
            len(covered_sources) / len(expected_sources) if expected_sources else 1.0
        )
        for source in sorted(expected_sources - observed_sources):
            result.findings.append(
                HardFinding(
                    "MISSING_REQUIREMENT_SOURCE",
                    f'no Cedar policy is annotated with @source("{source}")',
                    severity="warning",
                )
            )

        result.non_vacuous_ratio = (len(policies) - vacuous) / len(policies)
        result.conflict_free = not conflicts
        result.non_redundant_ratio = (len(policies) - duplicate_bodies) / len(policies)

        # Duplicate IDs are structurally ambiguous even if Cedar accepts them.
        if duplicate_ids:
            result.reference_pass = False
        return result
