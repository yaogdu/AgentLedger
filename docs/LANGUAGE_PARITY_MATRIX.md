# Language Parity Matrix

This matrix tracks the target parity across AgentLedger language implementations. Python is the current v1.0 reference runtime. Go, TypeScript, and Rust are preview native runtime implementations; SDK/client-only milestones may appear first, but they do not count as runtime parity.

## Status Legend

| Status | Meaning |
|---|---|
| Stable | Implemented, documented, tested, and part of the stable runtime-core contract. |
| Preview | Implemented or sketched but not yet stable enough for runtime-ready claims. |
| Planned | In scope for that language, not implemented yet. |
| Optional | Adapter or package-level capability, not required in the minimal runtime core. |
| Not core | Should stay outside runtime-core and integrate through adapters or evidence contracts. |

## Runtime-core Parity

| Capability | Python | Go | TypeScript | Rust | Required for runtime-ready? |
|---|---|---|---|---|---|
| AgentContext boundary | Stable | Preview | Preview | Preview | Yes |
| Runtime state machine | Stable | Preview | Preview | Preview | Yes |
| Run/session/step model | Stable | Preview | Preview | Preview | Yes |
| StateStore contract | Stable | Preview | Preview | Preview | Yes |
| Event log / WAL semantics | Stable | Preview | Preview | Preview | Yes |
| ToolGateway | Stable | Preview | Preview | Preview | Yes |
| Tool schema validation | Stable | Preview | Preview | Preview | Yes |
| Tool Ledger | Stable | Preview | Preview | Preview | Yes |
| Idempotent tool calls | Stable | Preview | Preview | Preview | Yes |
| Evidence export | Stable | Preview | Preview | Preview | Yes |
| Replay without side effects | Stable | Preview | Preview | Preview | Yes |
| Lease/fencing/recovery | Stable | Preview | Preview | Preview | Yes |
| Cancellation semantics | Stable | Preview | Preview | Preview | Yes |
| Error/failure propagation | Stable | Preview | Preview | Preview | Yes |
| Policy/approval hooks | Stable | Preview | Preview | Preview | Yes |
| Sandbox boundary semantics | Stable | Preview | Preview | Preview | Yes |
| Budget enforcement hooks | Stable | Preview | Preview | Preview | Yes |
| Cost attribution shape | Stable | Preview | Preview | Preview | Yes |
| Failure attribution shape | Stable | Preview | Preview | Preview | Yes |
| Contract validation/export | Stable | Preview | Preview | Preview | Yes |
| Shared conformance runner | Stable | Preview | Preview | Preview | Yes |

## Adapter And Ecosystem Parity

| Capability | Python | Go | TypeScript | Rust | Core requirement? |
|---|---|---|---|---|---|
| SQLite/local store | Stable | Preview | Preview | Preview | Recommended default |
| Postgres StateStore | Preview | Planned | Planned | Optional | Optional adapter |
| Local blob store | Stable | Preview | Preview | Preview | Recommended default |
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

The `go/` module now implements a dependency-free preview baseline with an in-memory/JSON local store, run/step state machine, lease recovery, cancellation fencing, ToolGateway, Tool Ledger idempotency, evidence export, replay summary, policy denial, approval pause/resume, sandbox fail-closed behavior, cost/budget records, model-call accounting, and failure attribution. The `typescript/` module implements the same preview loop for Node.js with `.d.ts` declarations. The `rust/` module implements an in-memory dependency-free preview baseline with local snapshot persistence for the same runtime-core semantics. All three non-Python baselines now test `runtime_baseline.v1.json`, `local_persistence.v1.json`, `local_blob_store.v1.json`, `tool_schema_validation.v1.json`, `worker_service.v1.json`, `policy_approval_sandbox.v1.json`, `cost_failure_attribution.v1.json`, `media_stream_artifacts.v1.json`, `evidence_consumers.v1.json`, `static_debug_html.v1.json`, `ops_readiness.v1.json`, `storage_schema.v1.json`, `mcp_adapters.v1.json`, `framework_adapters.v1.json`, `otlp_trace_export.v1.json`, `simple_api.v1.json`, and `boundary_lint.v1.json`, `scheduler.v1.json`, `adversarial_review.v1.json`, `evidence_regression.v1.json`, `failure_injection.v1.json`, `shadow.v1.json`, `repro.v1.json`, `time_travel.v1.json`, `optional_adapters.v1.json`. A reportable aggregate runner exists at `scripts/check_language_parity.py`; the non-Python runtimes are still preview because concrete production adapter packages, full media processing/stream transport adapters, and stable published language packages are optional follow-up work; preview per-language CLIs now exist and execute fixture-aligned semantic smokes for state/evidence/replay, local persistence/reopen, local blob store, tool schema validation, worker service, Tool Ledger retry, policy/approval/sandbox, cost/failure attribution, and media/stream artifact refs, trace spans, evidence diff, divergence, debug summaries, static HTML debug export, ops readiness planning, storage schema helpers, MCP-style in-memory adapters, dependency-free framework adapters, OTLP JSON trace export, and the simple hello-world API.


Run the local cross-language gate with:

```bash
python3.11 scripts/check_language_parity.py
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

The JSON report includes parsed `language_conformance` output for Go, TypeScript, and Rust and verifies every runtime reports the same required semantic checks from `contracts/conformance/runtime_semantics.v1.json`.

## Runtime-ready Gate

A language becomes runtime-ready only when all required runtime-core capabilities are implemented and the shared conformance suite passes.

Minimum gate:

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

## Release Policy

Before parity:

```text
Python uses stable releases.
Go, TypeScript, and Rust may publish 0.x preview packages.
SDK/client packages must not be described as full runtime implementations.
```

After parity:

```text
all stable language runtimes move together
contract changes require synchronized implementation and conformance updates
breaking runtime semantics require a new major contract version
```
