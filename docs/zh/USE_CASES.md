# 使用场景

AgentLedger 适合解决的问题，不是“Agent 能不能回答”，而是：

```text
它到底做了什么？
能不能安全重试？
之后能不能证明发生过什么？
能不能 replay/debug，且不重复真实副作用？
```

它不是新的 planning framework。当 Agent 开始跨 runtime boundary 时，比如调用工具、消耗模型预算、等待审批、写 checkpoint、改文件、调用业务 API、产出未来需要审计的 evidence，就该考虑 AgentLedger。

对产品团队或企业团队来说，它的承诺应该克制但有价值：给每一次 runtime-managed action 留下一张“收据”。团队可以看到 Agent 试图做什么、实际执行了什么、什么被批准或拒绝、哪里失败、花了多少钱，以及哪些内容可以在不再次触碰外部世界的情况下 replay。

## 什么时候该用 AgentLedger

如果你的 Agent 有下面任意一种情况，就适合接 AgentLedger：

| 场景 | AgentLedger 的作用 |
|---|---|
| Agent 调用有副作用的工具 | 当副作用经过 runtime boundary 时，Tool Ledger、causal request ID、idempotency key 和 replay-safe record 可以帮助避免重复外部写入。 |
| 一个 run 可能超过单进程生命周期 | durable run、step、session、checkpoint、lease 和 fencing 支持 crash/restart 后恢复。 |
| 工具需要 approval、policy 或 sandbox 控制 | runtime gate 在高风险工具执行前生效，而不是事后只在 trace 里看到。 |
| 需要 audit/debug evidence | evidence bundle、payload ref、event log、Inspector HTML 和 replay summary 让 run 可复盘。 |
| prompt、model、tool schema 变化可能破坏行为 | 历史 evidence 可用于 replay 或对比，不需要重新调用真实工具。 |
| model 使用和失败归因很重要 | model-call evidence、proposed tool call、cost record 和结构化 failure 让 model/tool 责任边界清晰。 |
| 已经在用 LangGraph、Temporal、Langfuse、MCP 或 model gateway | AgentLedger 放在旁边，负责 model/tool/state boundary 的 runtime guarantees。 |

## 什么时候不应该优先接

如果是下面情况，AgentLedger 不一定应该是第一个依赖：

- 只是 toy chatbot，没有工具、没有持久化、没有审计需求
- 只需要 planner、graph builder、prompt framework 或托管 trace UI
- 主要问题是长期 semantic memory、RAG retrieval 或 vector search
- 主要问题是 benchmark 管理或离线 eval scoring
- 还在做一次性原型，retry safety 和 evidence 暂时不重要

这些系统后续仍然可以和 AgentLedger 组合。核心判断很简单：当副作用、恢复、治理、证据成为工程问题时，再引入 AgentLedger。

## 帮团队解决哪些实际问题

AgentLedger 主要降低这些采用和运维问题的处理成本：

| 团队问题 | AgentLedger 的回答 |
|---|---|
| “Agent 说它调了工具，真实发生了吗？” | Tool Ledger 和 event log 记录 runtime-managed call、参数、状态、evidence ref 和 failure state。 |
| “这个 run 能不能重试，不要重复发邮件或重复建 ticket？” | idempotency key、causal request record 和 unknown-state handling 给 retry path 一个可以检查的依据。 |
| “这个高风险工具调用是谁批准的？” | approval record 和 policy decision 会关联到 run、step 和 tool evidence。 |
| “是模型选错了工具，还是 runtime/tool 实现失败了？” | model-call evidence、proposed tool call、actual tool call 和结构化 failure 会串在同一条 run timeline 里。 |
| “为什么 prompt/model 变更后 cost 或 latency 飙升？” | cost/failure attribution 可以按 run、agent、step、tool、model 归因。 |
| “工程师能不能不重复生产副作用就排查问题？” | evidence bundle、payload ref、Inspector HTML 和 replay summary 提供 side-effect-free 的复盘路径。 |

## 常见使用场景

| 场景 | runtime 风险 | AgentLedger 角色 |
|---|---|---|
| 客服 Agent 创建 ticket 或发送邮件 | crash/retry 可能重复创建 ticket 或重复发邮件。 | 记录 causal tool request，强制 idempotency，导出 review evidence。 |
| 法务、金融、运营 Agent 查询和更新业务系统 | tool call 可能触碰敏感数据，或者需要审批。 | 增加 policy/approval gate、durable evidence、cost/failure attribution 和 Inspector review。 |
| Coding Agent 修改文件、执行 shell、创建 PR | 很难证明哪个 command/tool 造成了文件变化。 | 记录 tool call、artifact、failure cause 和 replay-safe evidence ref，大内容不内联进记录。 |
| Research/RAG Agent 使用可变的网页、搜索、向量检索结果 | 之后重新执行时，输入上下文可能已经变了。 | 存储 retrieval/model evidence ref，并基于记录过的 evidence replay。 |
| LangGraph 或 OpenAI Agents SDK 应用需要补强工具和状态的运行时可靠性 | framework trace 不一定能阻止重复副作用，也不一定在工具执行前强制 approval。 | 用 AgentLedger 包住 node/tool，补 runtime guarantees。 |
| Temporal/Ray/Kubernetes worker 执行 Agent step | scheduler 管 worker，但不管 Agent-specific Tool Ledger、model evidence 和 replay contract。 | 在 worker step 内运行 AgentLedger，提供 checkpoint、fencing、evidence 和 governance。 |
| model 或 prompt 升级后的故障复盘 | 团队需要判断是模型建议了错误 tool call，还是 runtime 执行错了。 | 串起 model-call evidence、proposed tool call、approval/policy decision、actual tool call、failure 和 cost。 |

## 3 分钟 Demo

建议先跑 side-effect safety demo。它会故意模拟：工具已经改变外部世界，但 worker 在提交状态前崩溃。在这个受控流程里，工具通过 AgentLedger 并带有 idempotency key，所以重试可以复用已记录的副作用，而不是再创建一次。

```bash
PYTHONPATH=src python3 examples/three_minute_demo/demo.py
```

四语言版本：

```bash
cd go && go run ./examples/three_minute_demo
cd typescript && node examples/three_minute_demo/three_minute_demo.js
cd rust && cargo run --example three_minute_demo
```

预期结果：

- 第一次尝试在外部副作用发生后失败
- 重试成功
- 外部写入次数保持为 `1`
- 只产生一条对应副作用的 Tool Ledger record
- replay 基于 evidence 验证，不重新调用真实工具

这是最短的价值验证路径：在集成遵守 runtime boundary 的前提下，AgentLedger 把一次危险的重试变得可观察、可复盘，并且更安全。

## 保证边界

AgentLedger 不应该被描述成能让所有外部系统天然 exactly-once 的魔法层。它的可靠性声明依赖明确的集成边界：

- runtime-managed tool call 必须经过 AgentLedger API 或 adapter
- 有副作用的工具应该提供稳定 idempotency key
- 外部系统最好能暴露足够的业务标识，用于在可能时验证已完成的工作
- 大 payload 或敏感 payload 应作为受控 blob ref 或 redacted evidence 保存，不应该盲目内联
- 如果 replay/debug 需要区分 model behavior 和 runtime behavior，model call 应经过 model evidence boundary 记录
- 生产使用仍然需要正常运维能力：backup、migration、secret management、network policy、sandbox infrastructure 和 monitoring

在这些边界成立时，AgentLedger 能给团队一个具体的 runtime record 和 replay path。没有这些边界时，它仍然可以存证，但无法治理它看不到的副作用。

## 怎么和其它工具组合

AgentLedger 的设计目标是和现有 Agent 基础设施组合，而不是替代它们。

| 现有工具 | 继续负责 | AgentLedger 负责 |
|---|---|---|
| LangGraph、LangChain、CrewAI、AutoGen、OpenAI Agents SDK | planning、graph routing、agent logic、prompt/workflow structure | durable state、Tool Ledger、approval/policy/sandbox gate、evidence、replay-safe model/tool boundary |
| Temporal、Ray、Kubernetes | distributed workflow lifecycle、worker scheduling、infra 层 retry | agent-specific checkpoint、lease/fencing、model/tool evidence、cost/failure attribution |
| Langfuse、LangSmith、OpenTelemetry | trace UI、monitoring、dataset、dashboard | 执行路径内 runtime evidence、副作用治理、replay artifact、执行前 policy decision |
| MCP server 和内部 tool server | 暴露 tool、resource、prompt | tool governance gateway semantics：schema、permission、approval、sandbox、idempotency、audit |
| LiteLLM、new-api、one-api、企业 gateway | model routing、provider failover、credential、quota | model-call evidence、proposed tool-call record、replay semantics、model failure attribution |
| Vector DB 和 memory system | 长期 semantic memory 和 retrieval | session state、checkpointed state transition、retrieval evidence ref、lossless replay input |

## 接入前检查清单

深度接入前，先回答这些问题：

- 哪些 tool call 会产生外部副作用？
- 哪些副作用需要 idempotency key 或 pending-verification state？
- 哪些工具需要 approval、policy 或 sandbox 控制？
- 事故复盘时需要哪些 evidence？
- 哪些 model call 和 tool proposal 需要记录，方便 replay？
- runtime metadata 放哪里：SQLite、Postgres、MySQL，还是自定义 StateStore？
- 哪些大 payload 应该存 blob ref，而不是内联进记录？
- AgentLedger 外围的 planning/execution 由哪个 framework 或 scheduler 负责？

如果这些问题和你的系统相关，AgentLedger 解决的就是你当前 stack 里的真实问题。
