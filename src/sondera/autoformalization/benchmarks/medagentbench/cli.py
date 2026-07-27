"""Command line interface for MedAgentBench generation and trajectory replay."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ...config import load_env_file, load_model_settings
from .experiment import generate_policy, replay_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--dataset", type=Path, required=True)
    generate.add_argument("--config", type=Path, required=True)
    generate.add_argument("--env-file", type=Path, default=Path(".env"))
    generate.add_argument("--cedar-cli", type=Path, required=True)
    generate.add_argument("--max-rounds", type=int, default=3)
    generate.add_argument("--output", type=Path, required=True)

    replay = subparsers.add_parser("replay")
    replay.add_argument("--dataset", type=Path, required=True)
    replay.add_argument("--experiment-data", type=Path, required=True)
    replay.add_argument("--policy", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--experiment-data", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--env-file", type=Path, default=Path(".env"))
    run.add_argument("--cedar-cli", type=Path, required=True)
    run.add_argument("--max-rounds", type=int, default=3)
    run.add_argument("--output", type=Path, required=True)
    return parser


async def run(args: argparse.Namespace) -> int:
    if args.command in {"generate", "run"}:
        load_env_file(args.env_file)
        settings = load_model_settings(args.config)
        generation_output = (
            args.output / "generation" if args.command == "run" else args.output
        )
        report = await generate_policy(
            dataset_root=args.dataset,
            settings=settings,
            cedar_cli=args.cedar_cli,
            output=generation_output,
            max_rounds=args.max_rounds,
        )
        summary = {
            "success": report.success,
            "stop_reason": report.stop_reason,
            "rounds": len(report.rounds),
            "hard_pass": report.final_round.hard.passed,
            "soft_pass": report.final_round.soft_pass,
            "metrics": report.aggregate_metrics(),
            "output": str(generation_output),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        if not report.final_round.hard.passed:
            return 2
        if args.command == "generate":
            return 0 if report.success else 1
        policy_path = generation_output / "generated.cedar"
    else:
        policy_path = args.policy

    replay_output = args.output / "replay" if args.command == "run" else args.output
    replay = await replay_policy(
        dataset_root=args.dataset,
        experiment_root=args.experiment_data,
        policy_path=policy_path,
        output=replay_output,
    )
    compact = {
        "groups": [
            {
                "dataset": group["dataset"],
                "condition": group["condition"],
                "all": group["all_trajectories"],
                "with_post": group["trajectories_with_post"],
            }
            for group in replay["groups"]
        ],
        "output": str(replay_output),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
