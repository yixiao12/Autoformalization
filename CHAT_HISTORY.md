# Autoformalization 项目聊天记录

> 整理日期：2026-07-16  
> 说明：用户问题按现有上下文尽量保留原文。部分较早的助手回答在界面中已经不可见，以下内容根据当前会话保存的上下文重建，并非逐字转录。

## 1. 项目目标与初步规划

### 用户

阅读当前文件夹下的论文 2606.26649v1，我需要对论文进行复现，我的任务如下：

1. 深入理解和掌握 Autoformalization，构建将自然语言转化为可验证 Cedar 的完整工作流；
2. 设计和实现策略生成工作流评估器，提供合理、准确的量化指标，用于评估模型生成策略的语法正确性、语义一致性和整体质量；
3. 基于已实现的工作流，以 OpenCode 插件的形式封装并提供实用工具能力。

请根据这些，告诉我我应该做什么。

### 助手（根据上下文重建）

建议把项目拆成三层：

1. **Autoformalization 核心**：读取自然语言规则、Agent 系统提示词、工具定义和 Cedar Schema，生成 Cedar 策略。
2. **评估与修复闭环**：硬评估器负责 Cedar 解析、Schema 校验和静态分析；软评估器负责语义覆盖、忠实度、过度约束和约束不足等判断；评估结果反馈给生成器，最多修复三轮。
3. **OpenCode 集成层**：将核心系统包装成插件，自动读取当前 Agent 和 MCP 工具定义，并提供策略生成、校验、评估以及运行时拦截能力。

建议先完成可独立运行的核心系统和实验，再做插件封装。

---

## 2. 论文复现、Agent 与 Cedar Schema

### 用户

我想实现论文中的流程，包括策略生成器和硬评估器和软评估器这些，然后用论文中使用的数据集得到论文中的实验结果，我应该用哪个 agent，Cedar Schema 去哪里获得呢？

### 助手（根据上下文重建）

论文中大致使用：

- 策略生成器：Gemini 3 Pro；
- 硬评估器：Cedar 官方解析、Schema 校验和静态分析工具；
- 软评估器：Judge 和 Verifier，论文使用 Gemini 2.5 Flash，温度分别约为 0.3 和 0.1；
- 目标 Agent 轨迹：MedAgentBench 相关实验中使用 GPT-5 生成的轨迹。

Cedar Schema 有两个来源：

1. 论文附录给出了实验使用的 Schema；
2. 对通用系统而言，应当根据 Agent/MCP 的工具定义确定性生成 Schema，而不是手工绑定某个 Agent。

论文实验相关数据可参考 `hyn0027/agent-symbolic-guardrails` 仓库，包括 `policy.md`、MedAgentBench 工具定义、实验配置和保存的轨迹。需要注意，论文策略还包含从 MCP/FHIR 工具实现中提取的规则，只使用 `policy.md` 不一定能完全复现实验数字。

---

## 3. 是否构建通用系统

### 用户

回答尽量简洁扼要，我已经晕了，我如果最后想做成一个 OpenCode 插件的，那这个应该是对很多 agent 通用的一个东西，所以我应该做的是通用的系统，能够根据当前 agent 的 MCP 工具定义生成 schema？

### 助手（根据上下文重建）

是。推荐构建通用系统：

```text
Agent 系统提示词 + MCP tools/list + 自然语言规则
                     ↓
              自动生成 Cedar Schema
                     ↓
              自动生成 Cedar Policy
                     ↓
          硬评估 + 软评估 + 自动修复
                     ↓
              OpenCode 插件运行时使用
```

其中：

- MCP 工具定义决定 Cedar 的 Action、参数类型和资源结构；
- 自然语言规则决定允许或禁止的行为；
- 不同 Agent 只需要更换适配器和上下文映射，核心生成与评估流程保持通用。

---

## 4. 如何复现论文实验

### 用户

我如果想复现论文中的结果，应该怎么做呢？

### 助手（根据上下文重建）

建议分两步：

1. **先复现策略生成流程**
   - 获取论文数据集、自然语言规则、工具定义和附录 Schema；
   - 实现生成器、硬评估器、Judge、Verifier 和最多三轮的修复循环；
   - 记录每轮策略、错误、评分、耗时和 token 成本。

2. **再复现实验比较**
   - 使用论文的原始轨迹或相同任务集合；
   - 比较无策略、论文策略和新生成策略；
   - 统计安全违规拦截、正常请求放行、任务完成率以及误报、漏报等指标。

精确复现论文数字还要求尽量保持模型版本、提示词、数据划分、随机种子和策略来源一致。

---

## 5. 先做系统还是先追求论文数字

### 用户

对论文实验结果的复现不是我追求的，我先做 Autoformalization 系统，按照论文的做法，策略生成器和软硬评估器等，然后再用论文的数据集在用新生成的策略重放同一批轨迹进行实验结果对比等。在搭建 Autoformalization 流程的时候，我拿什么数据测试比较好呢，直接用论文的数据集吗？

### 助手（根据上下文重建）

不建议一开始直接使用完整论文数据集。采用分阶段测试：

- **阶段 A：小型 Code Agent 数据集**。约 20 条通用规则，配少量工具和正反例，用来快速调试生成、校验和修复循环。
- **阶段 B：规则变异数据集**。人为加入遗漏条件、冲突规则、错误字段和类型错误，专门测试软硬评估器。
- **阶段 C：论文数据集子集**。确认系统能处理医疗领域工具、复杂上下文和真实规则。
- **阶段 D：完整论文数据集**。冻结系统后做最终轨迹重放和结果对比，避免在测试集上反复调参。

---

## 6. 小型 Code Agent 后续是否需要替换

### 用户

我现在用这个小型的 code agent，之后需要替换成别的 agent 吧？

### 助手（根据上下文重建）

需要，但不是重写系统，而是替换输入和适配器：

- 阶段 A 使用小型 Code Agent 验证流程；
- 阶段 C/D 换成论文中的医疗 Agent、工具定义、Schema 和规则；
- OpenCode 插件阶段再接入当前实际 Agent 的 MCP 工具。

核心生成器、硬评估器、软评估器和实验框架应保持不变。

---

## 7. Autoformalization 实验计划

### 用户

参考之前的论文，为这个 Autoformalization 系统完成实验计划，要求：

1. 分模块设计；
2. 对于策略生成器，设计层次化的 prompt，自然语言的策略 + 系统提示词 + 工具定义 + Cedar Schema + 来自软硬评估器的反馈拼成 prompt；
3. 设计软硬评估器，并列出它们采用的指标。

先不动代码给我一版实验计划。

### 助手（根据上下文重建）

#### 7.1 系统模块

1. **Agent Spec Collector**：采集系统提示词、MCP 工具定义和运行时上下文。
2. **Cedar Schema Generator**：由 MCP 工具定义确定性生成 Cedar Schema。
3. **Policy Requirement Normalizer**：把自然语言规则整理成带编号、主体、动作、条件、例外和严重级别的 Requirement IR。
4. **Policy Generator**：根据分层 Prompt 生成 Cedar 策略。
5. **Hard Evaluator**：执行解析、Schema、类型和静态检查。
6. **Soft Evaluator**：Judge 检查语义，Verifier 复核 Judge 的结论。
7. **Workflow Orchestrator**：组织生成、评估、反馈和最多三轮修复。
8. **Replay Evaluator**：用安全和正常轨迹评估策略的实际效果。

#### 7.2 策略生成器的层次化 Prompt

- **Level 1：固定系统约束**  
  规定 Cedar 语法、输出格式、安全要求和禁止虚构字段等规则。
- **Level 2：Agent Grounding**  
  注入 Agent 系统提示词、MCP 工具定义和已生成的 Cedar Schema。
- **Level 3：Policy Requirements**  
  注入自然语言策略和规范化后的 Requirement IR。
- **Level 4：生成任务与输出契约**  
  要求输出 Cedar 策略及规则到策略 ID 的映射，最好使用固定 JSON 结构。
- **Level 5：评估反馈**  
  注入硬评估器错误和经过 Verifier 确认的软评估反馈。

反馈处理顺序：先修复语法、Schema 和类型错误，再修复关键语义缺陷，最后处理一般的约束过强、约束不足和可维护性问题。

#### 7.3 硬评估器

检查项：

- Cedar Parse；
- Schema 和类型校验；
- Action、字段和实体是否存在；
- `has` 防护；
- 策略 ID 和来源注解完整性；
- 空策略或永不触发策略；
- 重复、包含和冲突策略；
- 对预定义请求样例执行授权测试。

量化指标：

- `ParsePass@1`、`ParsePass@3`；
- `SchemaPass@1`、`SchemaPass@3`；
- `HardPass@1`、`HardPass@3`；
- `ValidPolicyRatio`；
- `NonVacuousPolicyRatio`；
- `ConflictFreeRatio`；
- `AnnotationCompleteness`；
- `MeanHardErrors`；
- `MeanRepairRounds`；
- 生成与评估耗时。

#### 7.4 软评估器

Judge 按 0—4 分检查：

- Coverage；
- Faithfulness；
- Scope Correctness；
- Condition Completeness；
- Under-constraint；
- Over-constraint；
- Hallucination；
- Traceability；
- Operationality；
- Maintainability。

Judge 必须给出具体反例；Verifier 判断问题是否真实、证据是否充分以及建议是否可执行，只把通过复核的反馈交给生成器。

量化指标：

- `RequirementCoverage`；
- `CriticalCoverage`；
- 各维度平均分；
- `UnderConstraintRate`；
- `OverConstraintRate`；
- `HallucinationRate`；
- `JudgeVerifierAgreement`；
- `AcceptedCritiqueRatio`；
- `SoftPass@1`、`SoftPass@3`。

拥有标注测试请求时，再统计：

- `ViolationRecall`；
- `SafeSpecificity`；
- `Precision`；
- `Macro-F1`；
- `CriticalRuleRecall`。

#### 7.5 实验阶段

- 阶段 A：小型 Code Agent 数据集；
- 阶段 B：错误和规则变异数据集；
- 阶段 C：MedAgentBench 子集；
- 阶段 D：完整论文数据集和轨迹重放。

消融实验至少比较：One-shot、层次化 Prompt、仅硬评估、仅软评估、完整系统、去掉 Schema。保持模型、输入、最大修复轮数一致，并记录多个随机种子的均值、标准差、成本和延迟。

---

## 8. 阶段 A 小型数据集

### 用户

请按照你说的阶段 A 先为我准备 code agent 小型数据集，准备 20 条通用规则，项目中貌似已经有了几条，可以在它的基础上添加到 20 条。

### 助手（执行结果重建）

已在 `datasets/autoformalization/code_agent/` 创建独立的小型数据集：

- `README.md`：数据集说明和验证方法；
- `system_prompt.txt`：小型 Code Agent 的系统提示词；
- `tools.json`：8 个真实工具及输入、输出 Schema；
- `policy.md`：20 条原子化通用规则，编号 `CAG-001` 至 `CAG-020`；
- `requirements.json`：20 条规则对应的 Requirement IR；
- `expected.cedarschema`：预期 Cedar Schema；
- `gold.cedar`：基础 permit 策略和 20 条 forbid 金标准策略；
- `cases.json`：40 个重放样例，每条规则各含一个 DENY 和一个 ALLOW；
- `verify.py`：完整性、Schema、Cedar 策略和重放结果验证脚本。

20 条规则覆盖：敏感文件读写、`.git` 修改、私钥和密钥内容、破坏性 shell 命令、提权、下载后直接执行、超长超时、不安全 URL、凭据搜索以及工具输出泄密等。

验证命令：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python datasets/autoformalization/code_agent/verify.py
```

验证结果：

```text
Validated 20 requirements, 23 Cedar policies, and 40 replay cases.
```

相关文件：

- [数据集说明](datasets/autoformalization/code_agent/README.md)
- [自然语言规则](datasets/autoformalization/code_agent/policy.md)
- [工具定义](datasets/autoformalization/code_agent/tools.json)
- [Requirement IR](datasets/autoformalization/code_agent/requirements.json)
- [Cedar Schema](datasets/autoformalization/code_agent/expected.cedarschema)
- [Cedar 金标准策略](datasets/autoformalization/code_agent/gold.cedar)
- [测试样例](datasets/autoformalization/code_agent/cases.json)
- [验证程序](datasets/autoformalization/code_agent/verify.py)

---

## 9. 恢复不可见的问题

### 用户

之前的聊天记录看不到了，请给出上上个问题。

### 助手

上上个问题是：

> 参考之前的论文，为这个 Autoformalization 系统完成实验计划，要求：1. 分模块设计；2. 对于策略生成器，设计层次化的 Prompt，自然语言的策略 + 系统提示词 + 工具定义 + Cedar Schema + 来自软硬评估器的反馈拼成 Prompt；3. 设计软硬评估器，并列出它们采用的指标。先不动代码，给我一版实验计划。

### 用户

上个问题呢？

### 助手

你的上个问题是：

> 请按照你说的阶段 A，先为我准备 Code Agent 小型数据集，准备 20 条通用规则。项目中貌似已经有了几条，可以在它的基础上添加到 20 条。

---

## 10. 导出聊天记录

### 用户

把我们的聊天记录（包括问题和回答）做成一个 md，放在当前文件夹下。

### 助手

已整理为当前文件 `CHAT_HISTORY.md`。由于较早的回答无法从界面逐字恢复，相关段落已明确标记为“根据上下文重建”。
