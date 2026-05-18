# 多语言能力对齐矩阵

这份矩阵用于跟踪 AgentLedger 在不同语言实现之间的能力对齐状态。Python 是当前 v1.0 reference runtime。Go、TypeScript、Rust 是 native runtime implementations；SDK/client-only 阶段可以先出现，但不能算 runtime parity。

关于 runtime-core、可跨语言 adapter、provider 差异、Python-only 生态 adapter 和目录结构决策的完整四语言对比表，见 `zh/LANGUAGE_IMPLEMENTATION_COMPARISON.md`。

## 状态说明

| 状态 | 含义 |
|---|---|
| Stable | 已实现、已文档化、已测试，并属于 stable runtime-core contract。 |
| Preview | 已实现或已有骨架，但还不能作为 runtime-ready 承诺。 |
| Planned | 属于该语言目标范围，但尚未实现。 |
| Optional | adapter 或 package 层能力，不要求进入最小 runtime core。 |
| Not core | 不应放入 runtime-core，应通过 adapter 或 evidence contract 对接。 |

## Runtime-core 对齐

| 能力 | Python | Go | TypeScript | Rust | runtime-ready 必需？ |
|---|---|---|---|---|---|
| AgentContext boundary | Stable | Preview | Preview | Preview | 是 |
| Runtime state machine | Stable | Preview | Preview | Preview | 是 |
| Run/session/step model | Stable | Preview | Preview | Preview | 是 |
| StateStore contract | Stable | Preview | Preview | Preview | 是 |
| Event log / WAL semantics | Stable | Preview | Preview | Preview | 是 |
| ToolGateway | Stable | Preview | Preview | Preview | 是 |
| Tool Ledger | Stable | Preview | Preview | Preview | 是 |
| Idempotent tool calls | Stable | Preview | Preview | Preview | 是 |
| Evidence export | Stable | Preview | Preview | Preview | 是 |
| Replay without side effects | Stable | Preview | Preview | Preview | 是 |
| Lease/fencing/recovery | Stable | Preview | Preview | Preview | 是 |
| Cancellation semantics | Stable | Preview | Preview | Preview | 是 |
| Error/failure propagation | Stable | Preview | Preview | Preview | 是 |
| Policy/approval hooks | Stable | Preview | Preview | Preview | 是 |
| Sandbox boundary semantics | Stable | Preview | Preview | Preview | 是 |
| Budget enforcement hooks | Stable | Preview | Preview | Preview | 是 |
| Cost attribution shape | Stable | Preview | Preview | Preview | 是 |
| Failure attribution shape | Stable | Preview | Preview | Preview | 是 |
| Contract validation/export | Stable | Preview | Preview | Preview | 是 |
| Shared conformance runner | Stable | Preview | Preview | Preview | 是 |

## Adapter 与生态对齐

| 能力 | Python | Go | TypeScript | Rust | core 要求？ |
|---|---|---|---|---|---|
| SQLite/local store | Stable | Preview | Preview | Preview | 推荐默认实现 |
| Postgres StateStore | Preview | Planned | Planned | Optional | Optional adapter |
| Local blob store | Stable | Planned | Planned | Planned | 推荐默认实现 |
| S3/MinIO BlobStore | Preview | Planned | Optional | Optional | Optional adapter |
| Framework facades | Stable facade | Optional | Planned | Optional | Optional adapter |
| MCP/tool/context mapping | Preview | Optional | Planned | Optional | Optional adapter |
| OpenTelemetry/OTLP export | Preview | Optional | Optional | Optional | Optional adapter |
| Docker/bubblewrap sandbox path | Preview | Optional | Optional | Optional | Optional adapter |
| Kubernetes/gVisor/Firecracker sandbox path | Planned | Optional | Optional | Optional | Optional adapter |
| Worker service | Stable local | Preview | Preview | Preview | Optional adapter |
| Static HTML debug export | Stable | Optional | Optional | Optional | Optional consumer |
| Media/stream artifact refs | Preview | Preview | Preview | Preview | Preview contract |
| Full media processing | Planned | Optional | Optional | Optional | Not core |
| Full eval platform | Not core | Not core | Not core | Not core | Not core |
| RAG/vector memory | Not core | Not core | Not core | Not core | Not core |

## Go Preview Baseline

`go/` module 现在已经实现 dependency-free runtime-core package：in-memory/JSON local store、run/step state machine、lease recovery、cancellation fencing、ToolGateway、Tool Ledger idempotency、evidence export、replay summary、policy denial、approval pause/resume、sandbox fail-closed、cost/budget records、model-call accounting 和 failure attribution。`typescript/` module 为 Node.js 实现同样的 runtime-core loop，并提供 `.d.ts` declarations。`rust/` module 也实现了 in-memory dependency-free runtime-core package，并支持 local snapshot persistence，用于同一套 runtime-core 语义。三个非 Python baseline 现在都会在测试中覆盖 `runtime_baseline.v1.json`、`local_persistence.v1.json`、`local_blob_store.v1.json`、`tool_schema_validation.v1.json`、`worker_service.v1.json`、`policy_approval_sandbox.v1.json`、`cost_failure_attribution.v1.json` 、`media_stream_artifacts.v1.json` 、`evidence_consumers.v1.json`、`static_debug_html.v1.json`、`ops_readiness.v1.json`、`storage_schema.v1.json`、`mcp_adapters.v1.json`、`framework_adapters.v1.json`、`otlp_trace_export.v1.json` 、`simple_api.v1.json` 和 `boundary_lint.v1.json`, `scheduler.v1.json`, `adversarial_review.v1.json`, `evidence_regression.v1.json`, `failure_injection.v1.json`, `shadow.v1.json`, `repro.v1.json`, `time_travel.v1.json`, `optional_adapters.v1.json`。`scripts/check_language_parity.py` 已提供可输出 JSON report 的 aggregate runner；非 Python runtime-core 已对齐；concrete production adapter packages 和完整 media processing/stream transport adapters 仍是可选后续工作；per-language CLI 已存在，并会执行对齐 fixture 的 semantic smokes：state/evidence/replay、local persistence/reopen、local blob store、tool schema validation、worker service、Tool Ledger retry、policy/approval/sandbox、cost/failure attribution 和 media/stream artifact refs, trace spans, evidence diff, divergence, debug summaries, static HTML debug export, ops readiness planning, storage schema helpers, MCP-style in-memory adapters, dependency-free framework adapters, OTLP JSON trace export, and the simple hello-world API。


本地可以用统一 runner 执行 Python reference、Go、TypeScript、Rust、contract diff、Markdown link 和 diff whitespace 检查：

```bash
/Users/duyaoguang/.local/bin/python3.11 scripts/check_language_parity.py
/Users/duyaoguang/.local/bin/python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

JSON report 会包含 Go、TypeScript、Rust 的 `language_conformance` 输出，并校验每个 runtime 都报告 `contracts/conformance/runtime_semantics.v1.json` 中定义的同一组 required semantic checks。

## Runtime-ready Gate

某个语言只有在实现所有必需 runtime-core 能力，并通过共享 conformance suite 后，才算 runtime-ready。

最小 gate：

```text
contract JSON compatibility passes
event/evidence golden fixtures pass
StateStore conformance passes
Tool Ledger idempotency passes
tool schema validation passes
worker service semantics pass
lease/fencing/recovery passes
cancellation semantics pass
replay side-effect blocking passes
policy/approval/sandbox fail-closed checks pass
cost/failure attribution fixture checks pass
media/stream artifact ref fixture checks pass
```

## 发布策略

达到 parity 前：

```text
Python 使用 stable releases。
Go、TypeScript、Rust 在 packaging metadata、examples 和 CLI parity 验证后，应发布同一 release train 的 runtime-core packages。packaging-only fix 可以有 patch version 差异，但 runtime-core conformance 必须保持通过。
SDK/client package 不能被描述成完整 runtime implementation。
```

达到 parity 后：

```text
所有 stable language runtimes 进入统一 release train。
contract 变更需要同步实现和 conformance 更新。
breaking runtime semantics 需要新的 major contract version。
```
