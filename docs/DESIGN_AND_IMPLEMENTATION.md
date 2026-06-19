# Design and Implementation

This document explains how AgentLedger is implemented and which boundaries must remain stable. For the formal runtime schema, see `RUNTIME_SPEC.md`.

## Design Goals

AgentLedger is built around a narrow reliability claim:

```text
Every runtime-managed execution step should be durable, auditable, replayable, and fenced against stale workers.
```

Non-goals are equally important:

```text
do not replace agent frameworks
do not become a model SDK
do not own application business schemas
do not implement a long-running web application in runtime-core
do not promise exactly-once behavior for external systems without a Tool Ledger record
```

## Core State Machine

A run starts with one pending step:

```text
create_run
  -> runs.status = pending
  -> steps.status = pending
  -> append run_created and step_created
```

A worker claims a step:

```text
claim_step
  -> steps.status = running
  -> owner = worker_id
  -> lease_token = generated fencing token
  -> attempt += 1
  -> append step_claimed
```

The agent executes only inside `AgentContext`:

```text
AgentContext
  -> call_model
  -> call_tool
  -> write_state_patch
  -> create_artifact
  -> create_media_artifact
  -> create_stream_checkpoint
```

Commit is fenced:

```text
commit_state_patch
  -> validate lease token
  -> validate base state version
  -> merge JSON patch
  -> increment state_version
  -> mark step completed
  -> append state_patch_committed and step_completed
```

If the lease is stale, expired, or cancelled, commit fails. This is the key invariant that lets worker replicas exist without corrupting a logical run.

## Storage Implementation

The reference `SQLiteStore` stores runtime metadata:

```text
runs
steps
events
tool_ledger
artifacts
cost_records
approval_requests
schema_migrations
```

Payloads and large artifact contents go through `BlobStore` refs instead of being embedded directly into events.

SQLite is the local default. Postgres is an optional adapter path with its own migration status/apply commands, schema isolation, JSONB conversion, and native worker claim semantics.

## Tool Gateway and Tool Ledger

Agents should call external capabilities through `ctx.call_tool(...)`.

The `ToolGateway` performs:

```text
ToolSpec lookup
input schema validation
policy check
approval gate
budget check
sandbox boundary check
Tool Ledger reservation
tool execution
output schema validation
ledger status update
artifact/evidence recording
```

The Tool Ledger stores a stable idempotency key derived from the logical operation and causal context. If a worker crashes after a side effect, a retry can read the ledger instead of repeating the external write.

When the runtime cannot prove whether a side effect happened, the ledger should move into `PENDING_VERIFICATION` rather than blindly retrying.

## Replay, Evidence, and Regression

Replay is evidence-based:

```text
read events
read archived payload refs
validate tool/model/archive refs
summarize what happened
do not call external tools or model providers
```

Evidence bundles contain:

```text
run metadata
steps
events
tool ledger rows
artifacts
media artifact indexes
stream checkpoint indexes
cost records
final state
bundle hash
```

Regression tools compare evidence bundles instead of re-running side effects:

```text
diff
divergence
evidence regression
golden corpus evidence check
adversarial review checklist
```

## Worker and Scheduler Semantics

Workers are execution replicas, not the source of truth. Store transitions define correctness.

Important semantics:

```text
lease token fences stale workers
heartbeat extends the current lease
recover_expired_leases moves abandoned work back to retry_scheduled
cancel_run fences active workers
retry policy decides whether a failed step can be retried
failure attribution remains read-only
```

`WorkerService` is intentionally small. It provides a process-shaped loop with idle backoff and optional signal handlers, but distributed deployment policy should remain outside runtime-core.

## Sandbox and Permission Boundary

Sandbox support is a contract and adapter seam:

```text
none: fail closed for sandbox-required tools
local: explicit no-isolation mode
bubblewrap/docker: command-style adapter paths
kubernetes/gVisor: manifest dry-run and gated kubectl path
E2B/firecracker/custom: adapter slots
```

Runtime core records the sandbox decision and result. Hardened isolation, network policy, secrets, and resource limits belong in deployment-specific adapters.

## Media and Stream Contracts

Runtime core supports media and stream reliability metadata, not media processing:

```text
MediaArtifact: durable media ref, metadata, lineage
ArtifactLineage: source artifacts, blob refs, tool call ids, event ids
StreamChunkRef: immutable chunk ref and offset
EventStreamCheckpoint: consumer offset, watermark, partial result ref
```

Adapters own:

```text
capture
decoding
frame extraction
transcription
embedding generation
stream transport
backpressure integration
```

This keeps replay and evidence lightweight while still making multimodal workflows auditable.

## Adapter Design

Every adapter should preserve runtime invariants and pass a conformance suite where available.

Adapter categories:

```text
StateStore
BlobStore
FrameworkAdapter
Tool/MCP adapter
SandboxExecutor
Observability exporter
Policy engine
Media/stream adapter
Model provider
```

Adapters should translate external systems into AgentLedger contracts. They should not mutate evidence semantics or bypass ToolGateway for side effects.

## Testing and Release Gates

Core gates:

```text
compileall over src/tests/examples
unit tests
ResourceWarning-sensitive tests
root conformance
boundary lint
contract export and fixture diff
dependency-free example smoke
```

The checked-in contract fixture must match:

```bash
PYTHONPATH=src python3 -m agentledger contract export > /tmp/agentledger-contract.json
diff -u contracts/agentledger.runtime.v1.json /tmp/agentledger-contract.json
```

---

generated by codex cli
