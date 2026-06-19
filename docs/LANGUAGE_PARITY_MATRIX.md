# Language Parity Matrix

This matrix tracks parity across AgentLedger language implementations. Python is the v1.x reference runtime. Go, TypeScript, and Rust are native runtime-core implementations covered by shared parity gates; provider-specific adapters can still remain optional or preview.

For the concrete side-by-side table of runtime-core, portable adapters, provider-specific differences, ecosystem-specific framework adapters, and directory-layout decisions, see `LANGUAGE_IMPLEMENTATION_COMPARISON.md`.

## Status Legend

| Status | Meaning |
|---|---|
| Stable | Implemented, documented, tested, and part of the stable runtime-core contract. |
| Parity | Implemented, documented, and covered by shared runtime-core conformance; Python remains the reference for contract evolution. |
| Preview | Implemented or sketched but not yet stable enough for production-ready adapter claims. |
| Planned | In scope for that language, not implemented yet. |
| Optional | Adapter or package-level capability, not required in the minimal runtime core. |
| Not core | Should stay outside runtime-core and integrate through adapters or evidence contracts. |

## Runtime-core Parity

| Capability | Python | Go | TypeScript | Rust | Required for runtime-ready? |
|---|---|---|---|---|---|
| AgentContext boundary | Stable | Parity | Parity | Parity | Yes |
| Runtime state machine | Stable | Parity | Parity | Parity | Yes |
| Run/session/step model | Stable | Parity | Parity | Parity | Yes |
| StateStore contract | Stable | Parity | Parity | Parity | Yes |
| Event log / WAL semantics | Stable | Parity | Parity | Parity | Yes |
| ToolGateway | Stable | Parity | Parity | Parity | Yes |
| Tool schema validation | Stable | Parity | Parity | Parity | Yes |
| Tool Ledger | Stable | Parity | Parity | Parity | Yes |
| Idempotent tool calls | Stable | Parity | Parity | Parity | Yes |
| Evidence export | Stable | Parity | Parity | Parity | Yes |
| Replay without side effects | Stable | Parity | Parity | Parity | Yes |
| Lease/fencing/recovery | Stable | Parity | Parity | Parity | Yes |
| Cancellation semantics | Stable | Parity | Parity | Parity | Yes |
| Error/failure propagation | Stable | Parity | Parity | Parity | Yes |
| Policy/approval hooks | Stable | Parity | Parity | Parity | Yes |
| Sandbox boundary semantics | Stable | Parity | Parity | Parity | Yes |
| Budget enforcement hooks | Stable | Parity | Parity | Parity | Yes |
| Cost attribution shape | Stable | Parity | Parity | Parity | Yes |
| Failure attribution shape | Stable | Parity | Parity | Parity | Yes |
| Contract validation/export | Stable | Parity | Parity | Parity | Yes |
| Shared conformance runner | Stable | Parity | Parity | Parity | Yes |

## Adapter And Ecosystem Parity

| Capability | Python | Go | TypeScript | Rust | Core requirement? |
|---|---|---|---|---|---|
| SQLite/local store | Stable | Parity | Parity | Parity | Recommended default |
| Postgres StateStore | Preview | Contract | Contract | Contract | Optional adapter |
| Local blob store | Stable | Parity | Parity | Parity | Recommended default |
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

## Non-Python Runtime-Core Baseline

The `go/` module now implements a dependency-free runtime-core package with an in-memory/JSON local store, run/step state machine, lease recovery, cancellation fencing, ToolGateway, Tool Ledger idempotency, evidence export, replay summary, policy denial, approval pause/resume, sandbox fail-closed behavior, cost/budget records, model-call accounting, and failure attribution. The `typescript/` module implements the same runtime-core loop for Node.js with `.d.ts` declarations. The `rust/` module implements an in-memory dependency-free runtime-core package with local snapshot persistence for the same runtime-core semantics. All three non-Python baselines now test `runtime_baseline.v1.json`, `local_persistence.v1.json`, `local_blob_store.v1.json`, `tool_schema_validation.v1.json`, `worker_service.v1.json`, `policy_approval_sandbox.v1.json`, `cost_failure_attribution.v1.json`, `media_stream_artifacts.v1.json`, `evidence_consumers.v1.json`, `static_debug_html.v1.json`, `ops_readiness.v1.json`, `storage_schema.v1.json`, `mcp_adapters.v1.json`, `framework_adapters.v1.json`, `otlp_trace_export.v1.json`, `simple_api.v1.json`, and `boundary_lint.v1.json`, `scheduler.v1.json`, `adversarial_review.v1.json`, `evidence_regression.v1.json`, `failure_injection.v1.json`, `shadow.v1.json`, `repro.v1.json`, `time_travel.v1.json`, `optional_adapters.v1.json`. A reportable aggregate runner exists at `scripts/check_language_parity.py`; the non-Python runtimes are runtime-core aligned; concrete production adapter packages and full media processing/stream transport adapters remain optional follow-up work; per-language CLIs now exist and execute fixture-aligned semantic smokes for state/evidence/replay, local persistence/reopen, local blob store, tool schema validation, worker service, Tool Ledger retry, policy/approval/sandbox, cost/failure attribution, and media/stream artifact refs, trace spans, evidence diff, divergence, debug summaries, static HTML debug export, ops readiness planning, storage schema helpers, MCP-style in-memory adapters, dependency-free framework adapters, OTLP JSON trace export, and the simple hello-world API.


Run the local cross-language gate with:

```bash
python3.11 scripts/check_language_parity.py
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

The JSON report includes parsed `language_conformance` output for Go, TypeScript, and Rust and verifies every runtime reports the same required semantic checks from `contracts/conformance/runtime_semantics.v1.json`.

## Runtime-ready Gate

A language becomes runtime-core ready when all required runtime-core capabilities are implemented and the shared conformance suite passes. This gate does not make every optional external adapter production-hardened.

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

Runtime-core parity now:

```text
Python remains the reference implementation.
Go, TypeScript, and Rust publish on the same runtime-core release train when packaging metadata, examples, and CLI checks are green.
Patch versions may differ for packaging-only fixes, but runtime-core conformance must remain green.
SDK/client packages must not be described as full runtime implementations.
```

Future contract changes:

```text
all stable language runtimes move together
contract changes require synchronized implementation and conformance updates
breaking runtime semantics require a new major contract version
```

---

generated by codex cli
