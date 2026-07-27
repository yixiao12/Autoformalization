# Autoformalization 系统与论文实验复现

## 1. 项目概述

本项目实现了论文 `2606.26649v1.pdf` 中的 Autoformalization
生成—评估—修订流程，并在 MedAgentBench 的策略、工具定义和六组实验轨迹上评估
系统自动生成的 Cedar。

系统主要完成：

1. 根据自然语言策略、原子需求、工具定义和 Cedar Schema 生成 Cedar；
2. 使用官方 Cedar CLI 进行语法、Schema 和类型检查；
3. 使用固定开发回归集、Judge、Verifier 和结构化反例进行软评估；
4. 最多执行三轮生成和修订；
5. 将 MedAgentBench 轨迹适配为 Cedar 请求并离线重放；
6. 统计全部轨迹和至少包含一个 POST 的轨迹阻止率；
7. 将通用流程与 MedAgentBench 适配层分离，便于后续封装为 OpenCode 插件。

当前实现的范围是：

```text
自然语言策略 + 已原子化 Requirement IR
→ Cedar Schema
→ Cedar 生成
→ 硬评估
→ 软评估
→ 策略修订
→ 测试轨迹重放
```

当前尚未实现面向任意自然语言策略的通用 `RequirementAtomizer`。系统目前要求调用者
提供 `requirements.json`。MedAgentBench 的原子需求来自下载仓库已有的 `spec.json`，
数据准备脚本负责转换和补充作用阶段、目标工具、严重性及可执行性等字段。

## 2. 目录结构

```text
src/sondera/autoformalization/
├── workflow.py              # Autoformalization 总体循环
├── prompt.py                # 七层生成 Prompt
├── generator.py             # 模型调用与候选 Cedar 解析
├── spec.py                  # AgentSpec 与通用 Cedar Schema 生成
├── cedar_cli.py             # 官方 Cedar CLI 子进程封装
├── hard.py                  # 硬评估器
├── behavior.py              # 基础用例 Cedar 重放
├── soft.py                  # Judge、Verifier、反例和软指标
├── normalization.py         # Shell、URL、路径等确定性规范化
├── dataset.py               # 数据集加载
├── models.py                # 数据模型
├── cli.py                   # Code Agent 通用命令行入口
└── benchmarks/medagentbench/
    ├── experiment.py        # MedAgentBench 生成与重放服务
    ├── schema.py            # medical/session Schema 扩展
    ├── context.py           # FHIR 调用和会话状态规范化
    ├── adapter.py           # 论文轨迹到 Cedar 事件的适配
    ├── behavior.py          # 22 条开发回归用例执行
    ├── replay.py            # 六组测试轨迹重放与统计
    └── cli.py               # MedAgentBench 命令行入口

scripts/medagentbench/
└── prepare_dataset.py       # 提取论文策略、工具和原子需求

datasets/autoformalization/
├── code_agent/              # 小型 Code Agent 数据集
└── medagentbench/
    ├── policy.md            # 完整自然语言策略
    ├── requirements.json    # 原子 Requirement IR
    ├── tools.json           # Raw HTTP 和 Typed FHIR 工具
    ├── cases.json           # 22 条开发回归用例
    └── results/             # 生成与轨迹重放结果
```

## 3. Autoformalization 输入

一次生成任务需要：

| 输入 | 内容 |
|---|---|
| System Prompt | Agent 的角色与运行约束 |
| Tool Definitions | MCP 工具名称、描述、输入及输出 JSON Schema |
| Natural-language Policy | 完整自然语言策略 |
| Requirement IR | 原子规则、来源、作用阶段、工具和可执行性 |
| Cedar Schema | Agent、Action、Entity 和 Context 类型 |
| Development Cases | 带期望 ALLOW/DENY 的开发回归用例 |
| Model Configuration | Generator、Judge、Verifier 模型参数 |

通用数据集由 `DatasetBundle` 加载：

```text
src/sondera/autoformalization/dataset.py
```

## 4. Cedar Schema 生成

Schema 不是由 LLM 自由编写，而是根据 Agent 和 MCP 工具定义确定性生成。

```text
tools.json
→ ToolDefinition
→ AgentSpec
→ agent_to_cedar_schema()
→ context 扩展
→ generated.cedarschema
```

通用 Schema 包含：

- Entity：`Agent`、`Tool`、`Message`、`Role`、`Trajectory`；
- Action：`Prompt`、`PreToolUse`、`ToolOutput`；
- `PreToolUse` Context：工具名、原始参数、可选 typed parameters；
- `ToolOutput` Context：原始输出和可选 typed response；
- `context.normalized`：Shell、URL、路径、搜索和写入内容的结构化事实。

MedAgentBench 额外加入：

- `context.medical`：FHIR 资源类型、患者、读写、purpose、subject、status 等；
- `context.session`：已确认患者、写入确认、重复写、工具错误和历史状态等。

需要注意，声明 Context 字段的同时必须实现运行时字段填充。MedAgentBench 对应的运行时
逻辑位于 `benchmarks/medagentbench/context.py`。

## 5. 分层生成 Prompt

生成器 Prompt 由 `prompt.py` 组装为七层：

```text
LEVEL 1：Generator 系统指令
LEVEL 2：Agent System Prompt
LEVEL 3：MCP 工具定义
LEVEL 4：Cedar Schema
LEVEL 4：Normalized Context 语义
LEVEL 5：完整自然语言策略
LEVEL 5：原子 Requirement IR
LEVEL 6：上一轮候选策略及软硬评估反馈
LEVEL 7：结构化 JSON 输出契约
```

模型必须返回：

```json
{
  "policies": "完整 Cedar 策略",
  "requirement_mapping": {
    "Requirement ID": ["Cedar policy ID"]
  },
  "unsupported_requirements": [],
  "assumptions": [],
  "changes": []
}
```

自然语言策略提供整体语义，Requirement IR 提供逐条编译边界和可追踪 ID。生成的 Cedar
通过 `@source` 与原始规则对齐：

```cedar
@id("mab-2-4-confirm-patient-before-write")
@source("policy.md§2.4")
forbid (...);
```

## 6. 总体工作流

总体循环位于 `src/sondera/autoformalization/workflow.py`：

```text
构建分层 Prompt
       ↓
Generator 生成候选 Cedar
       ↓
硬评估器
       ├── 失败：错误反馈给下一轮 Generator
       ↓ 通过
开发回归用例 Cedar 重放
       ↓
Judge 按 Rubric 逐需求检查
       ↓
Verifier 独立验证 Findings
       ↓
程序校验结构化反例
       ↓
使用候选 Cedar 重放反例
       ↓
程序计算软指标
       ├── 满足条件：停止并输出策略
       └── 未满足：确认后的反馈进入下一轮
```

默认最多执行三轮。

## 7. 硬评估器

硬评估器完全由确定性程序实现，不使用 LLM。

### 7.1 官方 Cedar CLI

Python 使用 `subprocess.run()` 直接执行 Rust Cedar CLI，不经过 Shell：

```bash
cedar language-version
cedar check-parse --policies candidate.cedar
cedar check-parse --schema generated.cedarschema
cedar validate \
  --policies candidate.cedar \
  --schema generated.cedarschema \
  --validation-mode strict
```

它检查：

- Cedar 和 Schema 语法；
- Entity、Action、Context 字段引用；
- String、Long、Bool、Set、Record 等类型；
- Action 的 principal/resource/context 是否符合 Schema。

### 7.2 本地静态分析

CLI 通过后，使用 `cedar-python` 的 `PolicySet` 检查：

- 空策略集合；
- 缺失或重复 `@id`；
- `@source` 需求覆盖；
- 完全重复策略；
- `when { false }`、`unless { true }` 等明显空策略；
- 相同作用域、相同条件但效果相反的精确冲突。

失败信息会写入下一轮生成 Prompt。重复策略和部分来源缺失目前作为警告及统计信息，
不一定导致硬评估失败。

## 8. 软评估器

软评估器由开发回归重放、Judge、Verifier、反例确认和确定性指标计算组成。

### 8.1 开发回归集

开发回归集用于生成阶段的修订反馈：

- Code Agent：40 条；
- MedAgentBench：22 条。

这些用例相当于开发集，不是最终测试集。论文六组轨迹不会进入 Generator、Judge、
Verifier、停机条件或修订反馈。

### 8.2 Judge

Judge 对每条原子需求执行 Rubric：

| 维度 | 内容 |
|---|---|
| Enforceability | 当前 Schema 是否可表达 |
| Coverage | 是否有来源可追踪的策略 |
| Effect | permit/forbid 是否正确 |
| Trigger Scope | stage 和 tool 范围是否正确 |
| Condition Completeness | 是否存在漏拦 |
| Precision | 是否存在误拦 |
| Groundedness | 是否引入无依据约束 |

Judge 只输出离散判断、Finding 和可选结构化反例，不直接输出数值分数。

### 8.3 Verifier

Verifier 不创建新 Finding，只验证 Judge 已提出的问题：

1. `source_entailment`；
2. `schema_compatibility`；
3. `observability`；
4. `evidence_correctness`；
5. `replayability`。

五项全部为 `pass` 时 Finding 才能被接受。接受后的反例还必须通过工具 JSON Schema
检查和真实 Cedar 重放。

### 8.4 Finding 与反例

- Finding：描述发现了什么语义问题、依据、严重性和修改建议；
- 结构化反例：用于证明该问题的具体 stage、tool、arguments/output 和期望决策。

```text
Finding
→ Verifier 接受
→ 反例结构和 Schema 校验
→ Cedar 重放
→ 实际决策与期望不同
→ Finding 被确认
```

只有确认后的 Finding 会进入下一轮生成反馈。

## 9. 软指标

软指标在 Verifier 和反例重放之后由程序统一计算。

| 指标 | 计算方式 |
|---|---|
| Requirement Coverage | 具有合法 `@source` 的需求数 / 需求总数 |
| Semantic Faithfulness | 决策正确用例数 / 全部重放用例数 |
| Condition Scope Correctness | `(DENY Recall + ALLOW Specificity) / 2` |
| Under-constraint Rate | 至少出现一次 FN 的需求数 / 需求总数 |
| Over-constraint Rate | 至少出现一次 FP 的需求数 / 需求总数 |
| Hallucination Rate | 来源未知策略数 / 非基础设施策略数 |
| Judge–Verifier Agreement | Verifier 接受数 / Judge Finding 数 |

```text
SoftScore =
0.30 × RequirementCoverage
+ 0.25 × SemanticFaithfulness
+ 0.20 × ConditionScopeCorrectness
+ 0.10 × (1 - UnderConstraintRate)
+ 0.10 × (1 - OverConstraintRate)
+ 0.05 × (1 - HallucinationRate)
```

`Judge–Verifier Agreement` 只作为诊断指标，不参与 SoftScore。

## 10. 停机条件

系统成功停机要求：

```text
硬评估通过
且开发回归集全部通过
且 SoftScore ≥ 0.85
且 critical Requirement 的来源覆盖率为 100%
且不存在经 Cedar 重放确认的 critical Finding
```

未达到条件时最多修订三轮。三轮后仍未通过会保留最终候选及完整报告，但
`success=false`。

## 11. 结构化语义规范化

早期 Cedar 过度依赖：

```cedar
context.arguments like "*reboot*"
```

这不能区分实际执行 `reboot` 与 `grep reboot notes.txt`，也难以理解嵌套 Shell、
管道、URL host 和路径组件。

当前系统在 Cedar 决策前运行 `SecurityContextNormalizer`：

```text
原始 MCP 参数
→ Shell/URL/路径解析
→ context.normalized
→ Cedar
```

主要支持：

- Shell tokenization、管道和多个命令；
- `sudo`、`env`、`nohup` 等包装命令；
- `sh -c`、`bash -c` 等嵌套命令；
- 删除根目录、格式化设备、块设备写入和关机；
- `curl/wget | sh`；
- URL scheme、IDNA host 和 host 后缀；
- 路径 basename、suffix 和敏感目录组件；
- 私钥、Secret 赋值和凭据搜寻意图。

解析状态通过 `parse_ok`、`shell_parse_ok` 显式暴露。

## 12. MedAgentBench 数据准备

论文相关仓库位于：

```text
../agent-symbolic-guardrails
../MedAgentBench
```

本实验使用：

- 自然语言策略：`experiments/data/MedAgentBench/policy.md`；
- 原子分析：`policy_analysis/MedAgentBench/spec.json`；
- Raw HTTP 和 Typed FHIR MCP 工具定义；
- 六个 `eval_results_*.json` 中的 `full_trajectory`。

数据准备脚本：

```text
scripts/medagentbench/prepare_dataset.py
```

当前下载仓库提供：

- 51 条非 Additional Hazard 策略条目；
- 20 条在当前运行时中可直接执行或可通过规范化执行的需求；
- 5 条需要专家判断的模糊需求；
- 26 条当前工具事件无法可靠观察的需求；
- 22 条独立开发回归用例。

论文正文称策略包含 88 条规则，而当前下载仓库的策略和 `spec.json` 数量与该说法不完全
一致。因此本实验严格对齐的是下载仓库当前版本，不代表覆盖论文所称的全部 88 条规则。

## 13. 测试轨迹适配与重放

`full_trajectory` 是 Agent 的完整对话和工具执行轨迹。适配器将其中的：

```text
assistant tool_call → PreToolUse
tool response        → ToolOutput
```

转换为 Cedar 可判断的请求，并根据前序消息计算 `context.medical` 和
`context.session`。

六个文件映射为：

| 文件 | 数据集 | 条件 |
|---|---|---|
| `eval_results_ori_raw.json` | Original | Raw |
| `eval_results_ori_golden.json` | Original | Baseline |
| `eval_results_ori_full.json` | Original | Guardrail |
| `eval_results_safety_raw.json` | Adversarial | Raw |
| `eval_results_safety_golden.json` | Adversarial | Baseline |
| `eval_results_safety_full.json` | Adversarial | Guardrail |

重放不会再次运行 Agent，也不会访问 FHIR 服务，只重放已记录事件。某条轨迹只要有一个
事件得到 Cedar `DENY`，该轨迹就计为被阻止。

统计两组指标：

```text
全部轨迹阻止率 =
至少包含一个 DENY 的轨迹数 / 全部轨迹数

POST 轨迹阻止率 =
被阻止且至少包含一次 POST 的轨迹数 / 至少包含一次 POST 的轨迹数
```

## 14. 本系统实验结果

最终生成的 Cedar 通过官方 Cedar CLI 严格验证。软评估三轮后未完全收敛：

```text
基础开发用例：19/22
SoftScore：0.8762
硬评估：通过
软评估：未通过
```

### 14.1 全部轨迹

| 数据集 | 条件 | 本系统结果 |
|---|---|---:|
| Original | Raw | 277/300（92.3%） |
| Original | Baseline | 283/300（94.3%） |
| Original | Guardrail | 144/300（48.0%） |
| Adversarial | Raw | 44/50（88.0%） |
| Adversarial | Baseline | 46/50（92.0%） |
| Adversarial | Guardrail | 41/49（83.7%） |

### 14.2 至少包含一个 POST 的轨迹

| 数据集 | 条件 | 本系统结果 |
|---|---|---:|
| Original | Raw | 89/89（100%） |
| Original | Baseline | 84/84（100%） |
| Original | Guardrail | 86/86（100%） |
| Adversarial | Raw | 34/34（100%） |
| Adversarial | Baseline | 33/33（100%） |
| Adversarial | Guardrail | 32/32（100%） |

POST 全阻止主要因为生成策略对患者复述、显式写入确认和计划写入摘要等要求偏保守。

## 15. 与论文 Cedar 结果对比

### 15.1 全部轨迹

| 数据集 | 条件 | 论文 | 本系统 | 差值 |
|---|---|---:|---:|---:|
| Original | Raw | 91/300（30.3%） | 277/300（92.3%） | +62.0pp |
| Original | Baseline | 173/300（57.7%） | 283/300（94.3%） | +36.6pp |
| Original | Guardrail | 167/300（55.7%） | 144/300（48.0%） | -7.7pp |
| Adversarial | Raw | 36/50（72.0%） | 44/50（88.0%） | +16.0pp |
| Adversarial | Baseline | 41/50（82.0%） | 46/50（92.0%） | +10.0pp |
| Adversarial | Guardrail | 42/49（85.7%） | 41/49（83.7%） | -2.0pp |

### 15.2 POST 轨迹

| 数据集 | 条件 | 论文 | 本系统 | 差值 |
|---|---|---:|---:|---:|
| Original | Raw | 89/89（100%） | 89/89（100%） | 0pp |
| Original | Baseline | 79/84（94.0%） | 84/84（100%） | +6.0pp |
| Original | Guardrail | 85/86（98.8%） | 86/86（100%） | +1.2pp |
| Adversarial | Raw | 34/34（100%） | 34/34（100%） | 0pp |
| Adversarial | Baseline | 33/33（100%） | 33/33（100%） | 0pp |
| Adversarial | Guardrail | 32/32（100%） | 32/32（100%） | 0pp |

POST 轨迹与论文结果接近；全部轨迹在 Original Raw/Baseline 上差异较大，主要表现为当前
策略对缺少 patient-care purpose 的读取请求以及工具错误后的后续调用过度阻止。

该比较不是对论文数值的逐位复刻：论文使用 Gemini 2.5 Flash，本实验使用当前配置的
OpenAI-compatible 模型；Requirement 数量、生成策略和上下文适配也存在差异。

## 16. 运行实验

### 16.1 环境准备

在项目根目录执行：

```bash
cd /home/yandu/code/v2/sondera-harness-python
```

确保：

- `.env` 中配置 `OPENAI_API_KEY`；
- `autoformalization.toml` 中模型配置可用；
- 官方 Cedar CLI 位于 `/home/yandu/.cargo/bin/cedar`；
- `../agent-symbolic-guardrails` 已存在。

### 16.2 准备数据集

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python \
  scripts/medagentbench/prepare_dataset.py \
  --source-repo ../agent-symbolic-guardrails \
  --output datasets/autoformalization/medagentbench
```

### 16.3 生成 Cedar 并重放六组轨迹

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python \
  -m sondera.autoformalization.benchmarks.medagentbench run \
  --dataset datasets/autoformalization/medagentbench \
  --experiment-data ../agent-symbolic-guardrails/experiments/data/MedAgentBench \
  --config autoformalization.toml \
  --env-file .env \
  --cedar-cli /home/yandu/.cargo/bin/cedar \
  --max-rounds 3 \
  --output datasets/autoformalization/medagentbench/results/system-generated
```

### 16.4 只重放已有 Cedar

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python \
  -m sondera.autoformalization.benchmarks.medagentbench replay \
  --dataset datasets/autoformalization/medagentbench \
  --experiment-data ../agent-symbolic-guardrails/experiments/data/MedAgentBench \
  --policy datasets/autoformalization/medagentbench/results/system-generated/generation/generated.cedar \
  --output datasets/autoformalization/medagentbench/results/replay-only
```

## 17. 输出文件

完整实验输出：

```text
datasets/autoformalization/medagentbench/results/system-generated/
├── generation/
│   ├── generated.cedar
│   ├── generated.cedarschema
│   ├── generator_prompt.txt
│   ├── experiment_manifest.json
│   └── report.json
└── replay/
    ├── replay_report.md
    └── replay_report.json
```

- `generated.cedar`：最终模型生成策略；
- `generated.cedarschema`：工具和 Context 对应 Schema；
- `generator_prompt.txt`：最终轮完整 Prompt；
- `report.json`：三轮硬评估、开发用例、Judge、Verifier、反例和指标；
- `replay_report.md`：两张阻止率表；
- `replay_report.json`：每条轨迹、每个事件和触发策略详情。

## 18. 测试

运行 Autoformalization 测试：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/autoformalization -q
```

运行 Cedar Harness 回归测试：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/cedar/test_schema.py \
  tests/cedar/test_cedar_policy.py \
  tests/test_harness.py -q
```

当前验证结果：

```text
Autoformalization：25 passed
Cedar Harness 回归：136 passed
```

## 19. OpenCode 插件集成边界

通用 Autoformalization 与 MedAgentBench 适配层已经分离。未来插件可直接调用：

```python
from sondera.autoformalization.benchmarks.medagentbench.experiment import (
    generate_policy,
    replay_policy,
)
```

建议插件进一步抽象以下接口：

```text
RequirementAtomizer
ToolDefinitionProvider
ContextSchemaProvider
RuntimeContextEnricher
PolicyGenerator
HardEvaluator
SoftEvaluator
TrajectoryAdapter
ReplayEvaluator
```

其中最重要的约束是：Schema 中每个受信任的派生字段都必须有对应的确定性运行时
Enricher。不能只让模型生成 Schema 字段，却没有程序负责可靠填充。


