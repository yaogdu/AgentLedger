# 路线图

本文是 `../ROADMAP.md` 的中文主路径版本。AgentLedger 按阶段演进，每个阶段先证明一个可靠性能力，再扩展更多表面积。

## 能力范围地图

为了避免 runtime 变得过大、过臃肿，每个大能力都拆成三层：core contract、optional adapter、explicit non-goal。runtime-core 只负责生产执行路径上的控制点、状态转换、evidence、replay hooks、CLI checks、conformance 和安全默认值；重依赖、离线批处理和部署相关选择留给 optional adapters 或独立工具。

路线原则是“薄但不可替代的 runtime core”：只内建那些不在 runtime boundary 内就无法可靠保证的能力。如果某一层业界已经有成熟系统，AgentLedger 应该提供 adapter contract 和 conformance suite，而不是重做那一层。

大部分能力都按三层判断：core contract、built-in minimal implementation、optional production adapter。最小内置实现保证开箱可用；生产 adapter 让用户接入成熟系统，同时不把重依赖塞进 core。

| 能力 | runtime-core 负责 | optional adapter 可负责 | core 明确不做 |
|---|---|---|---|
| Planning / Workflow | adapter contract、runtime-managed checkpoint、evidence hook、tool boundary integration | LangGraph、CrewAI、AutoGen、LangChain、Temporal、Prefect、Airflow、自定义 workflow adapter | 重新实现 planner、graph engine 或 workflow engine |
| Eval / Evidence Consumers | evidence export、replay、deterministic rerun hooks、最小 side-effect-free regression checks、conformance fixtures、eval-adapter output formats | Langfuse、Phoenix、promptfoo、DeepEval、Ragas、OpenAI Evals、LangSmith/Braintrust-style consumers、CI report sinks | standalone Eval Platform、跑 N 个 agent x M 个 case 的完整离线评测器、指标服务、case 管理、scorer 管理 UI 或长运行 eval Web 应用 |
| Tracing / Observability | structured events、trace JSONL、OTLP/JSON export、evidence links | OpenTelemetry SDK packages、collector recipes、external trace stores | 完整观测套件 |
| Guardrails | ToolSpec schema validation、policy checks、approval、pre/postcondition hooks、adversarial review gates | 更强 policy engine、项目规则包、外部 review 流程 | 业务治理后台 |
| Tool Gateway + Sandbox | ToolGateway、Tool Ledger、idempotency、audit、sandbox executor contract、fail-closed behavior | Docker、bubblewrap、Kubernetes/gVisor、E2B、Firecracker、自定义 executor | 外部 sandbox 基础设施托管 |
| Memory | session memory、short-term durable state、versioned memory refs、memory lifecycle events、projection、diff、audit lineage、replayable memory read/write | vector store、semantic retrieval、RAG、long-term knowledge store、Mem0/Zep/Letta 类 memory service | 完整 knowledge base、semantic retrieval system、user-profile memory 产品、chat summarizer 或 memory compression SDK |
| Session / HITL | run/session/step 状态机、approval request lifecycle、audit events | 外部人工 review 队列、chat/app integrations | 业务 review 后台或流程后台 |
| FinOps / Cost Control | token/call/cost records、budget enforcement hooks、cost attribution reports | provider price catalogs、finance exports、alerts | 发票或支付系统 |
| Inspector / Debug Viewer | stable read models、evidence export、static HTML debug export、redaction hooks、schema/version metadata | 独立 read-only 本地/内网 inspector package | deployment management service、runtime-core 中的写入/控制平面 |
| Runtime Model Evidence Boundary | model-call evidence、request/response archival、tool-call proposal、replay skipping、token/cost attribution、model failure evidence | provider SDK、LiteLLM/new-api/one-api/企业 gateway、policy packs、price catalogs | 变成 model router/gateway、打包所有 model SDK、替代 provider SDK 或外部 gateway |
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
| Model providers / gateways | OpenAI、Anthropic、Gemini、Bedrock、Ollama、LiteLLM、new-api、one-api、企业 gateway | 外部执行/路由；AgentLedger 记录 runtime model evidence、archived model response、proposed tool call、budget/failure/replay semantics |
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
Runtime Model Evidence Boundary：等 model evidence contract 稳定后进入 core
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
外部 model provider 和 gateway：OpenAI、Anthropic、Gemini、Bedrock、Ollama、LiteLLM/new-api/one-api 或企业 gateway 通过用户代码或 optional endpoint adapter 接入
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
LiteLLM、new-api、one-api 和企业 model gateway
vector databases, RAG systems, long-term memory systems
Langfuse、Phoenix、promptfoo、DeepEval、Ragas、OpenAI Evals、LangSmith、Braintrust 等 eval platform 和 benchmark runner
MCP tool servers and enterprise tool catalogs
WisePick-style routing advisor / capability router；仅作为候选方向，前提是后续评估证明这个边界有价值
```

AgentLedger 应该为这些层提供 adapter、export format、evidence bundle、trace correlation 和 conformance checks。

### 明确不进入范围的能力

这些会让项目过宽，或者变成另一个产品：

```text
complete agent workflow engine
standalone eval platform
complete Langfuse/LangSmith replacement
complete RAG or memory platform
complete sandbox infrastructure platform
deployment management service、billing、organization admin
第一版 inspector 中的 debug viewer write/control plane
tool marketplace or app store
```

### 1.4.2 之后的推荐实现顺序

1. 增加 framework-native examples 和 smoke fixtures，优先覆盖最常见接入路径：OpenAI Agents SDK、LangGraph package compatibility、LangChain/CrewAI/AutoGen facades，以及更丰富的 runtime-boundary examples。
2. 增加 Temporal bridge example 和 optional adapter boundary，明确边界：Temporal 管 workflow lifecycle 和 retry；AgentLedger 管 node 内部 tool/model/state reliability。
3. 继续改进 Inspector 作为 language-neutral companion：更好的 run-index filtering/search，以及面向不想在应用 runtime 安装 Python 的 Go/TypeScript/Rust 用户的 standalone viewer path。
4. 强化 observability 和 eval exports，不只停留在本地 JSON mapping：先补 OTLP deployment recipes，再做 Langfuse/Phoenix/promptfoo/DeepEval/Ragas/OpenAI-Evals/LangSmith-style evidence adapters，但不替代这些工具。
5. 继续做 production-pilot adapter hardening：Postgres、MySQL、S3/MinIO、worker、OTLP transport、sandbox packages 的真实服务 conformance、权限边界、backup/restore drill 和 failure semantics。
6. 在 model/tool/failure evidence 路径保持稳定后，启动 Runtime Memory Lifecycle baseline：memory refs、snapshot、read/write、diff、lineage、replay semantics 和 redaction hooks。
7. 增加 sub-agent/multi-agent runtime semantics，但只作为可靠性层：parent-child run link、spawn/join event、cancellation propagation、replay-safe join、cost/failure attribution。
8. 通过 optional processing adapters 扩展 media/stream，runtime-core 继续只保存 ref、metadata、lineage、checkpoint 和 replay validation。

## Open Source Adoption And Maintainer Workflow

这条路线不是新的 runtime feature line，也不改变 stable v1.x runtime-core contract。它的目标是让项目更容易被评估、采用、维护，并且更清晰地接入 Agent 生态。

定位：

```text
AgentLedger 是面向生产级 AI Agent 的早期开源 reliability and governance runtime layer。

它应该通过清晰 example、adapter contract、conformance check 和维护证据证明基础设施价值，
而不是过度宣称已有大规模生产采用。
```

推荐工作：

1. 增加聚焦的 OpenAI Agents SDK example，展示 runtime-managed tool call、approval gate、Tool Ledger record、model evidence、evidence export 和 replay-safe debugging flow。
2. 增加 Temporal bridge example，说明推荐边界：Temporal 管 workflow lifecycle 和 retry；AgentLedger 管 node 内部 tool/model/state reliability。
3. 增加面向非 Python 用户的 standalone Inspector adoption path：Docker image、单文件可执行程序、读取导出 evidence JSON 的静态 Web viewer，以及/或 Node/npm CLI/viewer package。
4. 增加 Codex-assisted maintainer workflow 文档或脚本，用于 issue triage、release checklist 准备、adapter conformance check、文档一致性和 changelog 草稿。
5. 持续维护 `OPEN_SOURCE_IMPACT.md`、`MAINTAINER_NOTES.md` 和 `USE_CASES.md`，作为公开解释生态价值、维护职责和实际采用场景的入口。
6. 收集真实使用证据，但不夸大：examples、discussions、issues、integration notes、package downloads、external demos 和 real-service hardening reports。

Adoption evidence 工作：

1. 持续维护四语言 3-minute side-effect safety demo，确保每次 release 后仍可运行。
2. 持续维护四语言 MCP governance example，后续方便和真实 MCP SDK integration 对比。
3. 录一个短 GIF 或 terminal screencast，展示 runtime path：`run -> tool call -> approval -> crash -> resume -> replay evidence`。
4. 写一篇技术文章，主题可以是 "Agents Need a Runtime, Not More Retries" 或 "Making AI Agents Durable, Auditable, and Replayable"。
5. README 开头继续聚焦用户痛点："Your agent called a tool. Did it happen? Can you retry safely? Can you prove it later?"
6. 创建公开 issue 或 discussion，覆盖后续 adoption tasks：OpenAI Agents SDK approval/replay example、standalone Inspector viewer、Temporal bridge example、tool-injection risk scanner、memory lifecycle design。
7. 发布一到两个真实 integration note 或 case study，例如用 AgentLedger 审计 legal agent 的 tool calls，但不包含私有数据。

Companion product 方向：

| 方向 | 为什么重要 | package boundary |
|---|---|---|
| AgentLedger Inspector | 通过 timeline、Tool Ledger、approval、replay diff、artifact、cost、failure attribution 让 run 可见 | 独立 read-only 本地/内网工具，不进入 runtime-core UI |
| Tool Governance / MCP Gateway | 在工具副作用发生前强制执行 schema、permission、approval、sandbox、audit、idempotency | optional gateway package 或 reference service |
| Eval adapters / Replay regression | 让团队基于历史 evidence 测试 prompt、model、tool-schema、agent-logic 变更，且不重复副作用 | 基于 evidence bundle 的 exporter 和 CLI/CI companion；不做 standalone eval platform |
| Production Harness Blueprint | 展示 AgentLedger 如何和 LangGraph/OpenAI Agents SDK、Temporal、Langfuse/OTel、MCP、Postgres/S3、Docker sandbox 组合 | examples、templates、deployment recipes |
| Agent Security Scanner | 检测 tool boundary bypass、危险 tool schema、缺失 approval/sandbox、secret exposure 和敏感 evidence artifacts | optional scanner command 或独立 package |

adoption 目标不是直接追 star，而是让项目在几分钟内可理解、可验证：没有 AgentLedger，用户很难在 agent 失败后判断发生了什么；有 AgentLedger，用户可以 inspect、resume、replay，并治理 tool side effects。

这里提到 OpenAI Agents SDK，含义是计划中的生态 example 和 adapter target；不代表 OpenAI 官方 partnership、endorsement、certification，也不代表已经完成 production integration。除非后续 release 明确记录了对应证据，否则不能这样宣传。

这条路线明确不做：

```text
没有证据前，不把 AgentLedger 描述成成熟大规模采用项目
不增加没有 example 或 conformance 支撑的 marketing-only claim
不把 repo 做成完整 harness product 或 standalone eval platform
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

候选后续 release trains：

```text
1.5.0  framework/Temporal adoption：OpenAI Agents SDK example、Temporal bridge、framework-native smoke fixtures；设计草案见 `FRAMEWORK_TEMPORAL_ADOPTION_DESIGN.md`
1.6.0  standalone Inspector and evidence consumer UX：非 Python viewer path、model-call panel、filtering/search
1.7.0  Runtime Memory Lifecycle：memory refs、snapshots、reads/writes、diffs、lineage、replay semantics
1.8.0  sub-agent/multi-agent runtime semantics：parent-child runs、spawn/join、cancellation/failure/cost attribution
1.9.0  media adapter release：frame/audio/video refs、transcription/embedding adapters、stream transports
1.x    production-pilot adapter hardening 在有真实服务证据时可用 patch/minor release 发布
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

## Post-v1 - Reliability Harness and Eval Adapters

目标：

```text
让 prompt / workflow / runtime 变更可测试
把 evidence 变成外部和本地检查的 regression input
把 AgentLedger evidence 接到成熟开源 eval 工具
```

当前 v1.1.0 local reliability path 已实现：

```text
evidence-regression machine-readable summary：failed checks、changed dimensions、changed counts、bundle-hash status、cost deltas
```

方向：

AgentLedger 不应该做 standalone Eval Platform。Eval platform 可以使用 AgentLedger，也可以完全不接 AgentLedger。runtime 应提供高质量 evidence 和 replay 输出，让成熟 eval 工具消费。

计划中的 adapter/export 工作：

```text
evidence bundle -> Langfuse dataset/score/experiment input
evidence bundle -> Phoenix dataset/experiment/eval-span input
evidence bundle -> promptfoo YAML/JSON test cases
evidence bundle -> DeepEval test cases and metrics input
evidence bundle -> Ragas dataset rows，用于 RAG/agent workflow eval
evidence bundle -> OpenAI Evals-style sample records
failure、policy、model、tool、cost evidence -> eval sample metadata
replay result -> CI gate 使用的 regression report input
```

本地 evidence consumer 继续增强：

```text
richer divergence reports
richer golden corpus UX
larger real-world benchmark corpus
cost/failure attribution regression reports
adversarial review policy packs
shadow mode comparison workflows
additional golden evidence fixtures
```

明确非目标：

```text
不在 AgentLedger 内做 dataset management、scorer management、leaderboard 或 experiment dashboard
不运行长生命周期 eval service 或 Web application
不替代 Langfuse、Phoenix、promptfoo、DeepEval、Ragas、OpenAI Evals、LangSmith、Braintrust 或自定义 CI 系统
不把离线 eval 分数宣传成在线 runtime safety；在线 policy enforcement 仍由 AgentLedger/policy engine 负责
```

## 1.4.0 - Agent Failure Lifecycle

状态：1.4.0 已作为 runtime-core baseline 在 Python、Go、TypeScript、Rust 四种语言中实现。AgentLedger 现在会记录和报告 runtime 拥有的 failure evidence，包括 worker crash、lease expiry、stale worker fencing、cancellation、retry exhaustion、policy denial、sandbox failure、tool/model/runtime failure、budget failure、unknown side-effect state 和 replay divergence。1.4.0 把它整理成可移植生命周期：classify、attribute、recover、inspect、regress、export。

范围：

```text
agent execution failure：只有 runtime boundary 才能可靠保证时，属于 runtime-core
agent answer-quality failure：属于 evidence consumer、eval tool 或 adapter，不直接塞进 runtime-core
```

1.4.0 已实现：

```text
runtime / agent / tool / model / policy / sandbox / budget / cancellation / retry 的 failure taxonomy
failure attribution report 和 cost/failure attribution records
crash、retry、lease fencing、cancellation fencing、side-effect safety 的 failure injection suite
evidence bundle 中包含 failed step、failure event、Tool Ledger state、cost record、approval/policy decision、artifact 和 replay ref
Inspector 和 static debug view 可以展示 failure event、risk flag、cost/failure record 和 event timeline
四语言 conformance 覆盖 failure injection、cost/failure attribution、scheduler recovery、cancellation、replay、shadow/evidence regression
稳定的 AgentFailure / FailureEnvelope read model：category、severity、recoverability、retryability、owner、causal refs、evidence refs
failure_detected / failure_classified / failure_recovery_scheduled / failure_recovered / failure_terminal / failure_regressed 等生命周期事件
把 model call、tool call、state commit、approval decision、sandbox run、worker lease 和 runtime evidence 串成 failure causal graph
failure replay plan：解释排查时能否复用 archived evidence，或者必须阻止 unsafe side-effect replay
failure regression analyzer：覆盖 recurring failure、fixed failure、新引入 failure
面向外部 observability、incident review、eval、support system 的 failure export format
terminal failure、unknown side-effect state、costly failure、unsafe replay block 的本地 alert records
Inspector failure panels：failure lifecycle、replay plan、alert records、causal graph、evidence links
```

后续 adapter / evidence-consumer 工作：

```text
更深入的 Langfuse / LangSmith / OpenTelemetry live exporter integrations，不只是本地 JSON mapping
Temporal / Ray / Kubernetes failure propagation recipes，保证外部 backend 中仍保留 AgentLedger failure evidence
eval adapter examples：在 Langfuse、Phoenix、promptfoo、DeepEval、Ragas 或 OpenAI Evals 这类工具中消费 AgentLedger evidence，用来识别 answer-quality failure、hallucination、policy miss、task-level correctness regression
alerting/report sinks：把本地 alert records 发送到具体外部系统
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

## Post-v1 - Runtime Memory Lifecycle

状态：roadmap。AgentLedger 不应该变成 memory 产品、vector database、RAG framework 或 memory compression SDK。runtime 只应该负责那些会影响 execution correctness、replay、audit、recovery 和 governance 的 memory 语义。

定位：

```text
Runtime Memory Lifecycle 的目标是让 memory 可解释、可审计、可 replay。

它记录 agent 读了什么 memory、写了什么 memory、某次 run 看到的是哪个
snapshot、projection 随时间如何变化，以及后续 replay 使用的是同一份
memory facts，还是读取了已经变化的外部状态。
```

为什么属于 runtime boundary：

```text
memory read 会影响 model decision、tool call、approval 和 cost
memory write 可能污染后续 run，也可能让 action 的原因变得不可追踪
replay 必须知道它是在复用历史 memory snapshot，还是重新读取可变外部状态
audit 必须回答哪些 memory facts 导致了某次 decision 或 side effect
```

Lossless 与可压缩边界：

```text
Lossless runtime state 不能被 summary 掉：
  current node、retry count、tool result、approval、checkpoint、
  ledger status、failure state、replay ref。

可压缩 context 应通过 adapter 外部化：
  chat history、observation、search result、reasoning note、
  retrieved passage、conversation summary。
```

这样 AgentLedger 仍聚焦 runtime evidence。Memory compression 可以有价值，但除非它会影响 replay、audit、recovery 或 governance guarantee，否则应该留在 adapter/evidence-consumer 层。

Runtime-core 目标：

```text
MemoryRef：稳定引用 runtime 可见的 memory entry、projection 和 snapshot
MemoryScope：run、session、agent、shared、external memory 边界
MemorySnapshot：某个 run、step、model call 或 tool call 可见的 memory 视图
MemoryReadEvent / MemoryWriteEvent：关联 run id、step id、model call、tool call、approval 和 policy decision
MemoryProjection：由 append-only event log 生成的 read model，例如 current task state、active constraints、known facts、tool retry state
MemoryDiff：识别 memory drift、pollution、deleted facts、changed constraints 和 replay divergence
MemoryAudit / lineage：解释哪些 memory facts 影响了 decision、tool call、approval 或 failure
memory ref / snapshot 的 retention 和 redaction policy hooks
replay semantics：可以冻结历史 memory snapshot，而不是重新查询可变外部 memory
```

最小内置实现：

```text
基于现有 StateStore / BlobStore / EventLog 的 dependency-free memory refs
evidence bundle 中导出 memory snapshot
从 runtime events 构建 materialized projection read model
对两个 snapshot 或两个 projection version 输出 diff command/report
Inspector 从 model/tool/failure record 链接回 memory refs
```

Optional adapter 层：

```text
Mem0、Zep、Letta、vector database、RAG system、knowledge store、企业 memory service
把外部 memory read/write 导入为 runtime-visible refs 的 adapter contract
capture retrieval output，让 RAG 结果可 replay、可 audit，但不让 AgentLedger 负责 retrieval
针对包含用户、客户或项目私密数据的 memory fields 做 redaction adapter
```

runtime-core 明确非目标：

```text
不做 vector database
不做 RAG framework
不做 user-profile memory 产品
不做通用 chat summarizer 或 context-compression SDK
不宣称 semantic memory 让 agent 更聪明；runtime 的主张是 replay、audit、governance 和 recovery
```

退出标准：

- run 可以记录每个关键 execution boundary 看到的 memory snapshot
- replay 可以复用 archived memory snapshot，或者明确报告将读取可变外部 memory
- Inspector/evidence 可以回答哪些 memory refs 影响了 model decision、tool side effect、approval 或 failure
- memory diff 可以识别两个 run 或两个 snapshot 之间的 changed facts、deleted facts、新增 constraints 和 drift
- 外部 memory 系统可以通过 adapter 接入，同时不绕过 evidence、policy、redaction 和 replay contract

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

`1.4.0` 已实现：

```text
agentledger.failure.envelope.v1 normalized failure read model
agentledger.failure.lifecycle.v1、agentledger.failure.causal_graph.v1、agentledger.failure.replay_plan.v1、agentledger.failure.regression.v1、agentledger.failure.alerts.v1、agentledger.failure.export.v1
agentledger failure report 输出 failure lifecycle 数据，agentledger failure export 输出 portable export
agentledger failure regress 提供 failure regression comparison
Inspector Failure Lifecycle、Failure Replay Plan、Failure Alerts、Failure Causal Graph panels
missing event payload、retry scheduling、pending approval、pending tool verification、blocked tool、unsafe replay planning、terminal failure report、export mappings、Inspector HTML rendering 的非 happy path 测试
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

## 1.4.1 - Runtime Model Evidence Boundary

状态：已作为小型 runtime-core evidence upgrade 实现。AgentLedger 不变成 model router、model gateway、provider SDK wrapper，也不替代 LiteLLM/new-api/one-api。runtime 只记录用户代码、Agent 框架、SDK 或外部 gateway 已经产生的 model evidence。

为什么属于 runtime boundary：

```text
model output 可能导致 tool call 和 side effect
model failure 可以解释 agent failure
model request/response 必须能在 replay 时复用，而不是重新调用 provider
model token/cost 需要按 run/step/agent attribution
model-proposed tool call 必须和 runtime-executed tool call 区分开
```

`1.4.1` 已实现：

```text
dependency-free agentledger.model.evidence.v1 evidence schema
Python、Go、TypeScript、Rust 中的 external model-call recording APIs
model_call_requested、model_call_completed、model_call_failed、tool_call_proposed events
Python reference runtime 中的 request/response/failure payload archival
外部 model call 的 token/USD cost attribution
model_call_failed 进入 failure envelope、lifecycle、alert、replay plan、Inspector timeline 和 adversarial review checks
非 Python runtime 中兼容旧 recordModelCall / record_model_call 风格
```

集成方式：

```text
user code / framework / provider SDK / model gateway
  -> 执行 model call
  -> 把 model evidence 记录进 AgentLedger
  -> model 可能提出 tool call proposal
  -> runtime 通过 ToolGateway / Tool Ledger 执行工具
```

LiteLLM、new-api、one-api、provider SDK 和企业 model gateway 都应视为外部系统。它们负责 routing、retry、timeout、key management、fallback 和 provider-specific compatibility。AgentLedger 负责最终的 runtime evidence、cost/failure attribution、replay behavior 和 tool proposal link。

明确非目标：

```text
runtime-core 不做 model routing 或 provider selection engine
除非未来证明有很窄的 evidence-only 边界，否则不做专门 LiteLLM/new-api/one-api adapter
不打包 provider SDK
不负责 provider timeout/retry/rate-limit execution policy
不声明 archived model output 能让模型本身 deterministic；runtime 只能 replay 已记录 evidence
```

后续工作：

```text
为高风险 model request、data-classification evidence 和 redaction decision 增加 optional policy hook
为不想在应用 runtime 安装 Python 的 Go/TypeScript/Rust 用户提供 standalone Inspector packaging
```

退出标准：

- 外部执行的 model call 可以被绑定到 run/step，并产生 replayable model evidence
- budget/cost attribution 能记录每次调用使用的 provider/model
- replay/debug 可以跳过真实 model call，读取 archived response 或明确报告缺少 archived evidence
- model routing 仍由外部 SDK/gateway/user code 负责，runtime-core 不依赖 provider SDK

## 1.4.2 - Model Evidence UX、Export 和 Boundary Lint 收敛

状态：已实现，作为四语言 1.4.x release train 发布，并强化 Python reference tooling。Runtime-core event semantics 仍在 Python、Go、TypeScript、Rust 中对齐；Inspector 和 boundary lint 仍是通过 Python reference package 分发的 companion/read-model tooling。

`1.4.2` 已实现：

- Inspector `Model Calls` panel，展示 archived request/response/failure refs、usage、cost、provider/model metadata 和 failure status
- Inspector `Tool Proposals` panel，展示 ToolGateway 执行前的 `tool_call_proposed` records
- 加强 model calls、proposed tool calls、runtime events、Tool Ledger rows 和 failure records 之间的 read-model links
- failure export 增加 model evidence refs 和 proposed-tool refs，面向 Langfuse、OpenTelemetry、LangSmith、Temporal-style consumers 和本地 CI
- boundary lint 加固：直接 database client、直接 filesystem mutation、model SDK bypass 和缺少 idempotency/approval/sandbox 的高风险 ToolSpec metadata
- dependency-free model evidence example，展示外部 gateway/provider 调用如何记录到 AgentLedger，而不是让 AgentLedger 负责 provider routing

明确非目标：

```text
runtime-core 不做 model gateway/router
不打包 provider SDK
不做 standalone eval platform
这个 patch 不重写 Go/TypeScript/Rust 原生 Inspector
```

退出标准：

- developer 打开 Inspector 后可以把 model-call evidence 和 tool execution evidence 分开看
- model-proposed tool call 可以在有 name/ref 的情况下关联到后续 ToolGateway/Tool Ledger record
- failure export 可以暴露 model evidence 和 proposed-tool refs，但不向第三方平台发送数据
- boundary lint 可以在运行前抓住常见 bypass，避免 runtime instrumentation 被业务代码绕开

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

---

generated by codex cli
