# 路线图

本文是 `../ROADMAP.md` 的中文主路径版本。AgentLedger 按阶段演进，每个阶段先证明一个可靠性能力，再扩展更多表面积。

## 能力范围地图

为了避免 runtime 变得过大、过臃肿，每个大能力都拆成三层：core contract、optional adapter、explicit non-goal。runtime-core 只负责生产执行路径上的控制点、状态转换、evidence、replay hooks、CLI checks、conformance 和安全默认值；重依赖、离线批处理和部署相关选择留给 optional adapters 或独立工具。

路线原则是“薄但不可替代的 runtime core”：只内建那些不在 runtime boundary 内就无法可靠保证的能力。如果某一层业界已经有成熟系统，AgentLedger 应该提供 adapter contract 和 conformance suite，而不是重做那一层。

大部分能力都按三层判断：core contract、built-in minimal implementation、optional production adapter。最小内置实现保证开箱可用；生产 adapter 让用户接入成熟系统，同时不把重依赖塞进 core。

| 能力 | runtime-core 负责 | optional adapter 可负责 | core 明确不做 |
|---|---|---|---|
| Planning / Workflow | adapter contract、runtime-managed checkpoint、evidence hook、tool boundary integration | LangGraph、CrewAI、AutoGen、LangChain、Temporal、Prefect、Airflow、自定义 workflow adapter | 重新实现 planner、graph engine 或 workflow engine |
| Eval / Evidence Consumers | evidence export、replay、deterministic rerun hooks、最小 side-effect-free regression checks、conformance fixtures | 外部 eval runner、LLM judge、benchmark datasets、CI 报告落地 | 跑 N 个 agent x M 个 case 的完整离线评测器、指标服务、case 管理或长运行 Web 应用 |
| Tracing / Observability | structured events、trace JSONL、OTLP/JSON export、evidence links | OpenTelemetry SDK packages、collector recipes、external trace stores | 完整观测套件 |
| Guardrails | ToolSpec schema validation、policy checks、approval、pre/postcondition hooks、adversarial review gates | 更强 policy engine、项目规则包、外部 review 流程 | 业务治理后台 |
| Tool Gateway + Sandbox | ToolGateway、Tool Ledger、idempotency、audit、sandbox executor contract、fail-closed behavior | Docker、bubblewrap、Kubernetes/gVisor、E2B、Firecracker、自定义 executor | 外部 sandbox 基础设施托管 |
| Memory | session memory、short-term durable state、versioned memory refs、shared findings、replayable memory events | vector store、semantic retrieval、RAG、long-term knowledge store | 完整知识库或语义检索系统 |
| Session / HITL | run/session/step 状态机、approval request lifecycle、audit events | 外部人工 review 队列、chat/app integrations | 业务 review 后台或流程后台 |
| FinOps / Cost Control | token/call/cost records、budget enforcement hooks、cost attribution reports | provider price catalogs、finance exports、alerts | 发票或支付系统 |

这张范围地图也是 release gate 的一部分：新增能力要么作为生产执行可靠性 contract 进入 runtime-core，要么作为 optional adapter，要么作为独立 evidence consumer，要么明确写入 out of scope。默认选择应是 adapter 或外部 consumer，除非只有 runtime-core 才能强制保证对应 invariant。

## v1.0 Stable Runtime-Core Baseline

当前 Python reference runtime-core 已实现并通过 release gates。

目标：

```text
证明本地 durable execution
证明 Tool Ledger idempotency
证明 event-level replay/evidence
证明 policy/approval/sandbox boundaries
证明 storage/runtime contracts 可扩展
```

## Post-v1 - Developer Experience and Framework Adoption

当前 v1.0 core/adapters path 已实现：

```text
LangGraph dependency-free facade
LangChain / CrewAI / AutoGen / OpenAI Agents SDK / LlamaIndex / Semantic Kernel method facades
adapter conformance fixtures
debug timeline / state diff / static HTML export
plain Python / LangGraph / MCP / sandbox examples
runtime-boundary lint and JSON rule packs
tool schema/catalog export
Rust/TypeScript/Go contract docs
```

剩余：

```text
exact optional framework packages
framework-native smoke fixtures
deeper LangGraph package compatibility
more runtime-boundary lint examples
```

## Post-v1 - Production Adapter Hardening

当前 v1.0 core/adapters path 已实现：

```text
Postgres StateStore adapter path
S3/MinIO BlobStore adapter path
SQLite/Postgres migration commands and DDL catalog
backup/restore guide and backup readiness checker
OTLP JSON export and optional collector POST
worker guide, WorkerService, worker conformance
failure injection suite
policy and approval examples
sandbox contracts and Docker/bubblewrap/Kubernetes paths
```

剩余：

```text
production rollout exercises and restore drills
hardened OpenTelemetry adapter package
worker supervision and load/concurrency validation
stronger policy packs
sandbox deployment recipes with secret/network/resource guidance
actual compaction/snapshot job that preserves replay guarantees
```

## Post-v1 - Reliability Harness and Evidence Consumers

目标：

```text
让 prompt / workflow / runtime 变更可测试
把 evidence 变成外部和本地检查的 regression input
```

方向：

```text
richer divergence reports
richer golden corpus UX
larger real-world benchmark corpus
cost/failure attribution regression reports
adversarial review policy packs
shadow mode comparison workflows
additional golden evidence fixtures
```

## Post-v1 - Multimodal and Stream Adapters

当前已经有 preview contracts：

```text
MediaArtifact
MediaMetadata
ArtifactLineage
StreamChunkRef
EventStreamCheckpoint
AgentContext helpers
evidence indexes
replay validation/counts
eval/regression gates
backup/retention protected refs
trace spans
media tool conventions
media runtime conformance
```

剩余：

```text
image/audio/video/frame/transcription/embedding adapters
stream transport adapters
backpressure/cancellation integration
richer evidence cross-links
adapter-level replay semantics for reusing captured media artifacts
```

## v1.0 - Stable Runtime Contract

状态：Python runtime-core contract 已实现。

v1.0 稳定范围：

```text
AgentContext API boundary
runtime contract JSON
event/evidence schema
Tool Ledger semantics
StateStore and BlobStore conformance suite
versioning and migration policy
security policy and threat model
adapter certification checklist
```

media/stream schema 仍然是 v1 contract 内的 preview 部分。它已经覆盖 evidence 和 conformance checks，但在 adapter 成熟前，不应当被宣传为完全冻结的 media processing API。

release gate：

- critical runtime invariants 已文档化并被测试覆盖
- stable storage/blob adapter 通过 conformance tests
- high-risk tool flow 具备 audit、approval、ledger、replay、sandbox boundary
- 文档清晰区分 stable、preview、experimental、skeleton 和 roadmap features

## 多语言 Track

| Language | First milestone | Later milestone |
|---|---|---|
| Python | reference runtime | production runtime for Python users |
| TypeScript | protocol client and worker SDK | TS framework adapters |
| Rust | runtime primitives or sandbox worker | high-performance runtime engine |
| Go | worker/infra adapter | deployment-friendly worker/infra services |

所有语言实现都应以 `contracts/agentledger.runtime.v1.json` 和 conformance fixtures 为语义边界。
