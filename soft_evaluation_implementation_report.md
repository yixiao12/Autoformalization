# Autoformalization 软评估器实现报告

## 1. 目标与设计原则

软评估器用于判断候选 Cedar 策略是否正确表达自然语言需求。它关注的不是 Cedar
能否解析，而是策略是否存在漏拦、误拦、条件范围错误以及无依据约束等语义问题。

当前实现遵循以下原则：

1. Judge 和 Verifier 不直接输出数值分数，只输出有限枚举值和结构化证据；
2. LLM 提出的反例必须通过程序校验，并使用真实 Cedar 策略重放；
3. 软指标在 Verifier 和反例重放完成后由程序确定性计算；
4. 只有经过 Verifier 接受且被程序确认的问题才能反馈给下一轮策略生成器；
5. 对 Shell、URL、路径等内容先进行确定性语义规范化，Cedar 优先判断结构化事实，
   避免依赖原始字符串的 `like` 匹配。

主要代码：

| 模块 | 代码位置 | 作用 |
|---|---|---|
| 总体工作流 | `src/sondera/autoformalization/workflow.py` | 组织硬评估、回归重放、Judge、Verifier、反例确认和修订 |
| Judge、Verifier、指标 | `src/sondera/autoformalization/soft.py` | 实现 rubric、证据验证、反例校验和软指标计算 |
| 基础用例重放 | `src/sondera/autoformalization/behavior.py` | 使用候选 Cedar 对 ALLOW/DENY 用例进行确定性重放 |
| 数据模型 | `src/sondera/autoformalization/models.py` | 定义 assessment、finding、反例、指标和轮次结果 |
| 语义规范化 | `src/sondera/autoformalization/normalization.py` | 解析 Shell、URL、路径、搜索和写入内容 |
| Schema 扩展 | `src/sondera/autoformalization/spec.py` | 将 `context.normalized` 加入 Cedar Schema |

## 2. 总体流程

```text
自然语言策略 + 原子需求 + 工具定义 + Cedar Schema
                         │
                         ▼
                    候选 Cedar
                         │
                         ▼
                 Cedar 硬评估通过
                         │
                         ▼
              基础回归用例真实重放
                         │
                         ▼
        Judge：逐需求执行 rubric，提出 finding 和反例
                         │
                         ▼
        Verifier：独立执行五项证据检查，接受或拒绝 finding
                         │
                         ▼
       程序检查反例的需求范围、工具、阶段和 JSON Schema
                         │
                         ▼
                 使用候选 Cedar 重放反例
                         │
                         ▼
          程序计算七项软指标与最终 SoftScore
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
          满足条件停机       已确认问题反馈给生成器
```

### 2.1 总体输入

- Agent 系统提示词；
- 完整自然语言策略；
- 原子化 Requirement IR；
- MCP 工具名称、描述及输入输出 JSON Schema；
- Cedar Schema；
- 当前候选 Cedar；
- 基础回归集执行结果；
- 当前轮次及上一轮反馈。

### 2.2 总体输出

- 每条原子需求的 Judge rubric 结果；
- Judge 提出的结构化 finding 和反例；
- Verifier 对每个 finding 的五项验证结果；
- 有效、无效及经 Cedar 重放确认的反例；
- 七项软指标、SoftScore 和是否通过软评估；
- 只包含已验证、已确认问题的下一轮修订反馈。

## 3. Judge 模块

### 3.1 功能

Judge 是第一阶段语义分析器。它将自然语言需求与候选 Cedar 逐条对照，判断策略是否：

- 覆盖了该需求；
- 使用了正确的 `permit` 或 `forbid` 方向；
- 作用于正确的阶段和工具；
- 覆盖所有应当阻止的情况；
- 避免阻止安全行为；
- 没有引入自然语言策略之外的约束。

Judge 使用较高但仍受控的温度 `0.3`，用于发现不同形式的语义缺陷和构造反例。

### 3.2 输入

Judge 接收：

1. Agent 系统提示词；
2. MCP 工具定义；
3. Cedar Schema；
4. `context.normalized` 的字段语义；
5. 完整自然语言策略；
6. 原子 Requirement IR；
7. 当前候选 Cedar；
8. 基础回归集的逐用例 ALLOW/DENY 结果。

### 3.3 Rubric

Judge 首先判断需求在当前运行时中的可执行性：

| 取值 | 含义 |
|---|---|
| `direct` | 当前 Cedar Schema 可以直接表达 |
| `requires_normalization` | 需要确定性预处理产生结构化上下文字段 |
| `unenforceable` | 当前工具事件和 Schema 无法观察所需信息 |
| `ambiguous` | 自然语言需求存在无法可靠消除的歧义 |

随后对每条原子需求的六个维度输出离散判断：

| 维度 | 判断内容 |
|---|---|
| `coverage` | 是否存在带正确 `@source` 的 Cedar 策略 |
| `effect` | `permit/forbid` 是否符合自然语言要求 |
| `trigger_scope` | 阶段和工具范围是否准确 |
| `condition_completeness` | 是否覆盖所有应受约束的条件 |
| `precision` | 是否避免误拦安全请求 |
| `groundedness` | Cedar 中的约束是否都能由原始需求推出 |

每个维度只能输出：

```text
pass | fail | uncertain | not_applicable
```

### 3.4 输出

Judge 输出 `JudgeEvaluation`，包括：

- `assessments`：每条需求的 rubric 判断和理由；
- `findings`：具体语义问题；
- `counterexample_case`：可选的结构化反例。

Finding 类型限制为：

```text
missing_requirement
wrong_effect
under_constraint
over_constraint
hallucination
representation_gap
```

结构化反例示例：

```json
{
  "stage": "PreToolUse",
  "tool": "Bash",
  "expected": "ALLOW",
  "arguments": {
    "command": "grep reboot ./notes.txt"
  },
  "output": null
}
```

Judge 不输出 SoftScore，也不直接决定系统是否收敛。

## 4. Verifier 模块

### 4.1 功能

Verifier 是独立的第二阶段 LLM 审查器，用于防止 Judge 将误解、猜测或无效反例直接
反馈给策略生成器。Verifier 不允许创造新的 finding，只能验证 Judge 已提出的问题。

Verifier 使用较低温度 `0.1`，强调判断稳定性和证据一致性。

### 4.2 输入

Verifier 接收：

1. 与 Judge 相同的系统提示词、工具定义和 Cedar Schema；
2. 自然语言策略和原子需求；
3. `context.normalized` 字段语义；
4. 当前候选 Cedar；
5. 基础回归重放结果；
6. Judge 生成的结构化 findings 和反例。

### 4.3 五项验证

| 检查项 | 判断内容 |
|---|---|
| `source_entailment` | 自然语言规则是否确实支持 Judge 的结论 |
| `schema_compatibility` | 引用的阶段、工具和字段是否存在 |
| `observability` | Cedar 运行时是否能观察判断所需的全部信息 |
| `evidence_correctness` | Judge 引用的 Cedar 条件是否支持其诊断 |
| `replayability` | 反例是否完整、可执行且预期标签合理 |

每项只能输出：

```text
pass | fail | uncertain
```

### 4.4 输出与接受条件

Verifier 对每个 finding 输出：

- `verdict`：`accept`、`reject` 或 `uncertain`；
- 五项验证结果；
- 判断理由和严重级别。

只有五项检查全部为 `pass` 时，`accept` 才有效。如果 LLM 返回 `accept`，但任一检查
不是 `pass`，程序会将其自动降级为 `uncertain`。

Verifier 的接受仍不代表 finding 最终成立。后续程序还会检查：

1. finding 是否对应已知原子需求；
2. stage 和 tool 是否位于该需求的作用范围；
3. 参数或输出是否符合工具 JSON Schema；
4. `expected` 是否为合法的 `ALLOW` 或 `DENY`；
5. 当前 Cedar 对该反例的真实决策是否与期望相反。

只有最后一项成立时，行为类 finding 才被标记为“经 Cedar 重放确认”。

## 5. 软指标计算

### 5.1 计算位置

软指标不由 Judge 或 Verifier 生成。执行顺序为：

```text
Judge → Verifier → 反例程序校验 → Cedar 反例重放
      → calculate_soft_metrics()
```

计算函数位于：

```text
src/sondera/autoformalization/soft.py::calculate_soft_metrics
```

### 5.2 输入

- 原子需求及其 `source`；
- 候选 Cedar 及其 `@source` 标注；
- 基础回归用例的 Cedar 重放结果；
- 通过 Verifier 和 Schema 校验的反例重放结果；
- Judge findings；
- Verifier 的接受结果。

定义：

- TP：期望 DENY，Cedar 实际 DENY；
- TN：期望 ALLOW，Cedar 实际 ALLOW；
- FP：期望 ALLOW，Cedar 实际 DENY；
- FN：期望 DENY，Cedar 实际 ALLOW。

### 5.3 七项核心指标

| 指标 | 计算方式 |
|---|---|
| Requirement Coverage | 具有合法 `@source` 策略的需求数 / 需求总数 |
| Semantic Faithfulness | 重放决策正确的用例数 / 全部重放用例数 |
| Condition Scope Correctness | `(DENY Recall + ALLOW Specificity) / 2` |
| Under-constraint Rate | 至少出现一次 FN 的需求数 / 需求总数 |
| Over-constraint Rate | 至少出现一次 FP 的需求数 / 需求总数 |
| Hallucination Rate | 来源无法对应输入需求的策略数 / 非基础设施策略数 |
| Judge–Verifier Agreement | Verifier 接受数 / Judge finding 数 |

其中：

```text
DENY Recall      = TP / (TP + FN)
ALLOW Specificity = TN / (TN + FP)
```

### 5.4 SoftScore

```text
SoftScore =
0.30 × RequirementCoverage
+ 0.25 × SemanticFaithfulness
+ 0.20 × ConditionScopeCorrectness
+ 0.10 × (1 - UnderConstraintRate)
+ 0.10 × (1 - OverConstraintRate)
+ 0.05 × (1 - HallucinationRate)
```

`Judge–Verifier Agreement` 是诊断指标，不参与 SoftScore，避免 Judge 提出 finding 数量的
随机变化直接改变策略得分。

### 5.5 输出与停机

软评估输出 `SoftMetrics`、SoftScore 和 `soft_pass`。系统成功停机要求：

```text
硬评估通过
且基础回归集全部通过
且 SoftScore ≥ 0.85
且 critical Requirement 的来源覆盖率为 100%
且不存在经 Cedar 重放确认的 critical finding
```

未确认的 LLM 判断不会阻止系统收敛，也不会反馈给下一轮生成器。

## 6. 问题一：Judge 直接给分不稳定

### 6.1 问题

早期实现让 Judge 直接输出诸如 `0.75`、`0.80` 的语义分数。这种方式存在以下问题：

- 同一策略在重复运行时可能得到不同分数；
- 不同指标的评分边界不明确；
- 分数缺少可重放证据，难以解释和复核；
- Judge 既发现问题又决定最终得分，缺少独立验证；
- 一个错误的 LLM 判断可能直接影响停机或下一轮策略。

### 6.2 解决方法

第一，引入逐原子需求的 rubric，将开放式数值评分改为有限分类：

```text
pass | fail | uncertain | not_applicable
```

第二，Judge 只负责：

- 逐需求进行分类评估；
- 提供自然语言与 Cedar 证据；
- 输出结构化 finding；
- 构造最小反例。

第三，引入独立 Verifier，用五项证据检查过滤 Judge finding。

第四，将 SoftScore 计算移动到 Verifier、反例校验和 Cedar 重放之后，由程序根据
`@source`、TP、TN、FP、FN 等确定性数据计算。

第五，只有经过 Verifier 接受并被 Cedar 重放确认的 finding 才进入下一轮修订反馈。

这一改动不能完全消除 LLM 在发现语义问题时的随机性，但可以确保随机性不会直接变成
数值分数或未经验证的策略修改。

## 7. 问题二：过度依赖 `like` 无法理解真实语义

### 7.1 问题

早期 Cedar 策略大量使用：

```cedar
context.arguments like "*reboot*"
```

字符串包含关系不能表达 Shell、URL 和路径的真实结构。例如：

- `reboot` 是实际执行的命令，`grep reboot notes.txt` 只是搜索文本；
- `bash -c "reboot"` 隐藏了嵌套执行；
- `curl URL | sh` 的风险来自管道结构，而不是单一关键词；
- `sudo -u user command` 与直接执行命令的权限语义不同；
- `safe-example.com` 不能仅通过字符串后缀判断为 `example.com`；
- `/tmp/not-secrets.txt` 和 `/project/secrets/key` 的路径组件含义不同。

这会同时产生：

- 误拦：安全字符串包含危险关键词；
- 漏拦：通过引号、包装命令、管道或路径变体绕过匹配；
- 不可解释：Cedar 条件只能说明“字符串相似”，不能说明危险语义。

### 7.2 解决方法

在 Cedar 决策之前增加可信的确定性规范化层：

```text
原始工具参数 → 解析与规范化 → context.normalized → Cedar
```

`SecurityContextNormalizer` 使用 Python 程序提取结构化事实：

#### Shell

- 使用 `shlex` 进行 tokenization；
- 识别 `|`、`;`、`&&`、`||` 等命令结构；
- 识别 `sudo`、`env`、`command`、`nohup` 等包装命令；
- 递归分析 `sh -c`、`bash -c` 等嵌套 Shell；
- 提取实际执行程序集合；
- 判断删除根目录、格式化磁盘、写块设备、关机、提权和下载后交给 Shell。

对应字段例如：

```text
shell_parse_ok
shell_executables
shell_deletes_root_or_home
shell_formats_device
shell_writes_block_device
shell_invokes_shutdown
shell_uses_privilege_escalation
shell_downloads_to_shell
```

#### URL、路径和内容

- URL 使用标准解析器获得 scheme、IDNA host 和 host 后缀集合；
- 路径统一分隔符、大小写、basename、suffix 和路径组件；
- 搜索条件提取私钥、密钥赋值及凭据搜寻意图；
- 写入内容识别私钥头和敏感变量赋值。

生成器、Judge 和 Verifier 都接收这些字段的语义说明，并被要求优先使用
`context.normalized`，原始字符串只保留作审计或处理尚未结构化的规则。

改进后的 Cedar 可以写成：

```cedar
forbid (
    principal,
    action,
    resource
)
when {
    context has normalized &&
    context.normalized.shell_parse_ok &&
    context.normalized.shell_invokes_shutdown
};
```

这使策略判断从“字符串中出现 reboot”变成“解析后确认调用了关机类可执行程序”。

### 7.3 当前边界

当前 Shell 解析器是面向策略事实提取的轻量解析器，不是完整 POSIX Shell 解释器。
复杂的命令替换、重定向、平台特有 Shell 语法仍可能需要专用 AST 解析器或沙箱分析。
因此系统同时提供 `parse_ok` 和 `shell_parse_ok`，让 Cedar 对解析失败场景采取明确策略，
而不是假设解析成功。

## 8. 总结

改进后的软评估器将 LLM 的职责限制为语义分析、证据说明和反例构造，将可验证性和数值
计算交给程序。Judge 提出问题，Verifier 独立审查，程序校验并重放反例，最后依据真实
Cedar 决策计算软指标。

同时，系统通过 `context.normalized` 将 Shell、URL、路径等原始字符串转换为结构化
事实，减少脆弱的 `like` 匹配。最终形成了“LLM 负责理解和发现、Verifier 负责复核、
程序负责验证和计分、Cedar 负责真实决策”的软评估工作流。
