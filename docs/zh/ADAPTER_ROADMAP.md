# Adapter 路线图

[English](../ADAPTER_ROADMAP.md) | [中文](ADAPTER_ROADMAP.md)

AgentLedger 的 runtime-core 要保持薄：core 负责 invariant、contract、event、evidence、replay、policy 和 fail-closed 行为。具体生态集成应该在目标生态足够成熟、边界足够稳定时，作为 optional adapter 发布。

## 决策规则

满足多数条件时，adapter 应该做成官方支持：

- 该生态被 Agent/LLM 生产团队广泛使用。
- 集成边界足够稳定，不需要每个版本追内部实现。
- adapter 能保持 AgentLedger invariant：durable state、Tool Ledger、policy、audit、evidence、replay 和 failure semantics。
- 依赖太重或太部署相关，不适合进入 runtime-core。
- adapter 能通过 conformance test 或 injected-client test 验证，不要求 core CI 连接真实云账号。

下面情况应该保持 community/experimental：

- 上游 SDK 不稳定，或主要是私有/内部接口。
- 集成需要用户自己掌控的强 opinionated infra。
- runtime 只能暴露安全边界，无法保证真实后端行为。
- adapter 会迫使 core 变成 workflow engine、eval platform、SaaS platform 或 deployment product。

## 优先级 1：官方 Adapter

这些应该作为 first-class optional package，因为它们对应常见生产需求，且 runtime 边界清晰。

| 领域 | Adapter | 为什么重要 | Core 已有 contract | 预期 package 形态 |
| --- | --- | --- | --- | --- |
| Storage | Postgres StateStore | 企业 pilot 通常需要服务端 durable state、locking、migration 和 backup workflow。 | `storage_schema.v1.json`、local persistence semantics、`optional_adapters.v1.json` | `agentledger-postgres` / 各语言原生 package |
| Blob store | S3 / MinIO BlobStore | Evidence bundle、media ref、stream checkpoint 和 artifact 需要低成本 durable object storage。 | `local_blob_store.v1.json`、content-addressed refs、`optional_adapters.v1.json` | `agentledger-s3` / 各语言原生 package |
| Framework | LangGraph | 与 stateful agent workflow 高度重合；AgentLedger 补 Tool Ledger、evidence、replay、policy 和 adapter certification。 | `framework_adapters.v1.json`、checkpoint boundary、optional capability descriptor | `agentledger-langgraph` |
| Tool/context protocol | MCP transport | MCP 很适合作为 agent tool/context 边界。Runtime 应治理 MCP tool，但不拥有所有 tool server。 | `mcp_adapters.v1.json`、`optional_adapters.v1.json` | `agentledger-mcp` |
| Observability | OpenTelemetry exporter/transport | 企业需要把 trace 接到现有可观测系统。 | `otlp_trace_export.v1.json` | `agentledger-otel` |
| Sandbox | Docker sandbox | 常见本地/团队 isolation backend，适合在 Kubernetes/gVisor/Firecracker 之前落地。 | `policy_approval_sandbox.v1.json`、sandbox policy/result boundary | `agentledger-sandbox-docker` |
| Scheduler/backend | Temporal bridge | Temporal 可以负责 durable workflow orchestration，AgentLedger 负责 agent-specific evidence/tool/state semantics。 | `scheduler.v1.json`、execution backend boundary | `agentledger-temporal` |

## 优先级 2：推荐 Adapter

这些有价值，但应排在优先级 1 之后，或先保持较薄 facade，等需求明确后再稳定。

| 领域 | Adapter | 原因 | 备注 |
| --- | --- | --- | --- |
| Framework | LangChain Runnable | 使用广，callable 边界相对通用。 | 保持薄封装，避免依赖 LangChain 内部实现。 |
| Framework | CrewAI | role-based team 常见，但 AgentLedger 不应继承其 orchestration model。 | 只包 run/kickoff surface。 |
| Framework | AutoGen | 对 multi-agent conversation 有用，但 API 代际差异较大。 | 稳定声明前先做 adapter certification。 |
| Framework | OpenAI Agents SDK | 适合 OpenAI-native 团队。 | 跟随官方 SDK surface，不重复实现 SDK 语义。 |
| Framework | LlamaIndex | 适合 RAG/knowledge-agent workload。 | Runtime 治理 tool/evidence，不拥有 retrieval。 |
| Framework | Semantic Kernel | 在 .NET/企业环境有意义。 | 等 .NET runtime/package 出现时更重要。 |
| Sandbox | Kubernetes Job sandbox | 适合集群用户的生产边界。 | 支持 dry-run manifest、namespace/service account policy 和 optional runtimeClass。 |
| Sandbox | E2B | 适合托管 remote sandbox 的 code/tool execution。 | 保持 optional remote executor adapter。 |
| Distributed execution | Ray bridge | 适合 Python distributed worker pool。 | Ray 管 cluster scheduling；AgentLedger 管 run semantics。 |
| Deployment | Kubernetes worker recipe | 对 pilot 有用。 | 先做 recipe/Helm/example，不急着做完整 platform。 |

## 优先级 3：Experimental 或 Community Adapter

这些不应该阻塞 core parity 或官方 release claim。

| 领域 | Adapter | 为什么暂不 first-class |
| --- | --- | --- |
| Sandbox | gVisor | 通常通过 Kubernetes/container runtime config 使用，而不是直接 app SDK。 |
| Sandbox | Firecracker | 能力强但 infra-heavy，通常由平台层托管。 |
| Sandbox | bubblewrap | Linux local 有用，但对 macOS/Windows 团队不够通用。 |
| Workflow | Airflow / Prefect / Argo | 它们是 batch/workflow 系统；可以桥接，但 AgentLedger 不应变成通用 workflow engine。 |
| Eval | LangSmith / Braintrust / custom eval platforms | Eval 是 evidence/replay contract 的消费者，不属于 runtime-core。 |
| Vector DB / RAG | Pinecone、Weaviate、Milvus、pgvector 等 | Long-term memory/retrieval infra 应外置；runtime 存 ref/evidence，不拥有知识检索逻辑。 |
| SaaS/multi-tenant platform | 任意 hosted platform adapter | 当前项目范围外。AgentLedger 是 framework/library/runtime，不是 SaaS。 |

## 跨语言策略

Python 是 reference implementation，但官方 adapter 在生态存在时应尽量向 Go、TypeScript、Rust 收敛。

| Adapter 类型 | Python | Go | TypeScript | Rust | 策略 |
| --- | --- | --- | --- | --- | --- |
| Runtime-core local defaults | 必须 | 必须 | 必须 | 必须 | 必须持续对齐。 |
| Postgres | 官方必做 | 官方必做 | 官方必做 | 官方必做 | 各语言都有成熟 client。 |
| S3 / MinIO | 官方必做 | 官方必做 | 官方必做 | 官方必做 | 各语言都有成熟 client。 |
| LangGraph | Python 官方必做 | 生态不存在则不做 | 生态不存在则不做 | 生态不存在则不做 | 上游生态存在的语言才做官方。 |
| LangChain | 推荐 | community/optional | 推荐 | community/optional | API 稳定且使用广时再官方。 |
| MCP transport | 官方必做 | 官方必做 | 官方必做 | 官方必做 | 协议级 adapter 适合所有语言。 |
| Docker sandbox | 官方必做 | 官方必做 | 官方必做 | 官方必做 | CLI/runtime boundary 基本语言无关。 |
| Kubernetes sandbox/backend | 推荐 | 推荐 | 推荐 | 推荐 | 优先 manifest/dry-run contract，再 optional execution。 |
| Temporal bridge | 推荐 | Go runtime 成熟后必做 | 推荐 | community/optional | 按各语言 Temporal 生态强度决定。 |
| OpenTelemetry | 官方必做 | 官方必做 | 官方必做 | 官方必做 | 企业可观测标准路径。 |

## 官方 Adapter 的硬性要求

每个官方 adapter 必须提供：

- 清晰 package boundary，runtime-core 不强依赖。
- 配置脱敏和安全默认值。
- credentials、client、binary 或权限缺失时 fail closed。
- 使用 injected client 或 local fixture 的 conformance tests。
- 对 adapter call、failure、retry 和 external ref 记录 evidence。
- 上游 SDK 版本兼容说明。
- 中英文文档。

## 推荐实现顺序

1. Python、Go、TypeScript、Rust 的 Postgres 和 S3/MinIO adapter。
2. Python、Go、TypeScript、Rust 的 MCP transport adapter。
3. Python、Go、TypeScript、Rust 的 Docker sandbox adapter。
4. Python、Go、TypeScript、Rust 的 OpenTelemetry transport adapter。
5. LangGraph 官方 Python adapter package 和 certification examples。
6. 在生态稳定处补 LangChain / CrewAI / AutoGen / OpenAI Agents SDK / LlamaIndex / Semantic Kernel facade。
7. Kubernetes sandbox/backend recipe，然后再做 optional execution adapter。
8. 根据真实用户需求做 Temporal/Ray/Kubernetes scheduler/backend bridge。
