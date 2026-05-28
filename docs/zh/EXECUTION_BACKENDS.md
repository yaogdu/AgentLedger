# Execution Backends

AgentLedger 不应该和成熟的 durable execution 系统竞争。Temporal、Ray、Kubernetes 这类系统应被视为 execution backends。AgentLedger 是位于它们上方的 agent-specific runtime contract。

## 定位

```text
Temporal / Ray / Kubernetes
  durable scheduling、queue、worker、retry、timer、fleet management

AgentLedger
  agent runtime boundary、Tool Ledger、side-effect safety、evidence、
  replay safety、policy、sandbox、cost attribution、failure attribution
```

集成目标是：

```text
AgentLedger 不替代 Temporal。
AgentLedger 让跑在 Temporal 上的 Agent workflow 具备 agent-safe 语义。
```

## Backend 应该负责什么

Execution backend 可以负责：

- distributed scheduling
- worker queue
- durable timer
- retry backoff
- activity execution
- workflow lifecycle
- worker fleet management
- infrastructure-level heartbeat / timeout
- deployment topology

AgentLedger 应提供 adapter contract，而不是在 runtime-core 里重做完整调度平台。

## AgentLedger 必须保留什么

AgentLedger 必须保留 agent-specific invariants：

- `AgentContext` runtime boundary
- ToolGateway 和 Tool Ledger
- tool schema 与 capability boundary
- idempotency key 和 causal token
- policy、approval、sandbox decision records
- LLM request/response archive
- tool request/response archive
- side-effect-safe replay 和 shadow execution
- evidence bundle 与 audit trail
- 按 run/agent/step/tool/model 做 cost attribution
- agent/model/tool/runtime failure taxonomy
- adapter conformance checks

这些不是通用 workflow guarantee，而是 Agent 执行 guarantee。


## Workflow 内部的 Agent 节点

Temporal workflow 中可以有多个 agent activities：

```text
ResearchAgent Activity -> CodeAgent Activity -> ReviewAgent Activity
```

Temporal 可以让这个 workflow durable。它可以调度每个 activity、重试、超时，并在 worker crash 后恢复。这覆盖的是外层 workflow lifecycle。

AgentLedger 仍然适合放在每个 activity 内部，因为它治理 agent node 内部发生的事情：

```text
model_call_requested / model_call_completed
tool_call_requested / tool_permission_decided / tool_call_completed
tool_ledger RESERVED / RUNNING / SUCCEEDED / PENDING_VERIFICATION
state_patch_proposed / state_patch_committed
artifact_created / cost_recorded / failure_classified
```

如果 activity 是一个黑盒 `run_research_agent()`，AgentLedger 可以打开这个黑盒。如果把每个 tool call 都拆成 Temporal activity，AgentLedger 仍然可以避免 agent-specific semantics 散落在 workflow glue code 里。

有些 Temporal workflow 不需要 AgentLedger。如果 agent node 没有高风险工具、没有外部写入、不需要 replay-safe debugging、不需要 evidence/audit，并且 activity input/output 足够，那 Temporal 可能就够了。

当 agent node 调用模型和工具、写外部系统、需要权限或 sandbox、需要 evidence bundle，或者 replay 不能重复真实副作用时，AgentLedger 才有明显价值。

## Temporal Adapter 形态

Temporal 集成通常应是：

```text
Agent / Framework
  LangGraph、custom agent、plain function
        |
        v
AgentLedger Runtime Boundary
  AgentContext、ToolGateway、Tool Ledger、
  Policy / Approval / Sandbox、Evidence / Replay
        |
        v
TemporalSchedulerAdapter
  把 AgentLedger run/step execution 映射到 workflow/activity execution
        |
        v
Temporal
  durable workflow history、activity retry、timer、queue、worker fleet
```

Temporal 可以负责运行 activity。AgentLedger 仍然应该负责 tool/model boundary。

## 重合是正常的

确实有重合：

| 能力 | Temporal | AgentLedger |
|---|---|---|
| durable execution | 强 | runtime-core local baseline + adapters |
| retry | activity/workflow retry | agent/tool/model failure semantics |
| replay/history | workflow history replay | 不产生 model/tool side effect 的 evidence replay |
| distributed workers | 强 | local worker + backend adapters |
| cancellation/timeouts | 强 | agent step cancellation/fencing semantics |
| observability | workflow/activity visibility | agent evidence、tool audit、cost/failure attribution |

设计选择不是删除 AgentLedger，而是让 AgentLedger 保持薄，把通用分布式执行交给成熟 backend。

## Backend Adapter Contract

一个 backend adapter 应保留这些行为：

```text
create or map an AgentLedger run
claim or schedule an AgentLedger step
execute through AgentContext
route external calls through ToolGateway
commit state only through the runtime store boundary
preserve cancellation and stale-worker fencing semantics
export evidence that links backend ids to AgentLedger run/step ids
avoid real side effects during replay/shadow execution
```

## 非目标

runtime-core 不应该变成：

- Temporal replacement
- Ray replacement
- Kubernetes operator product
- 完整 worker fleet management platform
- 通用 distributed workflow engine

AgentLedger 应提供 local defaults 用于 quickstart 和 conformance，然后通过 adapter 接入成熟 backends。

## Temporal + LangGraph + AgentLedger

三层可以组合使用：

```text
Temporal
  outer durable distributed workflow runtime

LangGraph
  agent graph / workflow logic / multi-agent orchestration

AgentLedger
  inner runtime reliability、evidence、tool/model governance layer
```

典型栈：

```text
Temporal Workflow
  └── LangGraph Run Activity
        ├── ResearchAgent node -> AgentLedger AgentContext / ToolGateway
        ├── CodeAgent node     -> AgentLedger AgentContext / ToolGateway
        └── ReviewAgent node   -> AgentLedger AgentContext / ToolGateway
```

在这个组合里，Temporal 负责 workflow lifecycle、worker queue、retry、timer 和 distributed execution。LangGraph 负责 graph node、edge、routing 和 multi-agent orchestration。AgentLedger 负责每个 node 内部的 model/tool boundary：Tool Ledger、idempotency、approval、sandbox、evidence、replay safety、cost/failure attribution。

这是复杂生产系统里更清晰的定位。AgentLedger 不应该声称替代 Temporal 或 LangGraph，而是让跑在 Temporal 里的 LangGraph nodes 具备 agent-safe 能力。
