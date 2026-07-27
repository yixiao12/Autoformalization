# 改进后的软评估器

核心代码：

- `src/sondera/autoformalization/soft.py`：Judge、Verifier、反例校验和指标计算；
- `src/sondera/autoformalization/workflow.py`：反例重放和修复循环；
- `src/sondera/autoformalization/models.py`：rubric、反例和评估结果模型。
- `src/sondera/autoformalization/normalization.py`：确定性安全语义规范化。

## 0. Cedar 前置规范化

为了避免策略依赖 `like "*reboot*"` 等脆弱字符串匹配，PreToolUse 请求在进入 Cedar 前先由确定性代码生成 `context.normalized`：

```text
原始 MCP 参数 → Shell/URL/路径/搜索解析 → context.normalized → Cedar
```

主要字段包括：

- Shell：实际可执行程序、危险删除、磁盘格式化、块设备重定向、关机、提权、下载后交给 Shell；
- URL：小写 IDNA host、host 后缀集合、HTTPS 状态；
- 路径：规范化路径、basename、suffix、路径组件和敏感文件事实；
- 搜索与写入内容：私钥头、密钥赋值和凭据搜寻意图。

生成器、Judge 和 Verifier 都会收到这些字段的语义说明。原始参数仍然保留用于审计和无法规范化的规则，但策略应优先使用结构化字段。解析失败通过 `parse_ok` 或 `shell_parse_ok` 暴露，不能由模型在运行时猜测。

## 1. 总体流程

```text
自然语言规则 + 工具定义 + 扩展 Cedar Schema + 候选 Cedar + 基础用例重放
                              ↓
                Judge：逐原子规则执行分类 rubric
                              ↓
                    结构化 finding + 反例
                              ↓
             Verifier：执行五项证据检查并接受/拒绝
                              ↓
              程序校验反例字段、工具范围和 JSON Schema
                              ↓
                       Cedar 真实重放
                              ↓
                程序计算软指标和确认修复反馈
```

模型不再直接生成任何软指标分数。

## 2. Judge rubric

Judge 对每条原子 Requirement 分别判断：

| 维度 | 含义 | 可选值 |
|---|---|---|
| Enforceability | 当前 Schema 是否可直接表达 | `direct / requires_normalization / unenforceable / ambiguous` |
| Coverage | 是否有带正确来源标注的策略 | `pass / fail / uncertain / not_applicable` |
| Effect | permit/forbid 是否正确 | 同上 |
| Trigger Scope | stage 和 tool 范围是否正确 | 同上 |
| Condition Completeness | 条件是否覆盖应约束情况 | 同上 |
| Precision | 是否避免误拦安全请求 | 同上 |
| Groundedness | 约束是否来自输入规则 | 同上 |

Judge 只输出分类判断、证据和结构化反例。反例包含：

```json
{
  "stage": "PreToolUse",
  "tool": "Bash",
  "expected": "ALLOW",
  "arguments": {"command": "grep reboot ./notes.txt"},
  "output": null
}
```

## 3. Verifier

Verifier 对每个 finding 独立检查：

1. `source_entailment`：结论是否由自然语言规则支持；
2. `schema_compatibility`：stage、tool、字段是否存在；
3. `observability`：Cedar 是否能观察所需信息；
4. `evidence_correctness`：引用的 Cedar 证据是否正确；
5. `replayability`：反例是否完整且预期标签正确。

每项只能是 `pass / fail / uncertain`。只有五项均为 `pass` 的 finding 才能保持 `accept`，否则程序将其降为 `uncertain`。

## 4. 反例确认

Verifier 接受不等于 finding 成立。程序还会：

1. 检查 Requirement、stage 和 tool 的对应关系；
2. 按 MCP 工具输入或输出 JSON Schema 校验数据；
3. 转换为 `EvaluationCase`；
4. 使用当前 Cedar 策略真实重放；
5. 只有实际结果与自然语言要求的 `expected` 不一致时，才确认该 finding。

只有确认后的 finding 会进入下一轮策略生成 Prompt。现有 40 条人工用例继续作为每轮固定的基础回归集；当前版本暂不维护跨轮动态历史反例池。

## 5. 七项核心指标

指标名称和权重不变，但全部由程序计算：

| 指标 | 计算证据 |
|---|---|
| Requirement Coverage | Cedar `@source` 标注覆盖的 Requirement 数 / 总数 |
| Semantic Faithfulness | 基础用例与有效反例中，Cedar 决策正确数 / 总数 |
| Condition Scope Correctness | `(DENY Recall + ALLOW Specificity) / 2` |
| Under-constraint Rate | 出现 `DENY → ALLOW` 的 Requirement 数 / 总数 |
| Over-constraint Rate | 出现 `ALLOW → DENY` 的 Requirement 数 / 总数 |
| Hallucination Rate | 来源未知的非基础设施策略数 / 非基础设施策略数 |
| Judge–Verifier Agreement | Verifier 接受 finding 数 / Judge finding 数 |

```text
SoftScore =
0.30 × Coverage
+ 0.25 × Faithfulness
+ 0.20 × ScopeCorrectness
+ 0.10 × (1 - UnderConstraintRate)
+ 0.10 × (1 - OverConstraintRate)
+ 0.05 × (1 - HallucinationRate)
```

另报告反例接受数、Schema 有效数、Cedar 确认数、反例有效率和 finding 确认率，这些辅助指标不参与 SoftScore。

## 6. 停机与温度

当前成功停机条件：

```text
硬评估通过
∧ 40 条基础回归全部通过
∧ SoftScore ≥ 0.85
∧ critical Requirement 映射覆盖率 = 100%
∧ 不存在经 Cedar 重放确认的 critical finding
```

没有把未确认的 LLM 判断作为阻断条件。模型配置为 Judge `temperature=0.3`、Verifier `temperature=0.1`。

## 7. Judge 评分标准与指标计算细则

### 7.1 Judge 评分标准

Judge 不直接输出数值分数，而是对每条原子 Requirement 进行分类评价。

首先判断规则的可执行性：

| 取值 | 含义 |
|---|---|
| `direct` | Cedar 可直接表达 |
| `requires_normalization` | 需要使用预处理后的 `context.normalized` 字段 |
| `unenforceable` | 当前 Schema 和上下文无法表达 |
| `ambiguous` | 自然语言规则含义不明确 |

随后对六个维度输出 `pass / fail / uncertain / not_applicable`：

| 维度 | 判断内容 |
|---|---|
| `coverage` | 是否有来源可追溯的 Cedar 策略覆盖该规则 |
| `effect` | `permit/forbid` 与原始规则的 ALLOW/DENY 方向是否一致 |
| `trigger_scope` | 触发阶段和工具范围是否准确 |
| `condition_completeness` | 是否覆盖规则要求的所有禁止或必需情况 |
| `precision` | 是否避免误拦安全行为 |
| `groundedness` | 所有约束是否都能由输入规则推导出来 |

Judge 只在发现具体失败或不确定性时生成 finding。finding 类型包括 `missing_requirement`、`wrong_effect`、`under_constraint`、`over_constraint`、`hallucination` 和 `representation_gap`。对可重放的行为问题，Judge 还必须输出结构化反例，包含 stage、tool、arguments/output 和自然语言要求的预期 ALLOW/DENY。

Verifier 对每个 finding 检查 `source_entailment`、`schema_compatibility`、`observability`、`evidence_correctness` 和 `replayability`。五项全部为 `pass` 时 finding 才能被接受；接受后还需要通过 JSON Schema 校验和 Cedar 重放确认。

### 7.2 精确指标公式

将基础用例和通过校验的反例合并为重放结果集，定义：

- TP：期望 DENY，Cedar 实际 DENY；
- TN：期望 ALLOW，Cedar 实际 ALLOW；
- FP：期望 ALLOW，Cedar 实际 DENY；
- FN：期望 DENY，Cedar 实际 ALLOW。

| 指标 | 精确计算方式 |
|---|---|
| Requirement Coverage | 具有合法 `@source` 策略的 Requirement 数 / Requirement 总数 |
| Semantic Faithfulness | 决策正确的重放用例数 / 全部重放用例数 |
| Condition Scope Correctness | `(TP / (TP + FN) + TN / (TN + FP)) / 2` |
| Under-constraint Rate | 至少出现一次 FN 的 Requirement 数 / Requirement 总数 |
| Over-constraint Rate | 至少出现一次 FP 的 Requirement 数 / Requirement 总数 |
| Hallucination Rate | `@source` 无法对应输入规则的策略数 / 非基础设施策略数 |
| Judge–Verifier Agreement | Verifier 接受的 finding 数 / Judge 生成的 finding 数 |

```text
SoftScore =
0.30 × RequirementCoverage
+ 0.25 × SemanticFaithfulness
+ 0.20 × ConditionScopeCorrectness
+ 0.10 × (1 - UnderConstraintRate)
+ 0.10 × (1 - OverConstraintRate)
+ 0.05 × (1 - HallucinationRate)
```

`Judge–Verifier Agreement` 目前是诊断指标，不参与 SoftScore。因此，如果 Judge 提出问题但全部被 Verifier 拒绝，一致率可能为 0，但被拒绝的反例不会进入 Cedar 重放，也不会降低 SoftScore。
