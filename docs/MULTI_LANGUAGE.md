# Multi-language Strategy

AgentLedger should not become a Python-only framework.

The Python package is the current reference implementation because it is fastest for the first Agent/LLM ecosystem integrations. Rust, TypeScript, and Go should target the same runtime contract instead of re-implementing unrelated semantics.

## Positioning

```text
AgentLedger Runtime Contract
  language-neutral semantics, wire objects, event schema, invariants

agentledger-python
  reference runtime, local development, examples, CLI, framework adapters

agentledger-ts
  SDK and worker client for Node/edge/web tooling

agentledger-rs
  high-performance runtime pieces, sandbox/worker processes, embedded use cases

agentledger-go
  infra adapters, Kubernetes/controller style workers, enterprise services
```

## Why A Contract First

Without a shared contract, each language implementation will drift:

```text
different event names
different lease behavior
different idempotency semantics
different replay behavior
different evidence bundles
different schema assumptions
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

Rust, TypeScript, and Go implementations should use this as a golden compatibility target.

## Package Strategy

Recommended repository/package shape:

```text
agentledger/
  contracts/
    agentledger.runtime.v1.json
  python/
    agentledger reference runtime
  typescript/
    SDK, worker client, framework adapters
  rust/
    runtime primitives, worker, sandbox helpers
  go/
    worker services, Kubernetes/controller adapters
```

This repository currently contains the Python reference implementation at the repo root. It can later become a monorepo or the contract can be split into a dedicated `agentledger-contracts` repo/package.

## Language Roles

| Language | First role | Later role |
|---|---|---|
| Python | reference runtime and Agent framework integrations | production runtime for Python shops |
| TypeScript | protocol client, tool registration, Node worker | web/edge adapters and TS agent frameworks |
| Rust | high-performance worker/runtime components | sandbox, replay engine, embedded runtime |
| Go | infra worker and Kubernetes-friendly services | enterprise deployment adapters |

## Compatibility Rules

Each implementation should prove compatibility through:

```text
contract JSON snapshot test
StateStore conformance tests or equivalent fixtures
event/evidence golden fixtures
replay does not call external tools
Tool Ledger idempotency tests
lease/fencing tests
```

Python remains the reference implementation until another language passes the same conformance suite.

## Non-goals

The multi-language plan should not force every language to implement every feature immediately.

```text
TypeScript can start as worker/client only.
Rust can start as runtime primitives or sandbox worker only.
Go can start as infra adapter or worker service only.
Python can remain the fastest full-stack reference implementation.
```

