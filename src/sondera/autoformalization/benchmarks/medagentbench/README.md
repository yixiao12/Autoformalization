# MedAgentBench Autoformalization Replay

This package keeps the benchmark-specific integration outside the generic
Autoformalization workflow and Agent runtime.

## Modules

- `schema.py`: adds trusted medical/session records to the generated Cedar schema.
- `adapter.py`: converts saved OpenAI tool-call messages into Cedar replay events.
- `context.py`: deterministically normalizes FHIR calls and prior-event state.
- `behavior.py`: evaluates independent rule-level development cases.
- `replay.py`: replays held-out trajectories and calculates both block rates.
- `experiment.py`: stable service functions for CLI or plugin use.
- `cli.py`: thin command-line wrapper.

`generate_policy()` and `replay_policy()` are the intended integration boundary
for a future OpenCode plugin. They do not invoke the medical Agent or FHIR server.

## Reproduce

Prepare policy, tool definitions, requirements, and development cases:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/medagentbench/prepare_dataset.py \
  --source-repo ../agent-symbolic-guardrails \
  --output datasets/autoformalization/medagentbench
```

Generate Cedar and replay all six held-out trajectory groups:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python \
  -m sondera.autoformalization.benchmarks.medagentbench run \
  --dataset datasets/autoformalization/medagentbench \
  --experiment-data ../agent-symbolic-guardrails/experiments/data/MedAgentBench \
  --config autoformalization.toml --env-file .env \
  --cedar-cli "$HOME/.cargo/bin/cedar" --max-rounds 3 \
  --output datasets/autoformalization/medagentbench/results/system-generated
```

A trajectory is blocked when at least one replayed event receives a Cedar
`DENY`. The second metric uses only trajectories containing at least one raw or
typed POST call.
