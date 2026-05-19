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

Execution backend 定位见 `EXECUTION_BACKENDS.md`：Temporal、Ray、Kubernetes 是通用分布式执行 backend adapters，AgentLedger 保留 agent-specific runtime invariants。

这张范围地图也是 release gate 的一部分：新增能力要么作为生产执行可靠性 contract 进入 runtime-core，要么作为 optional adapter，要么作为独立 evidence consumer，要么明确写入 out of scope。默认选择应是 adapter 或外部 consumer，除非只有 runtime-core 才能强制保证对应 invariant。

Adapter 优先级见 `ADAPTER_ROADMAP.md`：生态成熟且边界能保持 AgentLedger invariant 时进入官方 adapter；否则保持 experimental 或 community-owned。

## v1.0.5 - Policy Engine Contract Upgrade

状态：已在 Python reference runtime-core 中作为向后兼容的 policy contract upgrade 实现。

目标：

```text
把裸 allow/deny policy check 升级成 normalized decision contract
当前仍以 ToolGateway 作为主要 enforcement point
保留简单 YAML/JSON role-capability policy
为未来 model、memory、output、media、sub-agent、multi-agent gate 预留结构
避免 runtime-core 变成 OPA、Cedar、DLP、eval 或治理后台
```

已实现：

```text
PolicyRequest: subject / action / resource / context / signals / runtime_state
PolicyDecision: effect / action_tier / risk_level / controls / reasons / findings / policy_version / delegation fields
PolicyFinding 和 PolicyControl
dependency-free 的 role capability、action boundary、runtime state evaluators
ToolGateway 接入，并在 tool_permission_decided 中记录完整 decision contract
PolicyEngine.check_tool(...) 保持兼容
为 child-agent/delegation context 预留 contract，但不实现 sub-agent execution
兼容 media/stream resource contract，但不实现 media processing adapters
Policy Engine 文档和 SVG 图
```

本版本明确不做：

```text
真实 OPA/Cedar adapters
prompt injection、PII、DLP 或 LLM safety providers
policy management UI 或多租户治理服务
sub-agent/multi-agent spawn/join runtime semantics
完整 media processing adapters
```

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

## Post-v1 - Sub-agent 与 Multi-agent Runtime Semantics

状态：roadmap。AgentLedger 不应该变成完整 multi-agent planner 或协作框架，但应该提供 sub-agent / multi-agent 执行关系的可靠 runtime primitives。

目标：

```text
让 parent / child agent run 具备 durable 和 replayable 语义
让 multi-agent execution evidence 可以跨 run 归因
orchestration / planning 仍交给 LangGraph、AutoGen、CrewAI、Temporal 或用户代码
```

计划中的 runtime-core primitives：

```text
parent_run_id / parent_step_id / child_run_id / child_role
agent_spawn_requested / agent_spawned / agent_joined / agent_spawn_failed
replay-safe join：读取历史 child evidence，而不是重复 spawn child work
child run cost/failure attribution 回到 parent run/step
parent cancellation propagation 到 child run，并 fence stale child worker
child run 的 policy / approval / sandbox / budget inheritance rules
parent/child evidence bundle links
child run creation、cancellation、failure propagation、replay-safe join 的 conformance fixtures
```

明确非目标：

```text
不重做 planner、debate system、voting system 或 autonomous multi-agent collaboration engine
不替代 LangGraph、AutoGen、CrewAI、Temporal、Ray 或 Kubernetes
不绕过 Tool Ledger、approval、sandbox 和 evidence pipeline 来隐藏 sub-agent side effects
```

退出标准：

- parent run 可以 spawn / join child run，并产生 durable evidence links
- child run 的 failure 和 cost 可以在 parent attribution report 中看到
- parent cancel 会 fence child worker 并记录 propagation evidence
- replay parent run 不会重复创建 child run 或重复 child side effects

Adapter 优先级见 `ADAPTER_ROADMAP.md`：生态成熟且边界能保持 AgentLedger invariant 时进入官方 adapter；否则保持 experimental 或 community-owned。

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

多语言计划不应阻塞 Python 版本继续稳定，但必须防止语义漂移。最终目标是 Python、Go、TypeScript、Rust 四种语言的 native runtime-core parity，而不是只提供 SDK-only packages。

| Language | First milestone | Runtime-ready milestone |
|---|---|---|
| Python | reference runtime | stable v1.0 runtime-core |
| Go | `go/` 下已有 preview runtime-core parity baseline，覆盖 lease/cancel、Tool Ledger、policy/approval/sandbox、cost/failure；下一步补 infra adapters | production adapters + worker/deployment hardening + packaged per-language conformance |
| TypeScript | `typescript/` 下已有 preview runtime-core parity baseline 和 `.d.ts`；下一步补 TS framework adapters | Node.js services 的 production adapters + framework integration + packaged per-language conformance |
| Rust | `rust/` 下已有 preview in-memory runtime-core parity baseline；下一步补 persistence/async/worker components | full runtime-core conformance 或 certified high-performance core subset |

过程：

1. Python 继续作为 reference implementation；
2. 冻结 shared contract、evidence fixtures 和 conformance fixtures；
3. 维护 Go、TypeScript、Rust 的 native runtime-core parity baselines，避免语义漂移；
4. framework、storage、sandbox、observability 等重依赖能力继续放在 adapter 层；
5. 只有当 stable language runtimes 都通过共享 conformance 后，才进入统一 release train。

达到 parity 前，非 Python 实现可以发布 0.x preview packages。达到 parity 后，runtime contract 变更必须同步更新各语言实现和 conformance 结果。

详见 `../MULTI_LANGUAGE.md` 和 `LANGUAGE_PARITY_MATRIX.md`。
