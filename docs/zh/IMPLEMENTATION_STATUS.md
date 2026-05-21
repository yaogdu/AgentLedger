# 实现状态

更新日期：2026-05-18

本文是 `../IMPLEMENTATION_STATUS.md` 的中文主路径版本，用来说明 Python reference runtime 已实现什么、哪些属于可选 adapter 或后续阶段、哪些不应该进入 runtime-core。

## 当前基线

AgentLedger 1.1.x 是 stable runtime-core line，Python 是 reference implementation，Go/TypeScript/Rust 已通过共享 runtime-core parity gate 覆盖；1.1.0 增加 normalized Policy Engine decision contract、adapter certification bundles 和更丰富的 evidence regression summaries，同时继续明确 concrete adapter path 中的 preview/experimental 边界。它适合：

- 本地使用
- runtime 设计评审
- framework adapter integration
- adapter 实验
- reliability semantics 验证
- 在明确 adapter 边界下做 production pilot 准备

版本范围说明：1.1.0 完成的是本地、dependency-free 的 P1/P3 gate slice：官方 adapter certification manifest 和机器可读 evidence regression summary。它不代表 exact optional adapter packages、framework-native smoke fixtures、production adapter hardening 或完整 richer reliability harness roadmap 已经全部完成。

runtime-core contract 已稳定。optional production adapter、外部基础设施加固和完整 eval 系统都不属于 stable core 边界；非 Python runtime-core baseline 由共享 parity gate 验证。

范围原则：runtime-core 要保持“薄但不可替代”。core 只负责那些不在 runtime boundary 内就无法可靠保证的能力；成熟的 planning、workflow、eval、observability、RAG、sandbox infrastructure 和 deployment 系统应通过 adapter 接入，或消费 evidence/replay 输出。

## 当前 Python 完成边界

对当前 1.1.x 目标来说，“stable runtime-core”指 Python reference runtime 已经可用、已文档化、已测试、可按 release gate 检查、contract 已冻结，并且 Go/TypeScript/Rust 已有 runtime-core parity gate。它不代表所有 optional production adapter 或外部 eval integration 已经在每种语言都发布。

包含在当前完成边界内：

- dependency-free local runtime 和 SDK
- durable state、event log、Tool Ledger、replay、evidence、normalized policy decision contract、approval、sandbox boundary、cost/failure attribution、worker loop、conformance
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
| Evidence regression primitives | side-effect-free evidence checks、`evidence-regression` media/stream gates、machine-readable regression summaries、adversarial review, evidence regression checklist、divergence report、golden corpus seed/add/list/check |
| Shadow mode | 使用归档 Tool Ledger response 做 side-effect-safe candidate run |
| Cost 与 budget | store-backed cost record、budget enforcement hook、按 run/agent/step/category/tool/model 的只读 cost attribution report |
| Approval 与 policy | approval request/approve/deny flow、YAML/JSON policy check、`PolicyRequest`、`PolicyDecision`、`PolicyFinding`、`PolicyControl`、built-in evaluator registry、`tool_permission_decided` 中的 decision evidence |
| 调度语义 | lease、fencing、heartbeat、cancellation、retry policy、failure taxonomy |
| Worker loop | local worker loop、process-shaped `WorkerService`、worker conformance runner |
| 存储 contract | `StateStoreProtocol`、`BlobStoreProtocol`、SQLite migration、DDL export |
| Adapter contract | framework adapter base、LangGraph facade、MCP tool/context mapping、dependency-free method facades |
| Sandbox boundary | fail-closed `none`、local executor、router、external executor contract、Docker/bubblewrap command path、Kubernetes dry-run/gated path |
| Observability | trace JSONL export、dependency-free OTLP JSON export、optional OTLP/JSON collector POST、evidence-linked audit record |
| Reliability checks | failure injection suite、failure attribution report、conformance runner、runtime-boundary lint, scheduler facade, adversarial review, evidence regression、JSON rule-pack extension |
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
| Framework support | LangGraph facade、LangChain/CrewAI/AutoGen/OpenAI Agents SDK/LlamaIndex/Semantic Kernel method facades、generic adapter base、examples、conformance fixtures、adapter certification bundles | 各框架 exact optional package 和 framework-native smoke fixture |
| Tool schema/catalog DX | dependency-free schema subset validation、output validation、AgentLedger manifest export、OpenAI function-tool export | framework-specific tool package adapter、optional full JSON Schema integration |
| MCP support | descriptor-to-ToolSpec mapping、dependency-free tool/context fixtures、context read tool adapter、examples | exact MCP SDK client/server integration |
| Sandbox | contract、local/fail-closed modes、Docker/bubblewrap command-style path、Kubernetes dry-run/gated execution、E2B/Firecracker slots | hardened isolation packages、secret injection policy、network policy recipe、resource limit validation |
| Retention/backup checks | non-destructive retention plan、compaction marker、backup readiness check | 保留 replay guarantees 的实际 compaction/snapshot job |
| Time travel/debug | JSON CLI timeline、state reconstruction、state diff、`debug --json`、`--include-diffs`、`--include-states`、static HTML export | 更丰富 report layout 和 artifact cross-links；core 不做长运行 Web 应用 |

## 剩余缺口与 Preview 区域

- 非 Python 实现：Go、Node/TypeScript、Rust 已在 `go/`、`typescript/`、`rust/` 下有 dependency-free preview runtime-core parity baseline。三者都会执行共享 runtime-core parity tests：`runtime_baseline.v1.json`、`local_persistence.v1.json`、`local_blob_store.v1.json`、`tool_schema_validation.v1.json`、`worker_service.v1.json`、`policy_approval_sandbox.v1.json`、`cost_failure_attribution.v1.json` 、`media_stream_artifacts.v1.json` 、`evidence_consumers.v1.json`、`static_debug_html.v1.json`、`ops_readiness.v1.json`、`storage_schema.v1.json`、`mcp_adapters.v1.json`、`framework_adapters.v1.json`、`otlp_trace_export.v1.json` 、`simple_api.v1.json` 和 `boundary_lint.v1.json`, `scheduler.v1.json`, `adversarial_review.v1.json`, `evidence_regression.v1.json`, `failure_injection.v1.json`, `shadow.v1.json`, `repro.v1.json`, `time_travel.v1.json`, `optional_adapters.v1.json`，覆盖 lease、cancellation、Tool Ledger idempotency、policy denial、approval pause/resume、sandbox fail-closed、cost/budget accounting、failure attribution、media/stream artifact refs, trace spans, evidence diff, divergence, debug summaries, static HTML debug export, ops readiness planning, storage schema helpers, MCP-style in-memory adapters, dependency-free framework adapters, OTLP JSON trace export, and the simple hello-world API 和 Rust local snapshot persistence；`scripts/check_language_parity.py` 可以输出 JSON parity report，并会读取 `contracts/conformance/runtime_semantics.v1.json` 作为 semantic-check authority，同时运行 Go、TypeScript、Rust 的 preview per-language conformance CLI，其中包含对齐 fixture 的 semantic smokes：state/evidence/replay、local persistence/reopen、local blob store、tool schema validation、worker service、Tool Ledger retry、policy/approval/sandbox、cost/failure attribution 和 media/stream artifact refs, trace spans, evidence diff, divergence, debug summaries, static HTML debug export, ops readiness planning, storage schema helpers, MCP-style in-memory adapters, dependency-free framework adapters, OTLP JSON trace export, and the simple hello-world API。剩余工作是 concrete production adapter packages、完整 media processing/stream transport adapters 和稳定发布级语言 package。SDK/client-only 可以先出现，但不算 runtime-ready。
- 生产级 Postgres 与 S3/MinIO rollout playbook，超出当前 CI-backed service conformance。
- hardened OpenTelemetry adapter package 和部署 recipe。
- 各 Agent 框架的 exact optional packages。
- exact MCP SDK client/server integration。
- 大规模真实 benchmark corpus；完整 eval 系统后续单独讨论。
- 完整 media processing adapters：image、audio、video、frame extraction、transcription、embedding、stream transport。
- production stream backpressure/cancellation adapters。
- stable v1.0 core contract 之外的 optional adapter production hardening。Postgres/S3/sandbox/worker/OTLP 的 production-ready 声明仍然需要真实服务、负载/并发检查，以及 restore 或 rollback drill；本地 certification manifest 会明确标记为 external-required。

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
2. 在不膨胀 core 的前提下改善 adoption：exact optional framework packages、framework-native smoke fixtures、runtime-boundary lint, scheduler facade, adversarial review, evidence regression examples。
3. 加固 production-pilot adapter path：Postgres、S3/MinIO、worker deployment、OTLP transport、non-destructive retention/backup checks。这类 P2 声明需要真实服务、负载/并发检查，以及 restore 或 rollback drill；本地 certification manifest 会明确标记为 external-required。
4. 更丰富的 external evidence consumer 和 eval adapter 放在 runtime-core 之外。
5. media/stream preview contracts 在 core reliability harness 稳定后，再进入 optional adapters。
