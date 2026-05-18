# 四语言实现对比

[English](../LANGUAGE_IMPLEMENTATION_COMPARISON.md) | [中文](LANGUAGE_IMPLEMENTATION_COMPARISON.md)

本文明确四种语言的实现边界。AgentLedger 的“完全对齐”指 **portable runtime-core parity**，不是要求每种语言都有完全相同的 provider、云 SDK、沙箱执行器或生态框架 adapter。

## 表格说明

| 标记 | 含义 |
|---|---|
| Yes | 该语言已实现。 |
| Contract | 有跨语言 contract、facade、manifest 或 injected-client adapter；真实 provider hardening 可在外部完成。 |
| Python-only | 只在 Python 实现，因为上游框架或生态主要是 Python。 |
| N/A | 对该语言不适用，或有意不放入 runtime core。 |
| Roadmap | 后续可做，但不属于当前 parity claim。 |

## Runtime-core 对齐

这些能力属于对齐目标。四种语言都应该实现同一套 runtime 语义，并通过共享 conformance checks。

| 能力 | Python | Go | TypeScript | Rust | 证据 / 说明 |
|---|---:|---:|---:|---:|---|
| AgentContext / execution boundary | Yes | Yes | Yes | Yes | Runtime 管理执行上下文边界。 |
| Run / session / step model | Yes | Yes | Yes | Yes | 共享 run state machine。 |
| Durable state commits | Yes | Yes | Yes | Yes | 每种语言都有本地 durable/snapshot store。 |
| Event log / WAL semantics | Yes | Yes | Yes | Yes | Evidence/replay fixtures 覆盖。 |
| Lease, fencing, recovery | Yes | Yes | Yes | Yes | stale worker fencing 和 expired lease recovery。 |
| Cancellation semantics | Yes | Yes | Yes | Yes | cancelled run 会 fence late commits。 |
| ToolGateway | Yes | Yes | Yes | Yes | Runtime-managed tool execution boundary。 |
| Tool schema validation | Yes | Yes | Yes | Yes | tool input/output schema checks。 |
| Tool Ledger / idempotency | Yes | Yes | Yes | Yes | 幂等 side-effect retry 语义。 |
| Policy denial | Yes | Yes | Yes | Yes | 执行前拒绝。 |
| Approval pause/resume | Yes | Yes | Yes | Yes | HITL approval 语义。 |
| Sandbox fail-closed boundary | Yes | Yes | Yes | Yes | 对齐的是边界语义，不是 provider 数量。 |
| Budget enforcement | Yes | Yes | Yes | Yes | runtime-level budget exceeded 行为。 |
| Cost attribution | Yes | Yes | Yes | Yes | run/step/tool/model attribution shape。 |
| Failure attribution | Yes | Yes | Yes | Yes | agent/tool/model/runtime 分类。 |
| Evidence export | Yes | Yes | Yes | Yes | evidence bundle consumers。 |
| Replay without side effects | Yes | Yes | Yes | Yes | replay 不重复外部副作用。 |
| Diff / divergence / debug summary | Yes | Yes | Yes | Yes | evidence consumers。 |
| Static debug HTML export | Yes | Yes | Yes | Yes | debug artifact generation。 |
| Time travel timeline | Yes | Yes | Yes | Yes | timeline/state-at-seq 语义。 |
| Failure injection suite | Yes | Yes | Yes | Yes | reliability harness contract。 |
| Evidence regression | Yes | Yes | Yes | Yes | golden/evidence comparison。 |
| Shadow report | Yes | Yes | Yes | Yes | replay/rerun comparison shape。 |
| Scheduler facade | Yes | Yes | Yes | Yes | local scheduler/status/recover/cancel facade。 |
| Local worker/service | Yes | Yes | Yes | Yes | worker loop 和 idle polling 语义。 |
| CLI baseline | Yes | Yes | Yes | Yes | `help`、`doctor`、`quickstart`、`conformance`、`contract`。 |
| Runnable quickstart example | Yes | Yes | Yes | Yes | `examples/`、`go/examples/`、`typescript/examples/`、`rust/examples/`。 |
| Contract export/validation | Yes | Yes | Yes | Yes | 共享 contract 和 conformance manifest。 |

## 可跨语言 Adapter Contract

这些能力足够 portable，所以四种语言都暴露 contract/facade。但这不代表每种语言都内置同样的生产驱动或云 SDK。

| 能力 | Python | Go | TypeScript | Rust | 证据 / 说明 |
|---|---:|---:|---:|---:|---|
| Local StateStore | Yes | Yes | Yes | Yes | quickstart 和测试默认本地实现。 |
| Local BlobStore | Yes | Yes | Yes | Yes | content-addressed local blob 语义。 |
| Postgres adapter contract | Yes | Contract | Contract | Contract | Python 有 `PostgresStore`；Go/TS/Rust 是 injected SQL adapter/facade。 |
| S3/MinIO blob adapter contract | Yes | Contract | Contract | Contract | Python 有 `S3BlobStore`；Go/TS/Rust 是 injected object-client adapter/facade。 |
| OTLP trace export / transport | Yes | Contract | Contract | Contract | JSON/export 或 injected transport boundary。 |
| Docker sandbox manifest | Yes | Contract | Contract | Contract | portable manifest/fail-closed 行为；daemon hardening 属于外部。 |
| MCP-style tool/context mapping | Yes | Yes | Yes | Yes | dependency-free in-memory contracts。 |
| Function/method framework facade | Yes | Yes | Yes | Yes | 通用 dependency-free framework adapter shape。 |
| Media artifact refs | Yes | Yes | Yes | Yes | 只做 evidence refs，不做完整 media processing。 |
| Event stream checkpoint refs | Yes | Yes | Yes | Yes | checkpoint/ref 语义。 |

## 具体 Provider 实现

这些不要求四种语言完全一致。它们属于 provider-specific infrastructure 或 production-pilot path。

| 能力 | Python | Go | TypeScript | Rust | 说明 |
|---|---:|---:|---:|---:|---|
| Sandbox executor 数量 | 7 | 2 | 2 | 1 | Python 有 Bubblewrap/Docker/E2B/Firecracker/Kubernetes/Local/Remote。其他语言保留 provider facade 和 fail-closed semantics。 |
| Bubblewrap executor | Yes | N/A | N/A | N/A | Linux/Python command executor path；不是 core parity 要求。 |
| Docker executor | Yes | Contract | Contract | Contract | Python 可通过 CLI 执行；其他语言暴露 manifest/adapter boundary。 |
| E2B executor | Yes | Roadmap | Roadmap | Roadmap | hosted sandbox provider，属于 adapter 层。 |
| Firecracker executor | Yes | Roadmap | Roadmap | Roadmap | infrastructure-specific sandbox adapter。 |
| Kubernetes executor | Yes | Roadmap | Roadmap | Roadmap | deployment/sandbox infrastructure adapter。 |
| Native Postgres StateStore driver | Yes | Roadmap | Roadmap | Roadmap | Python 有 psycopg-backed store；其他语言当前是 injected SQL contract。 |
| Native S3 SDK-backed BlobStore | Yes | Roadmap | Roadmap | Roadmap | Python 有 optional boto3 path；其他语言是 injected object client boundary。 |
| Real-service Postgres hardening | Optional | Optional | Optional | Optional | release/pilot 验证，不属于当前 core parity。 |
| Real-service S3/MinIO hardening | Optional | Optional | Optional | Optional | release/pilot 验证，不属于当前 core parity。 |

## Python-only 生态 Adapter

这些 adapter 存在是因为上游 agent framework 主要是 Python 生态。不应该为了表格对称而强行复制到 Go、TypeScript 或 Rust。

| Adapter | Python | Go | TypeScript | Rust | 原因 |
|---|---:|---:|---:|---:|---|
| LangGraphCheckpointerAdapter | Yes | N/A | N/A | N/A | LangGraph 是 Python 生态。 |
| LangGraphNodeAdapter | Yes | N/A | N/A | N/A | LangGraph 是 Python 生态。 |
| LangChainRunnableAdapter | Yes | N/A | N/A | N/A | 当前内置目标是 Python LangChain。 |
| CrewAIAdapter | Yes | N/A | N/A | N/A | CrewAI 是 Python 生态。 |
| AutoGenAdapter | Yes | N/A | N/A | N/A | 当前内置目标是 Python AutoGen。 |
| OpenAIAgentsSDKAdapter | Yes | N/A | N/A | N/A | 当前内置目标是 Python Agents SDK。 |
| LlamaIndexAdapter | Yes | N/A | N/A | N/A | 当前内置目标是 Python LlamaIndex。 |
| SemanticKernelAdapter | Yes | N/A | N/A | N/A | 当前内置目标是 Python Semantic Kernel path。 |

## 什么算完全对齐

完全对齐是：

```text
portable runtime-core behavior + contract + conformance + CLI/DX + examples + package metadata
```

不是：

```text
每种语言都有完全相同的 provider implementation、cloud SDK、Python-only ecosystem adapter
```

## 目录结构决策

当前目录不需要调整：

| 目录 | 保留？ | 原因 |
|---|---:|---|
| `go/` | Yes | 符合 Go module 习惯，Go package 独立。 |
| `typescript/` | Yes | 源语言命名清晰；package 名是 `@agentledger/runtime`。runtime 面向 Node.js，但实现/文档表面是 TypeScript-compatible。 |
| `rust/` | Yes | 符合 Rust crate 习惯，Cargo 文件独立。 |
| `src/agentledger/` | Yes | Python reference package layout。 |

现在不建议把 `typescript/` 改成 `node/`：重命名会带来 churn，但不会改善 runtime 语义。如果未来拆 repo 或调整发布形态，再统一考虑 package/repo 命名。
