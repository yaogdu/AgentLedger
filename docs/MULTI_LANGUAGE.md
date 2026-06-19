# Multi-language Strategy

AgentLedger is contract-first and multi-language by design. The long-term goal is not a Python-only runtime and not a set of thin SDKs. The goal is native runtime-core parity across Python, Go, TypeScript, and Rust, all preserving the same durable execution, Tool Ledger, evidence, replay, policy, and conformance semantics.

Python is the current reference runtime. Other languages may start smaller, but a language is not considered runtime-ready until it implements the stable runtime-core capabilities and passes the shared conformance suite.

## Target State

```text
AgentLedger Runtime Contract
  language-neutral semantics, wire objects, event schema, invariants,
  failure semantics, conformance fixtures, and evidence format

agentledger-python
  current reference runtime, CLI, local runtime, examples, adapters

agentledger-go
  preview native runtime-core baseline for Go services, workers, and infrastructure-heavy deployments

agentledger-typescript
  preview Node/TypeScript-compatible runtime-core baseline for Node.js/edge-adjacent agent services and TS framework adapters

agentledger-rust
  preview in-memory runtime-core baseline with local snapshot persistence for high-performance workers, embedded runtimes, replay/sandbox components
```

SDK/client-only packages are allowed during the transition, but they are not enough for parity. They are useful when a language needs to submit work to another runtime, run framework adapters, or call a remote worker. They do not count as a stable language runtime by themselves.

## Why Contract First

Without a shared contract, each language implementation will drift:

```text
different event names
different lease behavior
different idempotency semantics
different replay behavior
different evidence bundles
different schema assumptions
different cancellation semantics
different policy/sandbox failure modes
```

The contract must define the semantics that every implementation preserves:

```text
append-only events
state version checks
lease/fencing
Tool Ledger idempotency
approval-before-execution
sandbox fail-closed
replay/shadow side-effect blocking
evidence bundle shape
storage migration status shape
cost and failure attribution shape
cancellation and error propagation semantics
```

## Current Contract Artifact

The current v1.0 stable runtime-core contract is exported from Python:

```bash
PYTHONPATH=src python3 -m agentledger contract export
PYTHONPATH=src python3 -m agentledger contract export --out contracts/agentledger.runtime.v1.json
```

The checked-in golden file is:

```text
contracts/agentledger.runtime.v1.json
```

Go, TypeScript, and Rust implementations should use this as a golden compatibility target together with shared evidence fixtures and conformance runners.

## Runtime-ready Definition

A language implementation is `runtime-ready` only when it can prove the same core guarantees as the Python reference runtime.

Required capabilities:

```text
AgentContext boundary
Runtime and run/step state machine
StateStore contract
EventLog contract
ToolGateway and Tool Ledger
tool input/output schema validation
idempotent tool calls
approval/policy hooks
sandbox boundary semantics
lease/fencing/recovery
cancellation semantics
budget and cost attribution
failure taxonomy and propagation
evidence export
replay without external side effects
contract export or contract validation
shared conformance suite
```

A language can be `sdk-ready` earlier if it only provides protocol clients, tool descriptors, or framework adapters. `sdk-ready` is useful, but it must be labeled differently from `runtime-ready`.

## Implementation Process

The process is staged so Python remains stable while the other languages catch up.

### 0. Keep Python As Reference

- Python remains the source of truth for v1 runtime semantics until another language passes equivalent conformance.
- The Python contract export and golden evidence fixtures define expected behavior.
- Python changes that affect runtime semantics must update the contract, tests, docs, and conformance fixtures together.

### 1. Freeze Shared Contract And Fixtures

- Keep `contracts/agentledger.runtime.v1.json` as the stable runtime-core contract.
- Keep `contracts/conformance/runtime_semantics.v1.json` as the shared semantic manifest. It is the machine-readable authority for the runtime semantic check ids every language conformance CLI must report.
- Add shared fixtures for event logs, Tool Ledger entries, evidence bundles, replay, lease fencing, cancellation, and failure propagation. The first shared preview fixture is `contracts/conformance/runtime_baseline.v1.json`. Preview parity fixtures now also exist for `local_persistence.v1.json`, `local_blob_store.v1.json`, `tool_schema_validation.v1.json`, `worker_service.v1.json`, `policy_approval_sandbox.v1.json`, `cost_failure_attribution.v1.json`, `media_stream_artifacts.v1.json`, `evidence_consumers.v1.json`, `static_debug_html.v1.json`, `ops_readiness.v1.json`, `storage_schema.v1.json`, `mcp_adapters.v1.json`, `framework_adapters.v1.json`, `otlp_trace_export.v1.json`, `simple_api.v1.json`, and `boundary_lint.v1.json`, `scheduler.v1.json`, `adversarial_review.v1.json`, `evidence_regression.v1.json`, `failure_injection.v1.json`, `shadow.v1.json`, `repro.v1.json`, `time_travel.v1.json`, `optional_adapters.v1.json`; Go, TypeScript, and Rust tests execute these semantics as runtime-core parity gates.
- Keep fixtures language-neutral: JSON, JSONL, and documented directory layouts.

### 2. Build Native Runtime Baselines

Suggested order:

1. Go: strong fit for workers, services, Kubernetes/controller integrations, and enterprise infrastructure teams.
2. TypeScript: strong fit for Node.js agent services, web/edge-adjacent tooling, and TS framework adoption.
3. Rust: strong fit for high-performance replay/sandbox/worker components and embedded runtimes.

Each language should first implement the smallest native runtime loop:

```text
create run
claim leased step
append event
call runtime-managed tool
write Tool Ledger entry
commit checkpoint
reopen local durable store
write/read local content-addressed blobs
validate tool input/output schemas
run local worker/service loop
export evidence
replay without side effects
```

### 3. Add Adapter Layers Without Bloated Core

Each language can then add optional adapters:

```text
framework adapters
storage adapters
blob store adapters
sandbox executors
observability exporters
MCP/tool/context adapters
worker/deployment adapters
```

Adapters must preserve the runtime contract. Mature external systems should be integrated through adapters instead of being rebuilt inside AgentLedger core.

### 4. Pass Shared Conformance

Before a language leaves preview, it must pass conformance for:

```text
contract JSON compatibility
event/evidence golden fixtures
StateStore behavior
Tool Ledger idempotency
lease/fencing/recovery
cancellation behavior
replay side-effect blocking
policy/approval/sandbox fail-closed behavior
cost/failure attribution shape
```

Conformance should be runnable in CI and should produce a report. Use `scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json` for the local aggregate report across Python, Go, TypeScript, Rust, per-language conformance CLIs, contract diff, docs links, and whitespace checks. The report loads `contracts/conformance/runtime_semantics.v1.json`, records `required_semantic_checks`, and parses `language_conformance` output for each preview runtime.

### 5. Move To Unified Release Train After Parity

Before parity:

```text
Python: stable reference releases
Go/TypeScript/Rust: 0.x preview releases until conformance is complete
```

After parity:

```text
all language runtimes move under the same AgentLedger release train
runtime contract changes require synchronized language updates
no language is marked stable for a release unless it passes the shared conformance suite
breaking runtime semantics require a new major contract version
```

## Repository Strategy

This repository is the canonical source for the contract, docs, Python reference runtime, and shared fixtures. Future language implementations can start in this repository so contract changes, fixtures, and release gates stay visible together.

A future split is possible only if it keeps the same compatibility rules:

```text
agentledger-contracts   shared contract and fixtures
agentledger-python      Python runtime
agentledger-go          Go runtime
agentledger-typescript  TypeScript runtime
agentledger-rust        Rust runtime
```

Even if packages move to separate repositories later, the contract and conformance suite must remain the shared authority.

## Package Strategy

Current package:

```text
agentledger-runtime  PyPI distribution
agentledger          Python import package and CLI
```

Future packages should make maturity explicit:

```text
agentledger-go          native Go runtime package
agentledger-typescript  native TypeScript runtime package
agentledger-rust        native Rust runtime crate
agentledger-contracts   optional shared contract/fixture package
```

SDK-only packages should include that in their name or documentation until they are runtime-ready.

## Language Roles

| Language | First useful milestone | Runtime-ready milestone |
|---|---|---|
| Python | reference runtime and Agent framework integrations | already stable for v1.0 runtime-core |
| Go | preview native worker/runtime baseline, StateStore adapters next, infra services | full runtime-core conformance, worker/deployment hardening |
| TypeScript | preview Node/TypeScript-compatible runtime baseline, protocol client, tool registration, TS framework adapters next | full runtime-core conformance for Node.js services |
| Rust | preview in-memory runtime baseline with local snapshot persistence, runtime primitives, replay/sandbox/worker components next | full runtime-core conformance or certified high-performance core subset |

## Compatibility Rules

Each implementation must prove compatibility through:

```text
contract JSON snapshot test
StateStore conformance tests or equivalent fixtures
event/evidence golden fixtures
replay does not call external tools
Tool Ledger idempotency tests
lease/fencing tests
cancellation tests
policy/approval/sandbox fail-closed tests
cost/failure attribution fixture tests
media/stream artifact ref fixture tests
```

Use `scripts/check_language_parity.py` as the local aggregate runner for Python, Go, TypeScript, Rust, contract diff, Markdown links, and whitespace checks.

Python remains the reference implementation until another language passes the same conformance suite. Once all target languages pass, the release train should move together.

## Non-goals

The multi-language plan should not turn AgentLedger into a bloated platform.

```text
Do not rebuild mature workflow engines in every language.
Do not put full eval platforms inside runtime-core.
Do not force heavy observability, sandbox, or cloud SDK dependencies into core.
Do not claim runtime parity for SDK-only clients.
Do not let each language invent different event, evidence, or Tool Ledger semantics.
```

The default decision remains: keep runtime-core thin but enforce the invariants that only the runtime can enforce.

---

generated by codex cli
