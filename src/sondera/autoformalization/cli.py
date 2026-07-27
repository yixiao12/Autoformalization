"""Command-line runner for autoformalization experiments."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .behavior import CedarBehavioralEvaluator
from .config import ModelSettings, load_env_file, load_model_settings
from .dataset import DatasetBundle
from .generator import FixturePolicyGenerator, LiteLLMTextModel, ModelPolicyGenerator
from .hard import CedarHardEvaluator
from .soft import (
    DeterministicSoftJudge,
    DeterministicSoftVerifier,
    ModelSoftJudge,
    ModelSoftVerifier,
)
from .spec import CedarSchemaGenerator
from .workflow import AutoformalizationWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and evaluate Cedar policies from Agent instructions"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--agent-id", default="coding_agent")
    parser.add_argument("--provider", default="custom")
    parser.add_argument("--generator", choices=("fixture", "model"), required=True)
    parser.add_argument("--fixture-policy", type=Path)
    parser.add_argument("--generator-model")
    parser.add_argument("--soft", choices=("deterministic", "model"), required=True)
    parser.add_argument("--judge-model")
    parser.add_argument("--verifier-model")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument(
        "--cedar-cli",
        type=Path,
        help="absolute path to the official cedar-policy-cli binary",
    )
    parser.add_argument("--output", type=Path)
    return parser


def _configured_model(
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


async def run(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    model_settings = load_model_settings(args.config) if args.config else None
    dataset = DatasetBundle.load(
        args.dataset,
        agent_id=args.agent_id,
        provider=args.provider,
    )
    generated_schema = CedarSchemaGenerator().generate(dataset.spec)
    grounded = dataset.grounded(generated_schema)

    if args.generator == "fixture":
        fixture = args.fixture_policy or args.dataset / "gold.cedar"
        if not fixture.exists():
            raise ValueError(
                "fixture generator requires --fixture-policy or gold.cedar"
            )
        generator = FixturePolicyGenerator.from_path(fixture)
    else:
        generator_model = args.generator_model or (
            model_settings.model if model_settings else None
        )
        if not generator_model:
            raise ValueError("model generator requires --generator-model")
        generator_text_model = (
            _configured_model(model_settings, generator_model)
            if model_settings
            else LiteLLMTextModel(generator_model)
        )
        generator = ModelPolicyGenerator(generator_text_model)

    if args.soft == "deterministic":
        judge = DeterministicSoftJudge()
        verifier = DeterministicSoftVerifier()
    else:
        judge_model = args.judge_model or (
            model_settings.review_model if model_settings else None
        )
        verifier_model = args.verifier_model or (
            model_settings.review_model if model_settings else None
        )
        if not judge_model or not verifier_model:
            raise ValueError("model soft evaluation requires both model arguments")
        judge_text_model = (
            _configured_model(
                model_settings,
                judge_model,
                temperature=model_settings.judge_temperature,
            )
            if model_settings
            else LiteLLMTextModel(judge_model, temperature=0.3)
        )
        verifier_text_model = (
            _configured_model(
                model_settings,
                verifier_model,
                temperature=model_settings.verifier_temperature,
            )
            if model_settings
            else LiteLLMTextModel(verifier_model, temperature=0.1)
        )
        judge = ModelSoftJudge(judge_text_model)
        verifier = ModelSoftVerifier(verifier_text_model)

    workflow = AutoformalizationWorkflow(
        generator=generator,
        hard_evaluator=CedarHardEvaluator(args.cedar_cli),
        behavioral_evaluator=CedarBehavioralEvaluator(),
        judge=judge,
        verifier=verifier,
        max_rounds=args.max_rounds,
    )
    report = await workflow.run(
        grounded,
        schema=generated_schema,
        spec=dataset.spec,
        cases=dataset.cases,
    )

    output = args.output or args.dataset / "results" / "latest"
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output / "generated.cedarschema").write_text(
        generated_schema.text,
        encoding="utf-8",
    )
    (output / "generated.cedar").write_text(
        report.final_round.candidate.policies,
        encoding="utf-8",
    )
    (output / "generator_prompt.txt").write_text(
        report.final_round.prompt,
        encoding="utf-8",
    )

    final = report.final_round
    behavior = final.behavioral
    aggregate = report.aggregate_metrics()
    summary = {
        "success": report.success,
        "stop_reason": report.stop_reason,
        "rounds": len(report.rounds),
        "hard_pass": final.hard.passed,
        "soft_pass": final.soft_pass,
        "schema_matches_expected": (
            generated_schema.text.strip() == dataset.expected_schema.strip()
            if dataset.expected_schema is not None
            else None
        ),
        "cases_passed": behavior.passed_cases if behavior else 0,
        "cases_total": behavior.total if behavior else len(dataset.cases),
        "macro_f1": aggregate.get("macro_f1", 0.0),
        "soft_score": aggregate.get("soft_score", 0.0),
        "output": str(output),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if report.success and behavior and behavior.all_passed else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args))
