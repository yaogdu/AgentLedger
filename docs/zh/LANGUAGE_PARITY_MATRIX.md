# 多语言能力对齐矩阵

这份矩阵用于跟踪 AgentLedger 在不同语言实现之间的能力对齐状态。Python 是 v1.x reference runtime。Go、TypeScript、Rust 是 native runtime-core implementations，并由共享 parity gate 覆盖；provider-specific adapter 仍可以是 optional 或 preview。

关于 runtime-core、可跨语言 adapter、provider 差异、生态特定 framework adapter 和目录结构决策的完整四语言对比表，见 `zh/LANGUAGE_IMPLEMENTATION_COMPARISON.md`。

## 状态说明

| 状态 | 含义 |
|---|---|
| Stable | 已实现、已文档化、已测试，并属于 stable runtime-core contract。 |
| Parity | 已实现、已文档化，并由共享 runtime-core conformance 覆盖；Python 仍是 contract 演进的 reference。 |
| Preview | 已实现或已有骨架，但还不能作为 production-ready adapter 承诺。 |
| Planned | 属于该语言目标范围，但尚未实现。 |
| Optional | adapter 或 package 层能力，不要求进入最小 runtime core。 |
| Not core | 不应放入 runtime-core，应通过 adapter 或 evidence contract 对接。 |

## Runtime-core 对齐

| 能力 | Python | Go | TypeScript | Rust | runtime-ready 必需？ |
|---|---|---|---|---|---|
| AgentContext boundary | Stable | Parity | Parity | Parity | 是 |
| Runtime state machine | Stable | Parity | Parity | Parity | 是 |
| Run/session/step model | Stable | Parity | Parity | Parity | 是 |
| StateStore contract | Stable | Parity | Parity | Parity | 是 |
| Event log / WAL semantics | Stable | Parity | Parity | Parity | 是 |
| ToolGateway | Stable | Parity | Parity | Parity | 是 |
| Tool Ledger | Stable | Parity | Parity | Parity | 是 |
| Idempotent tool calls | Stable | Parity | Parity | Parity | 是 |
| Evidence export | Stable | Parity | Parity | Parity | 是 |
| Replay without side effects | Stable | Parity | Parity | Parity | 是 |
| Lease/fencing/recovery | Stable | Parity | Parity | Parity | 是 |
| Cancellation semantics | Stable | Parity | Parity | Parity | 是 |
| Error/failure propagation | Stable | Parity | Parity | Parity | 是 |
| Policy/approval hooks | Stable | Parity | Parity | Parity | 是 |
| Sandbox boundary semantics | Stable | Parity | Parity | Parity | 是 |
| Budget enforcement hooks | Stable | Parity | Parity | Parity | 是 |
| Cost attribution shape | Stable | Parity | Parity | Parity | 是 |
| Failure attribution shape | Stable | Parity | Parity | Parity | 是 |
| Contract validation/export | Stable | Parity | Parity | Parity | 是 |
| Shared conformance runner | Stable | Parity | Parity | Parity | 是 |

## Adapter 与生态对齐

| 能力 | Python | Go | TypeScript | Rust | core 要求？ |
|---|---|---|---|---|---|
| SQLite/local store | Stable | Parity | Parity | Parity | 推荐默认实现 |
| Postgres StateStore | Preview | Contract | Contract | Contract | Optional adapter |
| Local blob store | Stable | Parity | Parity | Parity | 推荐默认实现 |
| S3/MinIO BlobStore | Preview | Contract | Contract | Contract | Optional adapter |
| Framework facades | Stable facade | Contract | Contract | Contract | Optional adapter |
| MCP/tool/context mapping | Preview | Contract | Contract | Contract | Optional adapter |
| OpenTelemetry/OTLP export | Preview | Optional | Optional | Optional | Optional adapter |
| Docker/bubblewrap sandbox path | Preview | Optional | Optional | Optional | Optional adapter |
| Kubernetes/gVisor/Firecracker sandbox path | Planned | Optional | Optional | Optional | Optional adapter |
| Worker service | Stable local | Parity | Parity | Parity | Optional adapter |
| Static HTML debug export | Stable | Parity | Parity | Parity | Optional consumer |
| Media/stream artifact refs | Preview | Preview | Preview | Preview | Preview contract |
| Full media processing | Planned | Optional | Optional | Optional | Not core |
| Full eval platform | Not core | Not core | Not core | Not core | Not core |
| RAG/vector memory | Not core | Not core | Not core | Not core | Not core |

## 非 Python Runtime-core Baseline

`go/` module 现在已经实现 dependency-free runtime-core package：in-memory/JSON local store、run/step state machine、lease recovery、cancellation fencing、ToolGateway、Tool Ledger idempotency、evidence export、replay summary、policy denial、approval pause/resume、sandbox fail-closed、cost/budget records、model-call accounting 和 failure attribution。`typescript/` module 为 Node.js 实现同样的 runtime-core loop，并提供 `.d.ts` declarations。`rust/` module 也实现了 in-memory dependency-free runtime-core package，并支持 local snapshot persistence，用于同一套 runtime-core 语义。三个非 Python baseline 现在都会在测试中覆盖 `runtime_baseline.v1.json`、`local_persistence.v1.json`、`local_blob_store.v1.json`、`tool_schema_validation.v1.json`、`worker_service.v1.json`、`policy_approval_sandbox.v1.json`、`cost_failure_attribution.v1.json` 、`media_stream_artifacts.v1.json` 、`evidence_consumers.v1.json`、`static_debug_html.v1.json`、`ops_readiness.v1.json`、`storage_schema.v1.json`、`mcp_adapters.v1.json`、`framework_adapters.v1.json`、`otlp_trace_export.v1.json` 、`simple_api.v1.json` 和 `boundary_lint.v1.json`, `scheduler.v1.json`, `adversarial_review.v1.json`, `evidence_regression.v1.json`, `failure_injection.v1.json`, `shadow.v1.json`, `repro.v1.json`, `time_travel.v1.json`, `optional_adapters.v1.json`。`scripts/check_language_parity.py` 已提供可输出 JSON report 的 aggregate runner；非 Python runtime-core 已对齐；concrete production adapter packages 和完整 media processing/stream transport adapters 仍是可选后续工作；per-language CLI 已存在，并会执行对齐 fixture 的 semantic smokes：state/evidence/replay、local persistence/reopen、local blob store、tool schema validation、worker service、Tool Ledger retry、policy/approval/sandbox、cost/failure attribution 和 media/stream artifact refs, trace spans, evidence diff, divergence, debug summaries, static HTML debug export, ops readiness planning, storage schema helpers, MCP-style in-memory adapters, dependency-free framework adapters, OTLP JSON trace export, and the simple hello-world API。


本地可以用统一 runner 执行 Python reference、Go、TypeScript、Rust、contract diff、Markdown link 和 diff whitespace 检查：

```bash
/Users/duyaoguang/.local/bin/python3.11 scripts/check_language_parity.py
/Users/duyaoguang/.local/bin/python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

JSON report 会包含 Go、TypeScript、Rust 的 `language_conformance` 输出，并校验每个 runtime 都报告 `contracts/conformance/runtime_semantics.v1.json` 中定义的同一组 required semantic checks。

## Runtime-ready Gate

某个语言只有在实现所有必需 runtime-core 能力，并通过共享 conformance suite 后，才算 runtime-core ready。这个 gate 不代表每个 optional external adapter 都已经 production-hardened。

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

当前 runtime-core parity：

```text
Python 继续作为 reference implementation。
Go、TypeScript、Rust 在 packaging metadata、examples 和 CLI 检查通过后，按同一 runtime-core release train 发布。
packaging-only fix 可以有 patch version 差异，但 runtime-core conformance 必须保持通过。
SDK/client package 不能被描述成完整 runtime implementation。
```

后续 contract 变更：

```text
所有 stable language runtimes 进入统一 release train。
contract 变更需要同步实现和 conformance 更新。
breaking runtime semantics 需要新的 major contract version。
```

---

generated by codex cli
