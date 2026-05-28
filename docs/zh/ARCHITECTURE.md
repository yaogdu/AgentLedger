# 架构说明

AgentLedger 是面向 Agent Harness stack 的 runtime reliability layer。它不是 Agent 框架、模型 SDK、workflow engine、eval 系统、observability 套件、RAG 系统或 sandbox infrastructure provider。

核心架构目标是把 Agent 业务逻辑和 runtime reliability 机制分开，同时让 runtime core 保持“薄但不可替代”：只负责必须在 Agent 逻辑与外部副作用边界上强制保证的语义。成熟系统通过 adapter 和 conformance test 接入，而不是被重做进 core。

在完整 Harness stack 里，AgentLedger 是位于 LangGraph、Temporal、Langfuse、MCP、model provider、storage backend 和 sandbox provider 下方或旁边的 reliability substrate。

实际分层是：

```text
core contract -> dependency-free local default -> optional production adapter
```

这样 hello-world 用户不需要额外服务就能跑起来，高阶用户也可以通过同一套 runtime contract 换成成熟基础设施。

```text
Agent / Framework 负责业务逻辑、推理和编排。
AgentLedger Runtime 负责状态、lease、tool governance、replay、evidence 和 adapter contracts。
```

![AgentLedger runtime architecture](../assets/agentledger-runtime-architecture.svg)

## Execution Backend 边界

Temporal、Ray、Kubernetes 这类系统可以作为 scheduler/execution adapters 放在 AgentLedger runtime boundary 下方。AgentLedger 不替代它们，而是让跑在这些 backend 上的 Agent execution 具备 tool governance、replay safety、audit 和 cost/failure attribution。详见 `EXECUTION_BACKENDS.md`。

## 分层架构

```text
Agent / Framework Layer
  Python functions, LangGraph, CrewAI, AutoGen, custom agents, future TS/Rust/Go workers

Runtime Boundary
  AgentContext, Runtime, ToolGateway, PolicyEngine, PolicyDecision, BudgetController

Execution Control
  Scheduler, lease, fencing token, retry policy, cancellation, worker loop

Durable Metadata
  runs, steps, events, tool_ledger, artifacts, costs, approvals, schema_migrations

Evidence and Reliability
  replay, evidence bundle, diff, evidence checks, trace JSONL, shadow mode

Adapter Layer
  storage, blob store, framework adapters, MCP, sandbox, observability, policy, model providers
```

## 核心执行流程

```text
create_run
  -> append run_created / step_created
claim_step
  -> 获取 lease token 和 attempt number
execute agent through AgentContext
  -> 通过 ToolGateway 调用工具
  -> 写 state patch
  -> 创建 artifact / media artifact / stream checkpoint
commit_state_patch
  -> 校验 lease token
  -> 校验 base state version
  -> 原子合并 state patch
  -> append completion events
replay/evidence
  -> 读取事件和归档 payload
  -> 不调用外部工具
```

## 关键模块

| 模块 | 职责 |
|---|---|
| `runtime.py` | Runtime 编排、本地执行入口。 |
| `context.py` | Agent-facing context，提供 state、tool、artifact、heartbeat 能力。 |
| `store.py` | SQLite StateStore reference implementation。 |
| `tools.py` | Tool registry、ToolGateway、policy、approval、ledger、sandbox boundary。 |
| `policy.py` | PolicyRequest、PolicyDecision、evaluator registry、role/risk policy、decision composition。 |
| `replay.py` | 不产生外部副作用的 replay summary。 |
| `evidence.py` | Evidence bundle export。 |
| `scheduler.py` | lease recovery、cancellation、status。 |
| `worker.py` | Local worker loop 和 WorkerService。 |
| `sandbox.py` | Sandbox executor contract 和内置 adapter slots。 |
| `media.py` | Media artifact、lineage、stream chunk、checkpoint contracts。 |
| `contract.py` | 语言无关 runtime contract export。 |

## 系统不变量

```text
events append-only 且按 run 内 seq 排序
state commit 必须持有有效 lease token
state commit 必须匹配 base state version
stale / expired / cancelled worker 不能提交状态
managed side effect 必须有唯一 idempotency key
PENDING_VERIFICATION 不能自动无脑重试
replay / shadow mode 不能产生真实外部副作用
sandbox-required tool 在隔离不可用时必须 fail closed
approval-required tool 在审批前不能执行
secret 不应默认写入 event payload 或 evidence
```

## Adapter 边界

Core 负责语义和不变量，adapter 负责具体基础设施。

```text
StateStore: SQLite, Postgres, custom store
BlobStore: local fs, S3, MinIO, custom object store
SandboxExecutor: none, local, bubblewrap, Docker, Kubernetes/gVisor, Firecracker, E2B
FrameworkAdapter: LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents SDK, custom
Observability: JSONL, OpenTelemetry, LangSmith-style backend, internal tracing
Policy: YAML, OPA, Cedar, RBAC/ABAC
```

一个 adapter 是否兼容，取决于它是否保留 runtime invariants，并通过对应 conformance tests。

## 多语言边界

Python 是当前 reference implementation，但不是协议边界。长期目标是 Python、Go、TypeScript、Rust 的 native runtime-core parity。SDK/client-only package 可以帮助接入，但不能单独算 runtime-ready。

Go、TypeScript、Rust 后续实现应对齐：

```text
contracts/agentledger.runtime.v1.json
docs/RUNTIME_SPEC.md
docs/MULTI_LANGUAGE.md
docs/LANGUAGE_PARITY_MATRIX.md
StateStore conformance semantics
evidence/replay golden fixtures
```

这样可以避免各语言自行发明不同的 event 名称、lease 语义、idempotency 行为或 evidence bundle 形状。
