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
| Inspector / Debug Viewer | stable read models、evidence export、static HTML debug export、redaction hooks、schema/version metadata | 独立 read-only 本地/内网 inspector package | deployment management service、runtime-core 中的写入/控制平面 |
| Model Gateway / Router | model-call boundary、request/response archival、replay skipping、token/cost attribution、budget/fallback semantics | provider adapter、LiteLLM-style router adapter、policy packs、price catalogs | 打包所有 model SDK、变成完整 model gateway 产品、替代 provider SDK |
| Routing Advisor / Capability Router | 仅作为候选边界评估；目前不承诺成为 core feature。如果未来验证这个边界有价值，runtime 可以把外部传入的 route decision 作为 evidence 记录，并保持 replay 确定性 | 可能的 WisePick-style capability router adapter 或 feedback client；只有真实需求证明有价值时才考虑 | 在 core 里做 capability router、provider selection optimization，或把外部 routing decision 当成授权/幂等键 |

Execution backend 定位见 `EXECUTION_BACKENDS.md`：Temporal、Ray、Kubernetes 是通用分布式执行 backend adapters，AgentLedger 保留 agent-specific runtime invariants。

这张范围地图也是 release gate 的一部分：新增能力要么作为生产执行可靠性 contract 进入 runtime-core，要么作为 optional adapter，要么作为独立 evidence consumer，要么明确写入 out of scope。默认选择应是 adapter 或外部 consumer，除非只有 runtime-core 才能强制保证对应 invariant。

Adapter 优先级见 `ADAPTER_ROADMAP.md`：生态成熟且边界能保持 AgentLedger invariant 时进入官方 adapter；否则保持 experimental 或 community-owned。

## Agent Harness 定位

AgentLedger 不应该尝试做成完整 Agent Harness 产品。完整 Harness 会要求重新实现或深度拥有 workflow orchestration、trace UI、eval system、model gateway、context engine、sandbox infrastructure、tool hosting 和 enterprise governance。这些层已经有成熟或快速演进的生态，例如 LangGraph、Temporal、Langfuse、LangSmith、OpenTelemetry、LiteLLM、MCP、vector database、Kubernetes 和 sandbox provider。

AgentLedger 更窄，也更稳的定位是：

```text
AgentLedger is the reliability substrate for Agent Harness stacks.

It provides durable execution, tool/model governance, evidence, replay,
policy, sandbox boundaries, cost/failure attribution, and adapter contracts.

It integrates with LangGraph, Temporal, Langfuse, MCP, model providers,
storage backends, and sandbox systems instead of replacing them.
```

推荐 stack 定位：

| 层 | 示例系统 | AgentLedger 职责 |
|---|---|---|
| Workflow / planning | LangGraph、CrewAI、AutoGen、LangChain、自定义代码 | adapter boundary、checkpoint/evidence hooks、side-effect-safe node/tool execution |
| Durable workflow backend | Temporal、Ray、Kubernetes workers | agent-specific leases、fencing、cancellation、checkpoint、Tool Ledger、evidence、replay |
| Observability / eval UI | Langfuse、LangSmith、OpenTelemetry、custom dashboards | structured events、evidence bundles、trace/cost/failure export、correlation IDs |
| Tool and context protocols | MCP、internal tool servers、provider SDK tools | ToolGateway、Tool Ledger、schema validation、approval、sandbox、audit records |
| Model providers / routers | OpenAI、Anthropic、Gemini、Bedrock、Ollama、LiteLLM | ModelGateway contract、archived model responses、budget/fallback/replay semantics |
| Routing advisors / capability routers | WisePick-style decision service、自定义 capability router | 仅作为候选集成边界；没有已规划实现，除非后续真实使用证明需要 |
| Storage / artifacts | SQLite、Postgres、MySQL、S3/MinIO、internal stores | StateStore/BlobStore contracts、migration、conformance、evidence refs |

### 必须留在 runtime-core 的能力

这些能力必须进 core，因为只有 runtime execution path 才能可靠强制保证：

```text
ToolGateway / Tool Ledger / idempotency
StateStore / checkpoint / lease / fencing / cancellation
event log / evidence bundle / replay
policy / approval / sandbox contract
cost and failure attribution
conformance and adapter certification
ModelGateway contract：等 model boundary 设计稳定后进入 core
```

runtime-core 可以包含 dependency-free local defaults 和 protocol contracts，但不应该把 provider SDK、Web framework、cloud SDK 或 orchestration engine 强塞进 base package。

### 应该做成官方 optional packages 的能力

这些有价值，但要保持清晰 package boundary：

```text
agentledger-inspector：read-only local/internal debug viewer，展示 run timeline、state diff、Tool Ledger、cost/failure、evidence
agentledger-langgraph：LangGraph checkpointer/node integration
agentledger-mcp：MCP tool/context integration
agentledger-otel 和 Langfuse/LangSmith-style exporters：observability/evidence export
agentledger-temporal：Temporal execution-backend bridge
agentledger-model-* packages：OpenAI、Anthropic、Gemini、Bedrock、Ollama、LiteLLM-style provider/router adapters
agentledger-sandbox-* packages：Docker、Kubernetes、E2B、Firecracker/gVisor/bubblewrap 等
agentledger-postgres、agentledger-mysql、agentledger-s3：storage and artifact adapters
```

官方 optional package 必须保持 AgentLedger invariants；依赖、权限或 credential 缺失时 fail closed；并提供 conformance 或 injected-client tests。

### 只应该做 adapter / export / contract 的系统

这些系统应该集成，不应该重做：

```text
LangChain / CrewAI / AutoGen / OpenAI Agents SDK / LlamaIndex / Semantic Kernel
Langfuse / LangSmith / OpenTelemetry backends
Temporal / Ray / Kubernetes
LiteLLM and enterprise model gateways
vector databases, RAG systems, long-term memory systems
eval platforms and benchmark runners
MCP tool servers and enterprise tool catalogs
WisePick-style routing advisor / capability router；仅作为候选方向，前提是后续评估证明这个边界有价值
```

AgentLedger 应该为这些层提供 adapter、export format、evidence bundle、trace correlation 和 conformance checks。

### 明确不进入范围的能力

这些会让项目过宽，或者变成另一个产品：

```text
complete agent workflow engine
complete eval platform
complete Langfuse/LangSmith replacement
complete RAG or memory platform
complete sandbox infrastructure platform
deployment management service、billing、organization admin
第一版 inspector 中的 debug viewer write/control plane
tool marketplace or app store
```

### 推荐实现顺序

1. 发布 `agentledger-inspector`，作为 read-only evidence/runtime metadata consumer，读取 SQLite/Postgres/MySQL 和导出的 evidence bundle。
2. 强化 observability export：先 OTLP，再做 Langfuse/LangSmith-style evidence/trace exporter，但不替代这些工具。
3. 设计并实现 runtime-core 中的 `ModelGateway`/`ModelRouter` contract，使用 injected provider clients 和 replay-safe archived responses。
4. 增加 OpenAI、Anthropic、Gemini、Bedrock、Ollama、LiteLLM-style routing 的 optional model provider/router adapters。
5. 增加 Temporal bridge，并明确边界：Temporal 管 workflow lifecycle；AgentLedger 管 node 内部 tool/model/runtime safety。
6. 继续 harden storage、sandbox、MCP、tool 和 framework adapters：真实服务 conformance、权限边界、backup/restore 和 failure semantics。

## Open Source Adoption And Maintainer Workflow

这条路线不是新的 runtime feature line，也不改变 stable v1.x runtime-core contract。它的目标是让项目更容易被评估、采用、维护，并且更清晰地接入 Agent 生态。

定位：

```text
AgentLedger 是面向生产级 AI Agent 的早期开源 reliability and governance runtime layer。

它应该通过清晰 example、adapter contract、conformance check 和维护证据证明基础设施价值，
而不是过度宣称已有大规模生产采用。
```

推荐工作：

1. 增加聚焦的 OpenAI Agents SDK example，展示 runtime-managed tool call、approval gate、Tool Ledger record、evidence export 和 replay-safe debugging flow。
2. 增加 MCP governance example，展示 MCP-style tools 的 schema validation、permission check、approval-required tools、sandbox-required tools 和 audit evidence。
3. 增加 Temporal bridge example，说明推荐边界：Temporal 管 workflow lifecycle 和 retry；AgentLedger 管 node 内部 tool/model/state reliability。
4. 增加 Codex-assisted maintainer workflow 文档或脚本，用于 issue triage、release checklist 准备、adapter conformance check、文档一致性和 changelog 草稿。
5. 持续维护 `OPEN_SOURCE_IMPACT.md` 和 `MAINTAINER_NOTES.md`，作为公开解释生态价值和维护职责的入口。
6. 收集真实使用证据，但不夸大：examples、discussions、issues、integration notes、package downloads、external demos 和 real-service hardening reports。

Adoption evidence 工作：

1. 做一个 3-minute demo，命名为 "Prevent duplicate tool side effects in AI agents"：约 30 行代码加一个简短 README，展示 agent 失败重试时，由于 Tool Ledger 拥有 idempotency record，不会重复执行外部副作用。预期输出要展示 run id、一次外部副作用、一条 Tool Ledger 记录，以及 replay/evidence 命令。
2. 录一个短 GIF 或 terminal screencast，展示 runtime path：`run -> tool call -> approval -> crash -> resume -> replay evidence`。
3. 写一篇技术文章，主题可以是 "Agents Need a Runtime, Not More Retries" 或 "Making AI Agents Durable, Auditable, and Replayable"。
4. README 开头继续聚焦用户痛点："Your agent called a tool. Did it happen? Can you retry safely? Can you prove it later?"
5. 创建公开 issue 或 discussion，覆盖后续 adoption tasks：OpenAI Agents SDK approval/replay example、MCP tool governance example、Inspector prototype、Temporal bridge example、tool-injection risk scanner。
6. 发布一到两个真实 integration note 或 case study，例如用 AgentLedger 审计 legal agent 的 tool calls，但不包含私有数据。

Companion product 方向：

| 方向 | 为什么重要 | package boundary |
|---|---|---|
| AgentLedger Inspector | 通过 timeline、Tool Ledger、approval、replay diff、artifact、cost、failure attribution 让 run 可见 | 独立 read-only 本地/内网工具，不进入 runtime-core UI |
| Tool Governance / MCP Gateway | 在工具副作用发生前强制执行 schema、permission、approval、sandbox、audit、idempotency | optional gateway package 或 reference service |
| Replay / Regression Lab | 让团队基于历史 evidence 测试 prompt、model、tool-schema、agent-logic 变更，且不重复副作用 | 基于 evidence bundle 的 CLI 和 CI companion |
| Production Harness Blueprint | 展示 AgentLedger 如何和 LangGraph/OpenAI Agents SDK、Temporal、Langfuse/OTel、MCP、Postgres/S3、Docker sandbox 组合 | examples、templates、deployment recipes |
| Agent Security Scanner | 检测 tool boundary bypass、危险 tool schema、缺失 approval/sandbox、secret exposure 和敏感 evidence artifacts | optional scanner command 或独立 package |

adoption 目标不是直接追 star，而是让项目在几分钟内可理解、可验证：没有 AgentLedger，用户很难在 agent 失败后判断发生了什么；有 AgentLedger，用户可以 inspect、resume、replay，并治理 tool side effects。

这里提到 OpenAI Agents SDK，含义是计划中的生态 example 和 adapter target；不代表 OpenAI 官方 partnership、endorsement、certification，也不代表已经完成 production integration。除非后续 release 明确记录了对应证据，否则不能这样宣传。

这条路线明确不做：

```text
没有证据前，不把 AgentLedger 描述成成熟大规模采用项目
不增加没有 example 或 conformance 支撑的 marketing-only claim
不把 repo 做成 完整 harness product 或 eval platform
不把 secret、私有客户信息或公司内部实现细节写进公开文档
```

## v1.3.0 - Language-neutral Inspector Release

状态：已作为 read-only evidence/runtime metadata consumer 实现，不改变 runtime-core 执行语义。

已实现：

- 增加 `agentledger inspector run`，可读取 SQLite、Postgres、MySQL runtime metadata
- 增加 `agentledger inspector evidence`，可读取导出的 evidence bundle 文件或目录
- 增加 `agentledger.inspector.v1` 稳定 read model，覆盖 run timeline、Tool Ledger、approval、policy decision、cost/failure record、artifact 和 risk flag
- 增加静态 HTML Inspector export，用于本地或内网 debug
- 增加 read-only SQLite store 和 read-only local blob store helper；Postgres/MySQL 文档要求使用只读 DB credential
- 增加 optional `agentledger-inspector` companion package 和用于自定义 data source/renderer 的 extension API
- 中英文文档说明 DB connection、evidence input、static HTML output 和 extension boundary

明确不包含：

- approval、deny、cancel、ledger edit、database mutation 等写入/控制平面动作
- permission/user/organization management
- 长运行 Web application
- 替代 Langfuse、LangSmith、OpenTelemetry 或 eval platform
- Inspector package 内置 remote blob service integration

后续工作：

- 基于 Inspector read model 的 evidence-driven replay/regression lab
- 如果保持 read-only 且依赖隔离，再考虑 optional local/internal web viewer

## v1.2.4 - Adoption And Short Demo Release

状态：已作为 adoption/example release 实现，不改变 runtime-core 语义。

已实现：

- 增加四语言 3-minute side-effect safety demo，展示 crash/retry 后不会重复外部写入
- 增加四语言 MCP governance example，把 descriptor annotations 映射到 policy、approval、sandbox metadata、idempotency 和 audit evidence
- 强化 README 第一屏，直接说明 tool side-effect safety 问题
- 增加 adoption planning 文档、公开 issue/discussion 候选清单和 legal-agent case-study 模板
- 将 package metadata 和当前 install examples 更新到 1.2.4 release train

明确不包含：

- 改变 stable runtime-core contract
- 声明 OpenAI Agents SDK 或 MCP 官方 endorsement
- 实现 Inspector、Replay Lab 或 Security Scanner companion products
- 在没有真实服务证据时声明 optional adapters production-hardened

## v1.2.3 - Query Documentation And Langfuse Adapter Boundary

状态：已作为小型 adapter/documentation release 实现，不改变 runtime-core 语义。

已实现：

- 增加 SQL 查询示例，覆盖单表 runtime inspection、多表 timeline、approval、cost、artifact，以及大规模业务 schema 的关联方式
- 增加 `agentledger-langfuse` 作为官方可选 observability adapter boundary
- 为 Langfuse-style evidence/trace payload export 增加 TypeScript subpath/package、Go adapter boundary、Rust crate/feature boundary
- 更新 adapter packaging、certification、optional-adapter conformance 和文档入口
- 将本地 runtime state 文件移出版本控制

明确不包含：

- 替代 Langfuse 或实现完整 observability backend
- 让 runtime-core 绑定 Langfuse SDK
- 对某个 Langfuse server ingestion endpoint 做生产验证

## v1.2.2 - MySQL Adapter Boundary Release

状态：已实现，定位为 storage adapter boundary release。本版本延续 `1.2.x` adapter packaging 模型，不改变 runtime-core 语义。

已实现：

- 在 Python、Go、TypeScript、Rust 的 storage schema helper 中增加 MySQL DDL/migration metadata
- 增加 Python `MySQLStore` / `MySQLStoreConfig`，通过 optional `pymysql` 依赖启用，并支持 CLI migration/status
- 增加 `agentledger-mysql` Python package、TypeScript npm package boundary、Go `go/adapters/mysql`、Rust `agentledger-mysql` crate boundary
- 增加 MySQL 的跨语言 optional adapter 与 official adapter conformance token
- 文档中明确 MySQL 是官方 optional adapter boundary，不是 production-hardening 声明

本版本明确不做：

```text
没有真实服务证据时，不声明 MySQL production-ready
不做 live MySQL concurrency/load/backup/restore gate
不把非 Python native MySQL driver 放进 core；Go/TypeScript/Rust 暴露 injected SQL adapter contract
```

## v1.2.1 - Adapter Packaging Release

状态：已在 `v1.2.1` 分支实现，定位为 adapter packaging 与边界版本。本版本把已有 adapter seam 打包成清晰的 optional package，不改变 runtime-core 语义。

为什么先做拆包，再做 reliability/media/sub-agent 增强：

```text
先冻结 core-vs-adapter 边界，再继续扩大能力表面积
保持 runtime-core dependency-light
让重依赖生态按自己的节奏发布
让后续 reliability hardening 落在对应 adapter 包里
避免 runtime-core 变成 optional integration 大合集
```

已实现：

- 创建 `packages/` workspace，承载官方 Python adapter packages
- 增加第一批 Python adapter packages：`agentledger-postgres`、`agentledger-s3`、`agentledger-langgraph`、`agentledger-mcp`、`agentledger-otel`、`agentledger-sandbox-docker`
- 增加 TypeScript subpath exports，以及 `typescript/packages/` 下的 npm adapter packages
- 增加 Go adapter import subpackages：`go/adapters/`
- 增加 Rust adapter features 与 `rust/crates/` 下的 crate packages
- 给 core 增加 extras，用户不用记独立包名也能安装能力：
  - `agentledger-runtime[postgres]`
  - `agentledger-runtime[s3]`
  - `agentledger-runtime[langgraph]`
  - `agentledger-runtime[mcp]`
  - `agentledger-runtime[otel]`
  - `agentledger-runtime[docker]`
  - `agentledger-runtime[all]`
- core 保留当前 Python adapter module 的 backwards-compatible import shim
- 每个 adapter package 都有 README、example/readme 或 package entry point，并有本地 smoke 覆盖
- 增加中英文 adapter package 文档
- adapter package 尽量使用 optional dependency、facade export 和 injected client，避免引入不必要重依赖

本版本明确不做：

```text
没有真实服务证据时，不声明 Postgres/S3/sandbox/worker/OTLP production-ready
不做所有 agent framework 的完整 native version matrix
不做完整 MCP SDK server/client 覆盖
不做 Temporal/Ray/Kubernetes scheduler backend adapters
不做 audio/video/frame/transcription/embedding 的 media processing adapters
不做 sub-agent 或 multi-agent runtime semantics
不做 长运行 UI 或完整 eval platform
```

已验证 release gates：

```text
scripts/check_adapter_packages.py
Python unittest suite
Go tests including adapter subpackages
TypeScript tests and syntax checks including adapter subpath exports
Rust tests with adapters-all
cross-language parity script with markdown link and diff checks
complete core parity/package dry-run script
```

后续版本：

```text
1.2.x  adapter packaging fixes、framework-native smoke、package docs polish
1.3.0  language-neutral Inspector：read-only DB/evidence consumer 和 static HTML debug report
1.3.x  richer Inspector/report UX、redaction、evidence-driven replay/regression lab
1.4.0  sub-agent/multi-agent runtime semantics：parent-child runs、spawn/join、cancellation/failure/cost attribution
1.5.0  media adapter release：frame/audio/video refs、transcription/embedding adapters、stream transports
1.6.0  ModelGateway/ModelRouter contract：ctx.call_model、model events、provider injection、fallback/budget/replay semantics
1.6.x  optional model provider/router adapters，继续保持在 runtime-core 之外
```

## v1.1.0 - Adapter Certification And Reliability Gate Upgrade

状态：已在 Python reference runtime-core 中作为向后兼容的 policy、adapter certification 和 evidence regression upgrade 实现。

目标：

```text
把裸 allow/deny policy check 升级成 normalized decision contract
当前仍以 ToolGateway 作为主要 enforcement point
保留简单 YAML/JSON role-capability policy
为未来 model、memory、output、media、sub-agent、multi-agent gate 预留结构
把官方 adapter 的期望沉淀为机器可读 certification bundle
让 evidence regression 输出更适合 CI 和 release gate 消费
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
agentledger adapter certify 官方 adapter certification bundle
Postgres / S3 / MCP / Docker / OTEL / LangGraph / Temporal 内置 certification profile
依赖真实基础设施的 adapter path 明确标记 production_validation.status=external-required
evidence-regression metadata summary：failed checks、changed dimensions、changed counts、bundle-hash status、cost delta
```

本版本明确不做：

```text
真实 OPA/Cedar adapters
prompt injection、PII、DLP 或 LLM safety providers
policy management UI 或governance backend
sub-agent/multi-agent spawn/join runtime semantics
完整 media processing adapters
没有真实服务凭证、并发/负载检查、restore 或 rollback drill 时，不声明 P2 类 production hardening 完成
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
official adapter profile certification bundles
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

当前 v1.1.0 local reliability path 已实现：

```text
evidence-regression machine-readable summary：failed checks、changed dimensions、changed counts、bundle-hash status、cost deltas
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

## Post-v1 - Agent Failure Lifecycle

状态：部分已实现。AgentLedger 现在已经会记录和报告 runtime 拥有的 failure evidence，包括 worker crash、lease expiry、stale worker fencing、cancellation、retry exhaustion、policy denial、sandbox failure、tool/model/runtime failure、budget failure 和 replay divergence。后续应该把它整理成更清晰的生命周期：classify、attribute、recover、inspect、regress、export。

范围：

```text
agent execution failure：只有 runtime boundary 才能可靠保证时，属于 runtime-core
agent answer-quality failure：属于 evidence consumer、eval tool 或 adapter，不直接塞进 runtime-core
```

当前已实现：

```text
runtime / agent / tool / model / policy / sandbox / budget / cancellation / retry 的 failure taxonomy
failure attribution report 和 cost/failure attribution records
crash、retry、lease fencing、cancellation fencing、side-effect safety 的 failure injection suite
evidence bundle 中包含 failed step、failure event、Tool Ledger state、cost record、approval/policy decision、artifact 和 replay ref
Inspector 和 static debug view 可以展示 failure event、risk flag、cost/failure record 和 event timeline
四语言 conformance 覆盖 failure injection、cost/failure attribution、scheduler recovery、cancellation、replay、shadow/evidence regression
```

计划中的 runtime-core 工作：

```text
稳定的 AgentFailure / FailureEnvelope read model：category、severity、recoverability、retryability、owner、causal refs、evidence refs
failure_detected / failure_classified / failure_recovery_scheduled / failure_recovered / failure_terminal / failure_regressed 等生命周期事件
更丰富的 recovery policy metadata：retry budget、backoff、manual approval required、sandbox escalation、alternate tool/model fallback、terminal stop reason
把 model call、tool call、state commit、approval decision、sandbox run、worker lease、child-agent run 串成 failure causal graph
failure replay mode：复现 evidence path，但不重复不安全副作用
failure regression fixtures：覆盖 recurring failure、fixed failure、新引入 failure
面向外部 observability、incident review、eval、support system 的 failure export format
Inspector failure panels：failure timeline、root-cause candidates、recovery attempts、retry/fallback history、evidence links
```

计划中的 adapter / evidence-consumer 工作：

```text
Langfuse / LangSmith / OpenTelemetry failure export mappings
Temporal / Ray / Kubernetes failure propagation recipes，保证外部 backend 中仍保留 AgentLedger failure evidence
eval adapter examples：消费 AgentLedger evidence 来识别 answer-quality failure、hallucination、policy miss、task-level correctness regression
alerting/report sinks：重复 terminal failure、高成本 failure loop、replay divergence、side-effect unknown state
```

runtime-core 明确非目标：

```text
不做完整 incident-management system
不做完整 eval 或 LLM-judge platform
不宣称 runtime failure attribution 能证明答案正确
不在缺少 Tool Ledger、approval、sandbox、replay evidence 的情况下自动重试不安全副作用
不把外部 framework 或 backend failure 从 evidence bundle 中隐藏掉
```

退出标准：

- 每个 terminal run failure 都有 normalized failure envelope 和 causal evidence refs
- recoverable failure 可以 retry 或 resume，且不会重复 side effect
- replay 可以解释历史 failure 是否会再次调用外部系统，还是复用 archived evidence
- Inspector 可以展示 failure timeline，并链接到相关 model/tool/state/policy/sandbox records
- 外部 eval 或 observability 系统可以消费 failure evidence，而不需要读取未文档化 runtime tables

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

## Post-v1 - Inspector Evolution

状态：`1.3.0` 已部分实现。当前 Inspector 是 read-only evidence/runtime metadata consumer，支持静态 HTML export。后续能力仍应留在 optional package 中，并且不改变 runtime-core 执行语义。

包名：

```text
agentledger-inspector
后续 package 名只有在保持 read-only consumer 边界时再考虑
```

推荐定位：

```text
read-only local/internal web inspector
AgentLedger runtime metadata 的 debug / audit UI
StateStore、BlobStore、evidence bundle、static debug export 的消费者
```

目标：

```text
不用直接读数据库行，也能检查 AgentLedger run history
把 replay/debug/cost/failure 命令已经暴露的 evidence 可视化
runtime-core 不引入 Web framework 依赖
权限和安全成熟前，不做写操作或控制平面
```

`1.3.0` 已实现：

```text
read-only SQLite runtime database input
通过文档化 adapter boundary 读取 Postgres / MySQL runtime database
跨语言 evidence-bundle input
static HTML export，用于离线 debug 分享
Tool Ledger、approval、policy decision、cost/failure、artifact、timeline read model
```

`1.3.2` 已实现：

```text
JSON 和 static HTML 输出的可配置 Inspector redaction policy
CLI 支持 --redact-key、--redaction-policy 和 --redaction-replacement
给自定义 read-model consumer 使用的 InspectorRedactionPolicy API
```

`1.3.3` 已实现：

```text
timeline、step、Tool Ledger、approval、policy、artifact row 的稳定 read-model anchor
相关 runtime record 之间的 static HTML section navigation 和内部 cross-link
```

`1.3.5` 已实现：

```text
JSON 和 static HTML report 中的 chronological Event Stream
只读 run index：status、timestamp、cost summary、failure summary、可选单 run 链接
event/timeline row 中的 runtime run id 和提取出的 agent run id
run list static HTML 分页，以及 Inspector、evidence、time-travel 表格中的全宽 JSON/details 行
```

后续工作：

```text
只读 run index 的 filtering、search、pagination、saved views
面向非 Python 用户的 standalone Inspector distribution：Docker image、单文件可执行程序、读取导出 evidence JSON 的静态 Web viewer，以及/或 Node/npm CLI/viewer package
单个 run timeline：step、event、model call、tool call、approval、artifact、checkpoint
state diff 和 state-version view
Tool Ledger view：idempotency key、causal token、side-effect status、request/response refs、unknown-state handling
artifact/evidence browser：payload refs、blob hashes、media refs、stream checkpoint refs
cost / failure attribution panels
prompt、大 blob 和项目自定义 evidence field 的更丰富 redaction preset
读取数据库前做 schema/version compatibility check
```

明确非目标：

```text
第一版不修改 runtime state、不做 approval/deny、不 cancel run、不编辑 ledger rows
不替代 LangSmith、Langfuse、OpenTelemetry backend 或 eval platform
不绕过 evidence/replay/export contracts，只依赖未文档化内部实现
```

退出标准：

- 开发者可以把 inspector 指向本地 `.agentledger/state.db`，查看 run timeline、state diff、Tool Ledger、cost、failure 和 artifacts
- 同一个 package 可以通过文档化 schema/version check 读取 Postgres/MySQL
- UI 作为本地/内网 debug 工具可用，不需要额外应用后台
- Go、TypeScript、Rust 用户不需要把 Python package 安装进自己的应用运行时，也能消费官方 Inspector viewer
- 敏感字段默认脱敏，或可以显式配置脱敏策略

## Post-v1 - Model Gateway 与 Router

状态：roadmap。它属于 runtime boundary 能力，但具体 model provider 和 routing engine 应该保持为 optional adapters。

为什么属于 runtime boundary：

```text
model call 会影响 cost、latency、replay、evidence、determinism 和 policy
runtime 是能记录 selected provider/model，并在 replay 时跳过真实 model call 的层
budget enforcement 和 fallback semantics 需要在 model call 前后都可见
```

Core contract 目标：

```text
ctx.call_model(...) 或各语言等价 API
ModelGateway contract：request validation、provider selection、execution、archival、replay
ModelRouterPolicy contract：按 task、model family、cost、latency、context size、data policy、allowed providers rule-based routing
model_call_requested / model_route_selected / model_call_completed / model_call_failed / model_call_replayed events
evidence bundle 中记录 request/response refs，并支持 redaction 和 payload hashing
按 run、step、agent role、provider、model 做 token/cost attribution
昂贵 model call 前做 in-flight budget enforcement
timeout、rate limit、policy denial、budget exceeded、provider failure、malformed output 的 fallback/failure taxonomy
replay 时复用 archived model response，不再次调用 provider
shadow model comparison hook，可以比较 model/provider 输出，但不产生 tool side effect
```

Adapter 层计划：

```text
OpenAI、Anthropic、Gemini、Bedrock、Azure OpenAI、Ollama、本地 inference server provider adapters
LiteLLM-style adapter，用于已经集中管理 provider routing 的团队
provider price catalog adapters，放在 runtime-core 外
org-specific model allowlist、region/data rules、high-risk model approval policy adapters
```

最小第一版：

```text
dependency-free ModelGateway interface
injected provider client，用于测试和用户应用接线
rule-based YAML/JSON router policy
model-call event/evidence/cost records
replay 返回 archived model output
runtime-core 不强依赖 provider SDK
```

明确非目标：

```text
把所有 model provider SDK 打包进 runtime-core
替代 OpenAI、Anthropic、Gemini、Bedrock、Ollama、LiteLLM 或企业 model gateway
做完整 model marketplace、billing system、prompt management platform 或 managed router
声明模型行为本身 deterministic；runtime 只能保证 archived-response replay
```

退出标准：

- agent code 可以通过 runtime boundary 调 model，并产生 replayable model evidence
- budget/cost attribution 能记录每次调用选择的 provider/model
- replay 可以跳过真实 model call，返回 archived response
- provider routing 可配置，同时 runtime-core 不依赖 provider SDK

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
