# 1.5.0 Framework 与 Temporal Adoption 设计

状态：下一阶段 adoption-focused release 的设计草案。

这个版本的目标是让 AgentLedger 更容易接入已有 Agent / workflow stack，同时不把 runtime-core 扩成 Agent 框架、workflow engine、trace UI、eval platform 或 model gateway。

## 目标

`1.5.0` 需要证明三条接入路径：

```text
OpenAI Agents SDK-style agent 可以把 tool/model evidence 接入 AgentLedger。
framework-native example 可以展示 runtime boundary，而不是替代框架。
Temporal-style workflow execution 可以在 activity 内调用 AgentLedger，并保持清晰职责边界。
```

用户看完示例后应该能回答：

```text
AgentLedger 放在哪一层？
已有框架仍然负责什么？
AgentLedger 新增了哪些 evidence？
如何在不重复副作用的情况下 replay/debug？
```

## 范围

包含：

- 聚焦的 OpenAI Agents SDK-style example
- Temporal bridge example 和 optional adapter boundary
- 常见 adoption path 的 framework-native smoke fixtures
- 解释 framework/workflow ownership boundary 的文档
- 保证示例可运行的 CI smoke checks

不包含：

- 不做新的 planner、graph engine、team orchestration 或 agent collaboration framework
- 不替代 OpenAI Agents SDK、LangGraph、CrewAI、AutoGen、LangChain 或 Temporal
- runtime-core test 不要求 Temporal server
- 不做长运行 Web service 或 hosted control plane
- 不做 model provider routing，也不绑定 provider SDK

## 分层

```text
Agent framework
  负责: agent definitions, prompts, planning, handoffs, graph/team topology

Workflow backend
  负责: long-running workflow lifecycle, activity retries, worker orchestration, timers

AgentLedger
  负责: run/step evidence, model/tool boundary records, Tool Ledger,
        approval/sandbox/budget gates, replay-safe evidence, cost/failure attribution
```

AgentLedger 应嵌入 framework node、activity 或 tool call 的 execution boundary。它不接管框架的 planning loop，也不接管 Temporal 的 workflow lifecycle。

## OpenAI Agents SDK-style Example

该示例应保持 dependency-light。如果没有安装真实 SDK，可以用一个本地 facade 表达集成形态，同时文档说明真实 SDK 接入边界。

必需流程：

```text
create AgentLedger run
record model request/response or model failure evidence
record model-proposed tool call
call a runtime-managed tool through ctx.call_tool(...)
trigger approval for a high-risk tool
commit state after approval/tool execution
export evidence
open Inspector or replay summary
```

必需 evidence：

- `model_call_requested`
- `model_call_completed` 或 `model_call_failed`
- `tool_call_proposed`
- Tool Ledger row
- 高风险 tool 的 approval request 和 approval decision
- 可用时记录 model/tool usage cost
- replay summary 不应再次调用 provider 或 tool

验收标准：

- 默认不依赖网络即可运行
- 输出包含 run id、evidence path、replay summary，以及可用时的 Inspector/static debug path
- failure path 能展示 model/tool evidence，且不需要真实 provider
- 文档明确说明不代表 OpenAI 官方 endorsement 或 certification

## Framework-native Smoke Fixtures

smoke fixture 不应该变成大 demo。它们只需要证明常见框架可以保留 AgentLedger boundary。

初始 fixture：

```text
LangGraph-style node
OpenAI Agents SDK-style agent/tool call
LangChain runnable facade
CrewAI / AutoGen method facade where dependency-free fixtures already exist
```

每个 fixture 应证明：

- framework code 可以进入 AgentLedger run
- framework-owned input/output 会进入 evidence 或 final state
- 有副作用的 tool call 仍经过 ToolGateway
- 即使模型由 framework 或 provider SDK 调用，也能记录 model evidence
- replay/debug 读取 evidence，而不是重新执行 framework work

CI 应优先使用 dependency-free fixtures。真实 framework SDK smoke tests 可以放在 extras 或环境变量保护下。

## Temporal Bridge 设计

Temporal 应被视为 execution backend，而不是 AgentLedger 替代品。

Temporal 负责：

- workflow lifecycle
- activity scheduling
- workflow/activity retry policy
- timers 和 long waits
- worker orchestration
- workflow history

AgentLedger 在 activity 内负责：

- `run_id` 和 `step_id` evidence
- Tool Ledger idempotency
- model-call evidence 和 tool-call proposals
- approval/sandbox/budget gates
- cost/failure attribution
- replay-safe evidence export

推荐映射：

| Temporal concept | AgentLedger concept |
|---|---|
| workflow id | run/session metadata 中的 `external_workflow_id` |
| workflow run id | metadata 中的 `external_workflow_run_id` |
| activity id | step/event metadata 中的 `external_activity_id` |
| activity retry attempt | AgentLedger step attempt metadata，但不是 Tool Ledger 幂等的事实来源 |
| activity failure | 如果发生在 runtime boundary 内，记录为 AgentLedger failure event / failure envelope |
| workflow cancellation | activity 观察到取消后，传播为 AgentLedger cancellation request |

关键规则：

```text
Temporal 可以 retry activity。
AgentLedger 必须阻止 retried activity 内重复执行 tool side effect。
```

bridge example 应故意模拟：

```text
activity starts
runtime-managed tool side effect succeeds
activity crashes before framework/workflow-level success
Temporal-style retry calls the activity again
AgentLedger Tool Ledger reuses the prior side-effect result
evidence proves one external side effect and two activity attempts
```

Replay 行为：

- AgentLedger replay 不应启动新的 Temporal workflow。
- AgentLedger replay 应读取 evidence，并报告 Temporal/workflow metadata。
- 如果 candidate rerun 会再次执行 Temporal activity，必须标记为 new run，而不是 replay。

Failure 归属：

- Temporal workflow failure 解释 scheduling/activity outcome。
- AgentLedger failure attribution 解释 activity 内 model/tool/policy/sandbox/budget/state outcome。
- 报告应通过 workflow/activity metadata 互相链接，而不是把两个系统混成一个隐藏状态机。

Cancellation 归属：

- Temporal cancellation 是外部输入。
- AgentLedger 在 runtime 观察到取消时记录 cancellation intent，并 fence stale commit。
- child/activity-local side effects 仍遵守 Tool Ledger、sandbox 和 approval 规则。

验收标准：

- dependency-free Temporal-style bridge example 可在 CI 运行
- 文档解释如何把本地 facade 换成真实 Temporal SDK
- 输出证明 activity retry 没有重复外部副作用
- evidence export 包含 workflow/activity correlation metadata
- failure/cost attribution 仍可通过 AgentLedger report 查看

## Contract 和 Schema 影响

优先使用 metadata 和 event payload 扩展，不优先新增必需 schema 字段。

本版本允许：

- 在 event payload、run metadata 或 evidence export 中加入 framework/workflow metadata
- adapter helper functions 或 optional package boundary
- examples 和 smoke fixtures

除非确有必要，否则避免：

- 必需的 StateStore schema migration
- 新 stable runtime-core event type
- 修改 Tool Ledger idempotency semantics
- 让 Temporal 或任一 framework SDK 成为 core dependency

## Tests 和 Gates

必需本地检查：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python scripts/benchmark_runtime.py --iterations 20 --output-dir /tmp/agentledger-benchmark
python scripts/check_language_parity.py
```

新增检查：

- OpenAI Agents SDK-style example smoke
- Temporal bridge retry/idempotency smoke
- 至少一个 framework-native boundary smoke
- boundary lint 保持干净
- benchmark coverage 复用现有 semantic checks；只有 durable runtime invariant 变化时才新增 semantic check

## 文档交付物

- OpenAI Agents SDK-style integration example README
- Temporal bridge example README
- 如有需要，更新 `docs/EXECUTION_BACKENDS.md` 的 Temporal ownership split
- 更新 `docs/USE_CASES.md` 的 framework/workflow adoption path
- release 后更新 `docs/ROADMAP.md` implementation status

## Definition of Done

`1.5.0` 完成标准：

- 开发者可以运行 OpenAI Agents SDK-style example，并看到 model/tool/approval/evidence/replay 输出
- 开发者可以运行 Temporal bridge example，并看到 retry 不重复副作用
- framework-native smoke fixtures 被测试或 CI 覆盖
- benchmark 和 language parity gates 保持绿色
- 文档清楚说明 AgentLedger 负责什么、framework/workflow backend 负责什么

---

generated by codex cli
