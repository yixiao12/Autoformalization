"""High-level generation and replay services used by the CLI and future plugins."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from ...config import ModelSettings, settings_as_safe_dict
from ...dataset import DatasetBundle
from ...generator import LiteLLMTextModel, ModelPolicyGenerator
from ...hard import CedarHardEvaluator
from ...models import WorkflowReport
from ...soft import ModelSoftJudge, ModelSoftVerifier
from ...workflow import AutoformalizationWorkflow
from .behavior import MedAgentBenchDevelopmentEvaluator
from .replay import MedAgentBenchReplayEvaluator, write_report
from .schema import MedAgentBenchSchemaGenerator


def _model(
    settings: ModelSettings,
    model: str,
    *,
    temperature: float | None = None,
) -> LiteLLMTextModel:
    provider = settings.provider
    return LiteLLMTextModel(
        model,
        temperature=temperature,
        provider=provider.name,
        base_url=provider.base_url,
        wire_api=provider.wire_api,
        api_key_env=provider.api_key_env,
        requires_auth=provider.requires_openai_auth,
        reasoning_effort=settings.reasoning_effort,
        store=settings.store,
        max_output_tokens=settings.max_output_tokens,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
        retry_base_seconds=settings.retry_base_seconds,
        stream=settings.stream,
    )


async def generate_policy(
    *,
    dataset_root: str | Path,
    settings: ModelSettings,
    cedar_cli: str | Path,
    output: str | Path,
    max_rounds: int = 3,
    agent_id: str = "medagentbench_agent",
) -> WorkflowReport:
    """Generate and evaluate a MedAgentBench policy without test-trace leakage."""
    dataset = DatasetBundle.load(dataset_root, agent_id=agent_id, provider="custom")
    schema = MedAgentBenchSchemaGenerator().generate(dataset.spec)
    enforceable = tuple(
        requirement
        for requirement in dataset.requirements
        if requirement.enforceability in {"direct", "requires_normalization"}
    )
    enforceable_ids = {requirement.id for requirement in enforceable}
    development_cases = tuple(
        case for case in dataset.cases if case.requirement_id in enforceable_ids
    )
    grounded = replace(dataset.grounded(schema), requirements=enforceable)
    generator = ModelPolicyGenerator(_model(settings, settings.model))
    judge = ModelSoftJudge(
        _model(
            settings,
            settings.review_model,
            temperature=settings.judge_temperature,
        )
    )
    verifier = ModelSoftVerifier(
        _model(
            settings,
            settings.review_model,
            temperature=settings.verifier_temperature,
        )
    )
    workflow = AutoformalizationWorkflow(
        generator=generator,
        hard_evaluator=CedarHardEvaluator(Path(cedar_cli)),
        behavioral_evaluator=MedAgentBenchDevelopmentEvaluator(),  # type: ignore[arg-type]
        judge=judge,
        verifier=verifier,
        max_rounds=max_rounds,
    )
    report = await workflow.run(
        grounded,
        schema=schema,
        spec=dataset.spec,
        cases=development_cases,
    )
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    final = report.final_round
    (directory / "report.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "generated.cedar").write_text(
        final.candidate.policies, encoding="utf-8"
    )
    (directory / "generated.cedarschema").write_text(schema.text, encoding="utf-8")
    (directory / "generator_prompt.txt").write_text(final.prompt, encoding="utf-8")
    (directory / "experiment_manifest.json").write_text(
        json.dumps(
            {
                "dataset_root": str(Path(dataset_root).resolve()),
                "agent_id": agent_id,
                "max_rounds": max_rounds,
                "policy_rules_total": len(dataset.requirements),
                "policy_rules_submitted_as_enforceable": len(enforceable),
                "development_cases": len(development_cases),
                "model": settings_as_safe_dict(settings),
                "held_out_trajectories_used_during_generation": False,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return report


async def replay_policy(
    *,
    dataset_root: str | Path,
    experiment_root: str | Path,
    policy_path: str | Path,
    output: str | Path,
    agent_id: str = "medagentbench_agent",
) -> dict[str, Any]:
    """Replay all six held-out groups and persist both requested result tables."""
    dataset = DatasetBundle.load(dataset_root, agent_id=agent_id, provider="custom")
    schema = MedAgentBenchSchemaGenerator().generate(dataset.spec)
    policy_text = Path(policy_path).read_text(encoding="utf-8")
    report = await MedAgentBenchReplayEvaluator().replay_experiment(
        policy_text,
        schema,
        dataset.spec,
        experiment_root,
    )
    report["policy"] = str(Path(policy_path).resolve())
    report["dataset_root"] = str(Path(dataset_root).resolve())
    write_report(report, output)
    return report
