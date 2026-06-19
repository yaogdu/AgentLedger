# 多语言对标审计

[English](../LANGUAGE_PARITY_AUDIT.md) | [中文](LANGUAGE_PARITY_AUDIT.md)

本文是当前目标的 completion audit checklist：**Go、TypeScript、Rust 需要在 AgentLedger 声明 native runtime parity 的范围内对标 Python 实现**。它避免只因为测试是绿的，就误判成“完整对标”。

## 成功标准

AgentLedger 使用三层 parity：

| 层级 | 含义 | 完成规则 |
| --- | --- | --- |
| Runtime-core parity | 该语言可以原生执行同一套可靠性、安全、evidence、replay、scheduler、tool、policy 和 adapter-boundary 语义。 | 必须由 `contracts/conformance/runtime_semantics.v1.json`、各语言 conformance CLI、单测、`scripts/check_language_parity.py` 和 module audit 覆盖。 |
| Optional adapter boundary parity | 该语言暴露同样的 backend/framework 扩展边界，但 core 不引入重 SDK。 | 必须由 `optional_adapters.v1.json` 表达，并在未安装/未注入具体 adapter 时 fail closed。 |
| Concrete adapter parity | 某语言真的提供 Postgres、S3、Docker、LangGraph、MCP transport 等 live adapter。 | 属于可选 package/module，不是 runtime-core parity 的必要条件，除非 release 明确声明支持该具体 adapter。 |

当前 parity claim 只有在每个 Python public capability 都满足下面之一时才算完成：

1. 已在 Go、TypeScript、Rust 实现并验证；
2. 已表示为 optional adapter boundary 或 out-of-core contract；
3. 已明确排除在 runtime-core parity 之外。

## Prompt-To-Artifact Checklist

| 要求 | 当前证据 | 覆盖强度 | 状态 |
| --- | --- | --- | --- |
| 多语言共享 contract | `contracts/agentledger.runtime.v1.json`、`src/agentledger/contract.py`、parity runner 的 contract diff | 强 | 已覆盖 |
| 语义 manifest | `contracts/conformance/runtime_semantics.v1.json` | 强 | 已覆盖 |
| 聚合验证器 | `scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json` | 对已列出的 checks 强 | 已覆盖 |
| 保守 module audit | `scripts/audit_python_parity.py` | 对 Python module 到 evidence 的映射强 | 已覆盖，zero gaps |
| Go native runtime baseline | `go/`、`go/cmd/agentledger-go/main.go`、`go test ./...`、Go conformance JSON | 对已列出的 checks 强 | runtime-core 已覆盖 |
| TypeScript native runtime baseline | `typescript/`、`npm test`、`npm run check`、TS conformance JSON | 对已列出的 checks 强 | runtime-core 已覆盖 |
| Rust native runtime baseline | `rust/`、`cargo test`、Rust conformance JSON | 对已列出的 checks 强 | runtime-core 已覆盖 |
| 最小 hello-world API | Python `simple.py`、Go `SimpleRun`、TS `simpleRun`、Rust `simple_run`、`simple_api.v1.json` | 强 | 已覆盖 |
| Scheduler facade | Python/Go/TS/Rust `RuntimeScheduler`、`scheduler.v1.json` | 对 runtime-owned status/recovery/cancel facade 强 | 已覆盖 |
| Evidence/replay/debug | Python evidence/replay/trace/diff/time travel；Go/TS/Rust 对应能力；`evidence_consumers.v1.json`、`static_debug_html.v1.json`、`time_travel.v1.json` | 对 portable evidence consumers 和 static debug artifact 强 | 已覆盖 |
| Reliability harness | Python review/eval/repro/failure injection/shadow；Go/TS/Rust 对应能力；`adversarial_review.v1.json`、`evidence_regression.v1.json`、`failure_injection.v1.json`、`shadow.v1.json`、`repro.v1.json` | 对 side-effect-free runtime evidence checks 强；外部 eval platform 仍属 out of core | 已覆盖 |
| Storage | Python SQLite/Postgres；Go JSON local；TS JSON local；Rust memory/snapshot local；`local_persistence.v1.json`、`storage_schema.v1.json`、`optional_adapters.v1.json` | local durable semantics 和 Postgres schema/adapter boundary 强；live driver 是 optional adapter | runtime-core 已覆盖 |
| Blob stores | Python local/S3；Go/TS/Rust local；`local_blob_store.v1.json`、`optional_adapters.v1.json` | local content-addressed semantics 和 S3 adapter boundary 强；live S3 client 是 optional adapter | runtime-core 已覆盖 |
| Sandbox | Python local/disabled/Docker/E2B/bubblewrap/Kubernetes/gVisor/Firecracker/remote；Go/TS/Rust fail-closed boundary；`policy_approval_sandbox.v1.json`、`optional_adapters.v1.json` | runtime boundary 和 optional backend descriptors 强 | runtime-core 已覆盖 |
| Framework adapters | Python base/function/method/LangGraph 和 framework facades；Go/TS/Rust base/function/method 加 optional capability descriptors；`framework_adapters.v1.json`、`optional_adapters.v1.json` | dependency-free adapter contract 和 framework capability boundary 强 | runtime-core 已覆盖 |
| MCP adapters | Python MCP adapters；Go/TS/Rust MCP-style in-memory/tool/context adapters；`mcp_adapters.v1.json`、`optional_adapters.v1.json` | dependency-free MCP contract 和 optional real transport boundary 强 | runtime-core 已覆盖 |
| Ops readiness | Python retention/backup/schema；Go/TS/Rust helpers；`ops_readiness.v1.json`、`storage_schema.v1.json` | 非破坏性 readiness checks 和 DDL metadata 强 | 已覆盖 |
| Boundary lint | Python `lint.py`、Go `ScanBoundarySource`、TS `scanBoundarySource`、Rust `scan_boundary_source`、`boundary_lint.v1.json` | 共享 dependency-free source lint semantics 强 | 已覆盖 |

## 当前 Runtime-Core 必须 Checks

每个 preview runtime 的 conformance CLI 必须报告：

- `runtime_smoke_evidence_replay`
- `local_persistence_smoke`
- `local_blob_store_smoke`
- `tool_schema_validation_smoke`
- `worker_service_smoke`
- `tool_ledger_idempotent_retry`
- `policy_approval_sandbox_smoke`
- `cost_failure_attribution_smoke`
- `media_stream_artifacts_smoke`
- `evidence_consumers_smoke`
- `otlp_trace_export_smoke`
- `simple_api_smoke`
- `static_debug_html_smoke`
- `ops_readiness_smoke`
- `storage_schema_smoke`
- `mcp_adapters_smoke`
- `framework_adapters_smoke`
- `boundary_lint_smoke`
- `scheduler_smoke`
- `adversarial_review_smoke`
- `evidence_regression_smoke`
- `failure_injection_smoke`
- `shadow_smoke`
- `repro_golden_smoke`
- `time_travel_timeline_smoke`
- `optional_adapters_smoke`

聚合 runner 会从 `contracts/conformance/runtime_semantics.v1.json` 读取并验证这些 checks。

## 仍不声明的内容

zero-gap audit 表示 runtime-core parity 已覆盖。它**不等于**每种语言都有每个 concrete production adapter。下面仍是 optional adapter/package 工作：

1. Go/TypeScript/Rust 的 live Postgres store package。
2. Go/TypeScript/Rust 的 live S3 或 S3-compatible blob store package。
3. Docker/E2B/bubblewrap/Kubernetes/gVisor/Firecracker 等 concrete sandbox package，超出 fail-closed runtime boundary descriptor 的部分。
4. LangGraph/LangChain/CrewAI/AutoGen/OpenAI Agents SDK/LlamaIndex/Semantic Kernel 的 concrete package，超出 dependency-free adapter contract 的部分。
5. 真实 MCP SDK transport，超出 dependency-free MCP-style tool/context contract 的部分。
6. 像素级完全一致的 debug UI layout；portable static HTML semantics 已覆盖。

## 当前结论

当前仓库已经具备 **Python reference runtime-core parity across Go, TypeScript, and Rust**。Adapter-heavy 能力没有被忽略，而是通过 `optional_adapters.v1.json` 表示为 optional adapter boundary，后续可以作为独立 package 实现，不需要改 runtime core。

## 机器可读 Audit

声明 parity 前运行：

```bash
/Users/duyaoguang/.local/bin/python3.11 scripts/audit_python_parity.py > /tmp/agentledger-python-parity-audit.json
```

当前 scope 的期望结果：`gap_count: 0`。

---

generated by codex cli
