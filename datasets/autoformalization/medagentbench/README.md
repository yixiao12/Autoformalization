# MedAgentBench Autoformalization Dataset

Generated from `/home/yandu/code/v2/agent-symbolic-guardrails` by `scripts/medagentbench/prepare_dataset.py`.

- `policy.md`: the paper experiment's natural-language policy.
- `tools.json`: Raw HTTP plus eight typed FHIR MCP tools. Nested FHIR records are
  intentionally summarized because trusted runtime normalization exposes the
  policy-relevant fields in `context.medical`.
- `requirements.json`: policy rules and enforceability metadata from
  `policy_analysis/MedAgentBench/spec.json` (Additional Hazard entries excluded).
- `cases.json`: independent rule-level development cases. The six held-out
  `eval_results_*.json` trajectory files are not copied into this dataset and are
  never included in Generator/Judge/Verifier prompts.

Replay uses the source repository's `experiments/data/MedAgentBench` directory.
