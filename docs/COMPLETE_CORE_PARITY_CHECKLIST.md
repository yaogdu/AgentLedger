# Complete Core Parity Checklist

[English](COMPLETE_CORE_PARITY_CHECKLIST.md) | [中文](zh/COMPLETE_CORE_PARITY_CHECKLIST.md)

This is the strict definition of "complete alignment" for AgentLedger Python, Go, TypeScript, and Rust. A green conformance run is necessary, but not sufficient. Complete core parity means every portable runtime-core capability has matching implementation, usage experience, docs, tests, packaging metadata, and release evidence across all four languages.

## Scope

Included:

- runtime-core capabilities that are portable across Python, Go, TypeScript, and Rust
- common official adapter APIs that are portable across languages: Postgres, S3/MinIO, OTLP transport, Docker sandbox manifest and command-style Docker execution
- CLI/DX baseline for every language
- docs, quickstarts, examples, conformance, and package metadata for every language

Excluded or not applicable:

- ecosystem-specific adapters whose upstream ecosystem does not exist or is not mature in a language, such as LangGraph outside Python
- real cloud/service hardening that requires external infrastructure, unless a release explicitly claims it
- application administration backend, full eval system, workflow engine, RAG system, or sandbox provider behavior

## Status Legend

| Status | Meaning |
| --- | --- |
| `done` | Implemented and verified with concrete evidence. |
| `weak` | Exists but coverage, docs, or packaging is not strong enough for complete parity. |
| `missing` | Not present. |
| `n/a` | Intentionally not applicable with a reason. |

## Checklist

| Area | Requirement | Python evidence | Go evidence | TypeScript evidence | Rust evidence | Verification | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Runtime state | Create run, claim step, commit state, append event | `src/agentledger/runtime.py`, `src/agentledger/store.py` | `go/runtime.go`, `go/store.go` | `typescript/src/index.js` | `rust/src/lib.rs` | `runtime_baseline.v1.json`, tests, conformance | done |
| Lease/fencing/recovery | Stale workers cannot commit; expired leases recover | Python tests + store | Go store/tests | TS tests | Rust tests | `runtime_baseline.v1.json`, `failure_injection.v1.json` | done |
| Cancellation | Cancelled runs fence late commits | Python tests | Go tests | TS tests | Rust tests | `runtime_baseline.v1.json`, `failure_injection.v1.json` | done |
| Tool Gateway | Runtime-managed tool calls | `context.py`, `tools.py` | `tools.go` | `index.js` | `lib.rs` | `tool_schema_validation.v1.json`, `runtime_baseline.v1.json` | done |
| Tool Ledger | Idempotent side-effect retry | `tools.py`, `store.py` | `tools.go`, `store.go` | `index.js` | `lib.rs` | `tool_ledger_idempotent_retry` | done |
| Schema validation | Tool input/output schema checks | Python schema subset | Go schema subset | TS schema subset | Rust schema subset | `tool_schema_validation.v1.json` | done |
| Policy/approval | Denial, pending approval, resume/deny | Python policy/approval | Go policy/approval | TS policy/approval | Rust policy/approval | `policy_approval_sandbox.v1.json` | done |
| Sandbox boundary | Fail-closed sandbox-required tools | Python sandbox | Go sandbox interface | TS sandbox classes | Rust sandbox error semantics | `policy_approval_sandbox.v1.json` | done |
| Cost/failure | Cost records, budgets, failure attribution | Python reporters | Go reporters | TS reporters | Rust reporters | `cost_failure_attribution.v1.json` | done |
| Evidence/replay | Evidence export and replay-safe summary | Python evidence/replay | Go evidence/replay | TS evidence/replay | Rust evidence/replay | `runtime_baseline.v1.json`, `evidence_consumers.v1.json` | done |
| Debug consumers | trace, diff, divergence, static HTML, time travel | Python modules | Go modules | TS functions | Rust functions | `evidence_consumers.v1.json`, `static_debug_html.v1.json`, `time_travel.v1.json` | done |
| Reliability harness | failure injection, adversarial review, evidence regression, repro, shadow report | Python modules | Go modules | TS functions | Rust functions | fixtures + conformance | done |
| Scheduler/worker | Local worker/service and scheduler facade | Python worker/scheduler | Go worker/scheduler | TS worker/scheduler | Rust worker/scheduler | `worker_service.v1.json`, `scheduler.v1.json` | done |
| Local persistence | Local durable store reopen | SQLite/local | JSON local | JSON local | snapshot local | `local_persistence.v1.json` | done |
| Blob store | Local content-addressed blobs | LocalBlobStore | LocalBlobStore | LocalBlobStore | LocalBlobStore | `local_blob_store.v1.json` | done |
| Media/stream refs | Store refs/checkpoints as evidence, not processing infra | Python media | Go support | TS support | Rust support | `media_stream_artifacts.v1.json` | done |
| MCP-style adapters | Dependency-free MCP tool/context contract | Python | Go | TS | Rust | `mcp_adapters.v1.json` | done |
| Framework base adapters | Dependency-free function/method adapter contract | Python | Go | TS | Rust | `framework_adapters.v1.json` | done |
| Optional adapter boundary | Capability descriptors and fail-closed boundary | Python docs/modules | Go | TS | Rust | `optional_adapters.v1.json` | done |
| Official adapter API | Postgres/S3/OTLP/Docker injected-client or manifest APIs | Python has concrete/injected paths | Go `official_adapters.go` | TS `index.js` | Rust `lib.rs` | `official_adapters.v1.json` | done |
| CLI baseline | `--help`, `doctor`, `version`, `quickstart`, `conformance`, `contract validate`, `contract export` | `agentledger` CLI | `agentledger-go` | `agentledger-ts` | `agentledger-rust` | `scripts/check_complete_core_parity.py` | done |
| Quickstart docs | Language quickstart and adapter quickstart | README + docs | `go/README.md` | `typescript/README.md` | `rust/README.md` | docs link check | done |
| Examples | Runnable examples for core runtime and adapter API | Python examples | `go/examples/quickstart/main.go` | `typescript/examples/quickstart/quickstart.js` | `rust/examples/quickstart.rs` | `scripts/check_complete_core_parity.py` | done |
| Package metadata | Installable package metadata in the current 1.3 release family | PyPI metadata `1.3.x` | `go.mod` tag `go/v1.3.1` for current baseline | npm package `1.3.1` for current baseline | `Cargo.toml` `1.3.1` for current baseline | `scripts/check_complete_core_parity.py` release-family check | done |
| Package install smoke | Install/import/run from published or built package | PyPI `agentledger-runtime==1.3.4` release smoke after publish for current Inspector patch | `go/v1.3.1` clean external `go get` smoke after tag | npm `agentledger-runtime@1.3.1` release smoke after publish | crates.io `agentledger-runtime==1.3.1` release smoke after publish | publish logs + `scripts/check_complete_core_parity.py` dry-run gates | release-gated |
| Release docs | Changelog, release checklist, status docs reflect exact parity boundary | docs | docs | docs | docs | docs link check | done |
| Comparison docs | Honest overlap with LangChain/LangGraph/LangSmith/Langfuse/etc. | docs | docs | docs | docs | docs link check | done |

## Current Boundary After Strict Core Parity Gate

The strict core parity gate now covers the previously weak areas:

1. CLI baseline is automatically checked for all four language CLIs.
2. Go, TypeScript, and Rust have runnable quickstart example files.
3. TypeScript and Rust package surfaces have package dry-run checks (`npm pack --dry-run`, `cargo package --allow-dirty --no-verify`) and post-publish install smokes are required for release.
4. Package release families are checked across Python, TypeScript, and Rust. The current core release family is `1.3`; Python may carry Inspector-only patch releases such as `1.3.4` without changing non-Python runtime-core baselines.
5. Go external module consumption is tag/release dependent; each release should repeat the clean external `go get` smoke after pushing the `go/vX.Y.Z` tag.
6. Real service-backed hardening remains out of scope for core parity and stays documented as optional follow-up work.

## Required Completion Gate

Before marking complete alignment achieved, run and record:

```bash
python3.11 scripts/audit_python_parity.py > /tmp/agentledger-python-parity-audit.json
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
python3.11 scripts/check_complete_core_parity.py
```

`check_complete_core_parity.py` must verify CLI baseline, runnable examples, package metadata, and docs links in addition to semantic conformance.
