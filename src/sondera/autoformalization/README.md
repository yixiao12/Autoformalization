# Autoformalization package

This package implements the generator-critic workflow described in
`2606.26649v1.pdf` while keeping model providers replaceable.

## Structure

- `spec.py`: normalized Agent/MCP specification and deterministic Cedar Schema
  generation.
- `prompt.py`: seven-level generator prompt assembly.
- `generator.py`: model, fixture, and repair-test generator backends.
- `cedar_cli.py`: safe adapter for the official Cedar policy CLI.
- `hard.py`: CLI policy/schema parsing and strict schema/type validation, plus
  lineage, vacuity, redundancy, and exact-conflict checks.
- `behavior.py`: deterministic ALLOW/DENY replay and confusion-matrix metrics.
- `soft.py`: Judge and Verifier implementations. Both deterministic experiment
  proxies and LLM implementations are available.
- `workflow.py`: maximum-three-round generator-critic orchestration.
- `dataset.py`: reusable experiment dataset loader.
- `cli.py`: command-line experiment runner and artifact writer.

## Reproducible Stage A run

Install the official Rust CLI and point the workflow at its absolute path:

```bash
cargo install cedar-policy-cli --locked
export CEDAR_CLI="$HOME/.cargo/bin/cedar"
```

The absolute path matters because `cedar-python` provides a different command
also named `cedar`. The hard evaluator probes `language-version` and fails
closed if the configured executable is missing or incompatible.

From the repository root:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m sondera.autoformalization \
  --dataset datasets/autoformalization/code_agent \
  --generator fixture \
  --soft deterministic
```

The fixture backend is explicit and intended only for deterministic integration
testing. It loads the supplied reference Cedar policy, then runs that candidate
through the same prompt construction, hard critic, Judge → Verifier, and Cedar
replay stages as a model-generated candidate.

## Model-backed run

Install the `ai` extra and configure credentials supported by LiteLLM, then run:

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY. Never commit this file.

uv run python -m sondera.autoformalization \
  --dataset datasets/autoformalization/code_agent \
  --config autoformalization.toml \
  --cedar-cli "$CEDAR_CLI" \
  --generator model \
  --soft model
```

The checked-in `autoformalization.toml` configures an OpenAI-compatible custom
endpoint, the Responses wire API, separate generator/review model names,
reasoning effort, response storage, output limits, and timeout. Credentials are
referenced only by environment-variable name. For a direct CLI run without the
TOML file, use `--generator-model`, `--judge-model`, and `--verifier-model`.

Check credentials and Responses API compatibility with a minimal request:

```bash
uv run python -m sondera.autoformalization.check \
  --config autoformalization.toml
```

## Outputs

The default output directory is `<dataset>/results/latest/` and contains:

- `report.json`: every generation round, critic finding, and metric;
- `generated.cedar`: final candidate policy;
- `generated.cedarschema`: schema generated from the MCP tools;
- `generator_prompt.txt`: exact hierarchical prompt used in the final round.
