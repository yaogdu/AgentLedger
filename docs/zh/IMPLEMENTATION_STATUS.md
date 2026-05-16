# 实现状态

更新日期：2026-05-16

本文是 `../IMPLEMENTATION_STATUS.md` 的中文主路径版本，用来说明 Python reference runtime 已实现什么、哪些属于可选 adapter 或后续阶段、哪些不应该进入 runtime-core。

## 当前基线

当前 Python 实现是 v1.0 stable runtime-core release，并带有部分 preview/experimental adapter path。它适合：

- 本地使用
- runtime 设计评审
- framework adapter integration
- adapter 实验
- reliability semantics 验证
- 在明确 adapter 边界下做 production pilot 准备

runtime-core contract 已稳定。optional production adapter、外部基础设施加固、非 Python 实现和完整 eval 系统都不属于 stable core 边界。

范围原则：runtime-core 要保持“薄但不可替代”。core 只负责那些不在 runtime boundary 内就无法可靠保证的能力；成熟的 planning、workflow、eval、observability、RAG、sandbox infrastructure 和 deployment 系统应通过 adapter 接入，或消费 evidence/replay 输出。

## 当前 Python 完成边界

对当前目标来说，“v1.0 stable Python 版本”指 Python runtime-core 已经作为 reference implementation 达到可用、已文档化、已测试、可按 release gate 检查，并且 contract 已冻结的状态。它不代表所有 optional production adapter、外部 eval integration 或未来其它语言实现都已经完成。

包含在当前完成边界内：

- dependency-free local runtime 和 SDK
- durable state、event log、Tool Ledger、replay、evidence、policy、approval、sandbox boundary、cost/failure attribution、worker loop、conformance
- local storage、local blob、simple policy、local/fail-closed sandbox、JSONL/OTLP JSON trace、static debug export 的最小内置实现
- framework、storage、blob、MCP、sandbox、observability、media/stream、worker seams 的 adapter contracts 和 dependency-free facades
- 中英文主路径文档、SVG 架构图、使用指南、发布检查清单和 runtime contract export

不包含在当前完成边界内：

- 非 Python 实现
- 各框架 exact native optional packages
- 完整外部 eval 系统
- production-hardened infrastructure adapters 和 rollout playbooks
- v1.0 core contract 之外的 optional adapter production hardening

## 已实现

| 领域 | 当前状态 |
|---|---|
| 本地 durable runtime | SQLite WAL store、local blob store、event log、Tool Ledger、AgentContext、Runtime、ToolGateway |
| 简单接入 API | `agent`、`run`、`arun`、`RunResult`、hello-world example |
| Replay 与 evidence | event-level replay、evidence export、evidence directory layout、静态 HTML evidence report、evidence diff |
| Evidence regression primitives | side-effect-free evidence checks、`evidence-regression` media/stream gates、adversarial review checklist、divergence report、golden corpus seed/add/list/check |
| Shadow mode | 使用归档 Tool Ledger response 做 side-effect-safe candidate run |
| Cost 与 budget | store-backed cost record、budget enforcement hook、按 run/agent/step/category/tool/model 的只读 cost attribution report |
| Approval 与 policy | approval request/approve/deny flow、YAML/JSON policy check |
| 调度语义 | lease、fencing、heartbeat、cancellation、retry policy、failure taxonomy |
| Worker loop | local worker loop、process-shaped `WorkerService`、worker conformance runner |
| 存储 contract | `StateStoreProtocol`、`BlobStoreProtocol`、SQLite migration、DDL export |
| Adapter contract | framework adapter base、LangGraph facade、MCP tool/context mapping、dependency-free method facades |
| Sandbox boundary | fail-closed `none`、local executor、router、external executor contract、Docker/bubblewrap command path、Kubernetes dry-run/gated path |
| Observability | trace JSONL export、dependency-free OTLP JSON export、optional OTLP/JSON collector POST、evidence-linked audit record |
| Reliability checks | failure injection suite、failure attribution report、conformance runner、runtime-boundary lint、JSON rule-pack extension |
| Media/stream contracts | `MediaArtifact`、`MediaMetadata`、`ArtifactLineage`、`StreamChunkRef`、`EventStreamCheckpoint`、AgentContext helpers、tool schema conventions、evidence/replay validation |
| 开源发布骨架 | CI workflow、changelog、security policy、versioning policy、release checklist、contributor checks、中英文文档入口、SVG 架构图、adapter certification checklist |

## 部分实现

这些能力已有 Python 路径或 preview contract，但生产级成熟度依赖后续 adapter、服务演练或兼容性加固：

| 领域 | 已有内容 | 后续内容 |
|---|---|---|
| Postgres StateStore | DDL、optional psycopg adapter、env/CLI config、migration status/apply、schema isolation、JSONB、injected conformance、CI service conformance | production rollout、operational tuning、真实服务 backup/restore 演练 |
| S3/MinIO BlobStore | optional boto3 adapter、env/CLI config、injected conformance、CLI smoke、CI service conformance | IAM/KMS/lifecycle review、大对象指南、运维加固 |
| OpenTelemetry | dependency-free OTLP JSON file export、optional OTLP/JSON collector POST | deployment recipe、hardened adapter package |
| Distributed workers | local worker loop、`WorkerService`、worker conformance、Postgres `FOR UPDATE SKIP LOCKED` path、deployment guide | supervision example、真实服务 load/concurrency validation |
| Framework support | LangGraph facade、LangChain/CrewAI/AutoGen/OpenAI Agents SDK/LlamaIndex/Semantic Kernel method facades、generic adapter base、examples、conformance fixtures | 各框架 exact optional package 和 framework-native smoke fixture |
| Tool schema/catalog DX | dependency-free schema subset validation、output validation、AgentLedger manifest export、OpenAI function-tool export | framework-specific tool package adapter、optional full JSON Schema integration |
| MCP support | descriptor-to-ToolSpec mapping、dependency-free tool/context fixtures、context read tool adapter、examples | exact MCP SDK client/server integration |
| Sandbox | contract、local/fail-closed modes、Docker/bubblewrap command-style path、Kubernetes dry-run/gated execution、E2B/Firecracker slots | hardened isolation packages、secret injection policy、network policy recipe、resource limit validation |
| Retention/backup checks | non-destructive retention plan、compaction marker、backup readiness check | 保留 replay guarantees 的实际 compaction/snapshot job |
| Time travel/debug | JSON CLI timeline、state reconstruction、state diff、`debug --json`、`--include-diffs`、`--include-states`、static HTML export | 更丰富 report layout 和 artifact cross-links；core 不做长运行 Web 应用 |

## 尚未实现或不作为当前 Python core 阻塞项

- 非 Python 实现：TypeScript SDK、Rust primitives/runtime parts、Go worker/infra adapters。
- 生产级 Postgres 与 S3/MinIO rollout playbook，超出当前 CI-backed service conformance。
- hardened OpenTelemetry adapter package 和部署 recipe。
- 各 Agent 框架的 exact optional packages。
- exact MCP SDK client/server integration。
- 大规模真实 benchmark corpus；完整 eval 系统后续单独讨论。
- 完整 media processing adapters：image、audio、video、frame extraction、transcription、embedding、stream transport。
- production stream backpressure/cancellation adapters。
- stable v1.0 core contract 之外的 optional adapter production hardening。

## Runtime-core 非目标

以下内容不应进入 runtime-core：

- 业务数据 schema
- 应用特定 identity、commerce 或 domain workflow
- 长运行 Web 应用
- 针对用户数据的 database drop/truncate/reset helper
- cloud resource provisioning
- 替代 Agent 框架、workflow engine、Ray、Temporal 或 Kubernetes

runtime-core 应暴露 durable contracts、conformance suites、adapter seams、CLI tools 和 safe defaults。后端具体执行、生产部署策略和重依赖应放到 optional package 或用户自定义 adapter。

## 下一步顺序

1. 继续用 release gates、contract snapshot 和 conformance suite 保护 v1.0 runtime-core compatibility。
2. 在不膨胀 core 的前提下改善 adoption：exact optional framework packages、framework-native smoke fixtures、runtime-boundary lint examples。
3. 加固 production-pilot adapter path：Postgres、S3/MinIO、worker deployment、OTLP transport、non-destructive retention/backup checks。
4. 更丰富的 external evidence consumer 和 eval adapter 放在 runtime-core 之外。
5. media/stream preview contracts 在 core reliability harness 稳定后，再进入 optional adapters。
