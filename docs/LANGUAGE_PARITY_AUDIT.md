# Language Parity Audit

[English](LANGUAGE_PARITY_AUDIT.md) | [中文](zh/LANGUAGE_PARITY_AUDIT.md)

This document is the completion-audit checklist for the goal: **Go, TypeScript, and Rust should match the Python implementation where AgentLedger claims native runtime parity.** It prevents treating a green test run as proof of parity unless the checked artifacts cover the claimed surface.

## Success Criteria

AgentLedger uses three parity levels:

| Level | Meaning | Completion rule |
| --- | --- | --- |
| Runtime-core parity | A language can execute the same reliability, safety, evidence, replay, scheduler, tool, policy, and adapter-boundary semantics natively. | Must be covered by `contracts/conformance/runtime_semantics.v1.json`, per-language conformance CLIs, unit tests, `scripts/check_language_parity.py`, and the module audit. |
| Optional adapter boundary parity | A language exposes the same extension boundary for concrete backends/frameworks without importing heavy SDKs in core. | Must be represented in `optional_adapters.v1.json` and fail closed when the concrete adapter is not installed or injected. |
| Concrete adapter parity | A language ships a live adapter for a backend/framework such as Postgres, S3, Docker, LangGraph, or MCP transport. | Optional package/module work. Not required for runtime-core parity unless the release explicitly claims that concrete adapter. |

The current parity claim is complete when every Python public capability is either:

1. implemented and verified in Go, TypeScript, and Rust,
2. represented as an optional adapter boundary or out-of-core contract, or
3. explicitly excluded from runtime-core parity.

## Prompt-To-Artifact Checklist

| Requirement | Evidence today | Coverage strength | Status |
| --- | --- | --- | --- |
| Contract shared across languages | `contracts/agentledger.runtime.v1.json`; `src/agentledger/contract.py`; `contract export` diff in parity runner | Strong | Covered |
| Required semantic manifest | `contracts/conformance/runtime_semantics.v1.json` | Strong | Covered |
| Aggregate verifier | `scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json` | Strong for listed checks | Covered |
| Conservative module audit | `scripts/audit_python_parity.py` | Strong for Python module-to-evidence mapping | Covered, zero gaps |
| Go native runtime baseline | `go/`; `go/cmd/agentledger-go/main.go`; `go test ./...`; Go conformance JSON | Strong for listed checks | Covered for runtime-core |
| TypeScript native runtime baseline | `typescript/`; `npm test`; `npm run check`; TS conformance JSON | Strong for listed checks | Covered for runtime-core |
| Rust native runtime baseline | `rust/`; `cargo test`; Rust conformance JSON | Strong for listed checks | Covered for runtime-core |
| Minimal hello-world API | Python `simple.py`; Go `SimpleRun`; TS `simpleRun`; Rust `simple_run`; `simple_api.v1.json` | Strong | Covered |
| Scheduler facade | Python/Go/TS/Rust `RuntimeScheduler`; `scheduler.v1.json` | Strong for runtime-owned status/recovery/cancel facade | Covered |
| Evidence/replay/debug | Python evidence/replay/trace/diff/time travel; Go/TS/Rust equivalents; `evidence_consumers.v1.json`, `static_debug_html.v1.json`, `time_travel.v1.json` | Strong for portable evidence consumers and static debug artifact | Covered |
| Reliability harness | Python review/eval/repro/failure injection/shadow; Go/TS/Rust equivalents; `adversarial_review.v1.json`, `evidence_regression.v1.json`, `failure_injection.v1.json`, `shadow.v1.json`, `repro.v1.json` | Strong for side-effect-free runtime evidence checks; external eval platforms remain out of core | Covered |
| Storage | Python SQLite/Postgres; Go JSON local; TS JSON local; Rust memory/snapshot local; `local_persistence.v1.json`, `storage_schema.v1.json`, `optional_adapters.v1.json` | Strong for local durable semantics and Postgres schema/adapter boundary; live drivers are optional adapters | Covered for runtime-core |
| Blob stores | Python local/S3; Go/TS/Rust local; `local_blob_store.v1.json`, `optional_adapters.v1.json` | Strong for local content-addressed semantics and S3 adapter boundary; live S3 clients are optional adapters | Covered for runtime-core |
| Sandbox | Python local/disabled/Docker/E2B/bubblewrap/Kubernetes/gVisor/Firecracker/remote; Go/TS/Rust fail-closed boundary; `policy_approval_sandbox.v1.json`, `optional_adapters.v1.json` | Strong for runtime boundary and optional backend descriptors | Covered for runtime-core |
| Framework adapters | Python base/function/method/LangGraph and framework facades; Go/TS/Rust base/function/method plus optional capability descriptors; `framework_adapters.v1.json`, `optional_adapters.v1.json` | Strong for dependency-free adapter contract and framework capability boundary | Covered for runtime-core |
| MCP adapters | Python MCP adapters; Go/TS/Rust MCP-style in-memory/tool/context adapters; `mcp_adapters.v1.json`, `optional_adapters.v1.json` | Strong for dependency-free MCP contract and optional real transport boundary | Covered for runtime-core |
| Ops readiness | Python retention/backup/schema; Go/TS/Rust helpers; `ops_readiness.v1.json`, `storage_schema.v1.json` | Strong for non-destructive readiness checks and DDL metadata | Covered |
| Boundary lint | Python `lint.py`; Go `ScanBoundarySource`; TS `scanBoundarySource`; Rust `scan_boundary_source`; `boundary_lint.v1.json` | Strong for shared dependency-free source lint semantics | Covered |

## Runtime-Core Checks Currently Required

Every preview runtime must report these checks from its conformance CLI:

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

The aggregate runner verifies this list from `contracts/conformance/runtime_semantics.v1.json`.

## What Is Still Not Claimed

The zero-gap audit means runtime-core parity is covered. It does **not** claim that every concrete production adapter exists in every language. These remain optional adapter/package work:

1. Live Postgres store packages for Go/TypeScript/Rust.
2. Live S3 or S3-compatible blob store packages for Go/TypeScript/Rust.
3. Concrete Docker/E2B/bubblewrap/Kubernetes/gVisor/Firecracker sandbox packages beyond fail-closed runtime boundary descriptors.
4. Concrete LangGraph/LangChain/CrewAI/AutoGen/OpenAI Agents SDK/LlamaIndex/Semantic Kernel packages beyond the dependency-free adapter contract.
5. Real MCP SDK transports beyond the dependency-free MCP-style tool/context contract.
6. Exact pixel-identical debug UI layout; portable static HTML semantics are covered.

## Current Conclusion

The repository now has **Python reference runtime-core parity across Go, TypeScript, and Rust** for the declared AgentLedger core scope. Adapter-heavy capabilities are not ignored; they are represented as optional adapter boundaries through `optional_adapters.v1.json` and may be implemented as separate packages without changing runtime core.

## Machine-Readable Audit

Run this before claiming parity:

```bash
/Users/duyaoguang/.local/bin/python3.11 scripts/audit_python_parity.py > /tmp/agentledger-python-parity-audit.json
```

Expected result for the current scope: `gap_count: 0`.

---

generated by codex cli
