# Code Agent Autoformalization Dataset

This is the Stage A development dataset for the Autoformalization pipeline. It
uses the repository's existing `coding_agent` and expands its policy corpus to
20 atomic, schema-expressible requirements.

## Files

- `system_prompt.txt`: agent system instruction supplied to the generator.
- `tools.json`: normalized MCP-style tool definitions.
- `policy.md`: the natural-language policy corpus.
- `requirements.json`: atomic requirement IR and source mappings.
- `expected.cedarschema`: the expected schema generated from the tools.
- `gold.cedar`: hand-authored reference policies.
- `cases.json`: one violating and one compliant case per requirement.
- `verify.py`: checks dataset consistency and replays all cases.

The three `default-*` permit policies in `gold.cedar` are infrastructure rules
and are not counted among the 20 requirements.

## Intended use

1. Generate a Cedar schema from `tools.json` and compare it with
   `expected.cedarschema`.
2. Generate Cedar policies from the system prompt, tools, schema, and
   `policy.md`.
3. Run the hard and soft evaluators.
4. Compare generated policies with `gold.cedar` by validation and decision
   behavior, not by exact source text.
5. Replay `cases.json` and compute rule-level recall and safe specificity.

Run the reference verification from the repository root:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python \
  datasets/autoformalization/code_agent/verify.py
```

Run the complete generator-critic experiment offline:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m sondera.autoformalization \
  --dataset datasets/autoformalization/code_agent \
  --generator fixture \
  --soft deterministic
```

This writes the generated schema, final policy, exact generator prompt, and all
hard/soft/behavioral metrics to `results/latest/`. The fixture generator is an
explicit reproducibility backend; use `--generator model` and `--soft model`
for a real LLM generation plus Judge → Verifier run.

With the repository model configuration and local `.env` credential:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m sondera.autoformalization \
  --dataset datasets/autoformalization/code_agent \
  --config autoformalization.toml \
  --generator model \
  --soft model
```
