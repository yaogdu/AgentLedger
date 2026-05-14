# Runtime Spec

This document defines the core runtime contract. Implementations may vary, but these concepts and invariants should remain stable.

## Core IDs

```text
session_id
run_id
step_id
event_id
tool_call_id
idempotency_key
causal_token
artifact_id
blob_ref
```

## Concept Model

### Session

A user/channel-scoped container that may span multiple runs.

Fields:

```text
session_id
user_id
tenant_id
channel
external_conversation_id
active_run_ids
last_run_id
message_refs
conversation_summary
session_variables
capability_grants
memory_refs
artifact_refs
session_version
retention_policy
```

### Run

A concrete execution instance with a frozen run spec.

Fields:

```text
run_id
session_id
run_spec_ref
status
workflow_version
agent_definition_version
policy_snapshot_id
tool_registry_version
state_version
created_at
updated_at
```

### Step / Continuation

The smallest schedulable unit.

Fields:

```text
step_id
run_id
session_id
status
owner
lease_token
lease_until
attempt
priority
required_capabilities
dependencies
budget_remaining
checkpoint_id
state_version
next_wake_condition
retry_policy
cancellation_state
```

## Step State Machine

```text
created
  -> pending
  -> claimed
  -> running
  -> waiting_tool
  -> waiting_human
  -> sleeping
  -> retry_scheduled
  -> completed
  -> failed
  -> cancelled
```

## Runtime Invariants

```text
I1. No worker may commit state without a valid lease token.
I2. Old owners must be fenced from committing stale results.
I3. Every state patch must include base_version.
I4. State commits are atomic: events, patches, checkpoints, and step status commit together.
I5. Every external_write tool must reserve a Tool Ledger row before execution.
I6. idempotency_key must be unique per logical side effect.
I7. side_effect_unknown / PENDING_VERIFICATION must not auto-retry.
I8. Replay and shadow mode must not perform real side effects.
I9. Secret values must not be stored in prompt, event payload, or artifact plaintext.
I10. High-risk tools are denied by default unless policy explicitly allows or approval is granted.
I11. Every completed step must be traceable to checkpoint and event log.
I12. Framework adapters must not leak framework-specific concepts into runtime core.
```

## State Store Interface

```python
class StateStore:
    async def create_run(self, spec): ...
    async def create_step(self, run_id, step): ...
    async def claim_step(self, worker_id, capability): ...
    async def heartbeat(self, lease_token): ...
    async def load_state(self, run_id): ...
    async def commit_state_patch(self, patch, lease_token, base_version): ...
    async def mark_step_waiting(self, step_id, condition): ...
    async def mark_step_completed(self, step_id, result): ...
    async def append_event(self, event): ...
```

Recommended implementations:

```text
Local: SQLite WAL
Production: Postgres
```

## Event Schema

Minimum event shape:

```json
{
  "event_id": "evt_...",
  "run_id": "run_...",
  "session_id": "sess_...",
  "step_id": "step_...",
  "seq": 42,
  "type": "tool_call_completed",
  "timestamp": "2026-05-14T00:00:00Z",
  "agent_role": "ExecutorAgent",
  "state_version": 7,
  "causal_token": "...",
  "payload_hash": "sha256:...",
  "payload_ref": "blob://..."
}
```

Minimum event types:

```text
run_created
run_started
step_created
step_claimed
agent_started
model_call_requested
model_call_completed
tool_call_requested
tool_permission_decided
tool_call_completed
tool_call_failed
state_patch_proposed
state_committed
artifact_created
error_raised
step_completed
run_completed
run_failed
run_cancelled
```

## Causal Token

`causal_token` should encode the minimum causality context:

```json
{
  "run_id": "run_...",
  "step_id": "step_...",
  "attempt": 2,
  "state_version": 7,
  "event_seq": 42,
  "lease_token": "lease_..."
}
```

Before executing a tool, Tool Gateway checks:

```text
lease is valid
state_version is current or accepted
attempt is not stale
event_seq belongs to the run causality chain
policy allows the action
```

## Tool Ledger

The Tool Ledger protects external side effects.

Fields:

```text
ledger_id
run_id
session_id
step_id
tool_name
tool_version
tool_call_id
idempotency_key
causal_token
request_hash
request_ref
status
external_id
response_hash
response_ref
error_type
created_at
updated_at
```

Status machine:

```text
RESERVED
  -> RUNNING
  -> SUCCEEDED
  -> FAILED_NO_EFFECT
  -> PENDING_VERIFICATION
  -> COMPENSATED
```

Rules:

```text
external_write requires ledger reservation before execution
same idempotency_key cannot create two successful effects
PENDING_VERIFICATION blocks automatic retry
replay returns archived result or stub, never real side effect
```

## Blob and Artifact Storage

Structured metadata belongs in DB. Large immutable payloads belong in Blob Store.

```text
DB:
  hashes, refs, metadata, indexes, ledger, state versions

Blob Store:
  model payloads, tool payloads, webhook bodies, artifacts, trace blobs
```

Supported backends:

```text
local filesystem
S3
MinIO
GCS / Azure Blob later
```

## Replay Contract

Deterministic replay must:

- load run spec and policy snapshot
- load state/session snapshots
- return archived model responses
- return archived tool responses
- not execute external side effects
- re-apply state transitions
- compare event/state/artifact hashes
- report divergence at event level
