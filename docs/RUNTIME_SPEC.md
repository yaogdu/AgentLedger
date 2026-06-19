# Runtime Spec

This document defines the core runtime contract. Implementations may vary, but these concepts and invariants should remain stable.

Python is the v1.x reference implementation. Rust, TypeScript, and Go implementations target the language-neutral contract exported by `agentledger contract export` and the golden fixture at `contracts/agentledger.runtime.v1.json`.


## Progressive Disclosure API

The runtime exposes a simple API for adoption and demos:

```python
from agentledger import agent, run

@agent
def hello(ctx):
    return "hello world"

result = run(hello)
```

This API is intentionally a thin layer over the same runtime state machine:

```text
SimpleAgent -> Runtime.create_run -> claim_step -> AgentContext -> commit_state_patch -> RunResult
```

It must not bypass leases, event logging, state version checks, policy, tool ledger, approval, sandbox, or evidence export.

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
environment
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
I10. High-risk tools are denied by default unless policy explicitly allows or a store-backed approval gate grants execution.
I11. Every completed step must be traceable to checkpoint and event log.
I12. Framework adapters must not leak framework-specific concepts into runtime core.
I13. Approval-required tools must move the step to waiting_human and must not execute until approved.
I14. Sandbox-required tools must emit sandbox boundary events and include executor/isolation metadata even when the executor is local/no-isolation.
I14a. If sandbox is disabled or a named executor is missing, required sandbox execution must fail closed by default.
I15. Retention/compaction must be non-destructive by default and evidence-first before physical deletion.
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
Production: Postgres or MySQL through optional adapters
```

The built-in SQLite backend owns AgentLedger runtime metadata only. It auto-applies dependency-free migrations and records them in `schema_migrations`; ordinary hello-world users should not need to inspect or manage DDL. Storage adapters may choose different physical schemas, but they must preserve the StateStore invariants and pass conformance tests.

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
model_call_failed
tool_call_proposed
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

## Runtime Model Evidence Boundary

AgentLedger records model evidence; it does not route model traffic or replace provider SDKs, LiteLLM/new-api/one-api, or enterprise model gateways.

The portable model evidence schema is `agentledger.model.evidence.v1`. It supports:

```text
model_call_requested   archived request, provider, model, metadata
model_call_completed   archived response, usage, total_usd, metadata
model_call_failed      timeout/rate-limit/malformed-output/provider-error evidence
tool_call_proposed     model-proposed tool name/args before ToolGateway execution
```

The execution model is:

```text
user code / framework / provider SDK / external gateway
  -> performs or attempts the model call
  -> records request/response/failure evidence in AgentLedger
  -> optionally records the tool call proposed by the model
  -> executes real tools through ToolGateway / Tool Ledger
```

`model_call_failed` participates in the failure lifecycle as category `model`. Runtime-core records cost/failure/replay evidence for model calls, but provider timeout, retry, fallback, key management, routing, and pricing catalogs remain external adapter or application responsibilities.

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

## Tool Schema and Catalog

`ToolSpec` is the runtime-owned tool contract. It is not a planner and does not replace framework-specific tool abstractions. It records the metadata needed for governance:

```text
name
version
description
input_schema
output_schema
side_effect
risk_level
idempotency_required
approval_required
sandbox_required
sandbox_executor
sandbox_policy
```

Runtime-core includes a dependency-free JSON Schema subset validator for `input_schema` and `output_schema`. It supports the portable contract keywords needed by runtime adapters:

```text
type
required
properties
additionalProperties=false
items
enum
const
minLength / maxLength / pattern
minimum / maximum / exclusiveMinimum / exclusiveMaximum / multipleOf
minItems / maxItems / uniqueItems
minProperties / maxProperties
anyOf / oneOf / allOf / not
```

Stronger or framework-specific validation can still live in optional adapter packages. The core rule is that every tool call entering `ToolGateway` is validated before execution and every declared output schema is validated before response archival.

`ToolRegistry.manifest()` exports the AgentLedger catalog shape. `ToolRegistry.openai_tools()` exports an OpenAI function-tool compatible shape for adapters that need to expose runtime-managed tools to model SDKs. The stable core tool-use execution path is `ctx.call_tool(...)`.



## Sandbox Configuration

Sandbox is a capability boundary, not one hard-coded product. Core accepts a `SandboxConfig` and routes `sandbox_required=True` tools to a named executor.

```yaml
default_executor: local
fail_closed: true
executors:
  local:
    type: local
  none:
    type: none
  bubblewrap:
    type: bubblewrap
  docker:
    type: docker
  k8s-gvisor:
    type: kubernetes
    runtime_class: gvisor
    namespace: agentledger-sandbox
    image: agentledger/sandbox:latest
    dry_run: true
    kubectl: kubectl
    cleanup: true
    wait_timeout_seconds: 60
  firecracker:
    type: firecracker
tools:
  shell.exec:
    required: true
    executor: bubblewrap
  untrusted_code.run:
    required: true
    executor: k8s-gvisor
```

Built-in external adapters are dependency-free contract adapters. They produce manifests and fail closed until a real backend package, command execution opt-in, or custom executor is injected.

Command-style sandbox execution uses `_sandbox_command: list[str]`. The runtime rejects string commands unless `allow_shell=true`; this keeps the default path argv-based and auditable.

Kubernetes sandbox execution is Job-based. In `dry_run: true`, the executor validates the command and returns the generated `batch/v1` Job manifest without contacting a cluster. With `allow_command_execution: true` and `dry_run: false`, the executor uses `kubectl create -f <job.json>`, waits for completion by default, captures `kubectl logs job/<name>`, and deletes the Job when `cleanup: true`. gVisor/Kata-style isolation is selected through `runtime_class`; network-deny intent is recorded as labels/annotations and should be enforced by a separately managed NetworkPolicy.

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

## Media and Event Stream Artifact Contract

Media and stream support is an artifact contract, not a codec or streaming engine. Runtime-core stores durable manifests, refs, metadata, lineage, and stream cursors. Adapter packages or user tools own transcription, frame extraction, encoding, transport, and model-specific media processing.

Agent-facing helpers:

```python
await ctx.create_media_artifact(
    "frame-0001",
    "frame",
    uri="s3://media/run-1/frame-0001.jpg",
    media_metadata=MediaMetadata(kind="frame", mime_type="image/jpeg", width=1920, height=1080),
    lineage=ArtifactLineage(source_blob_refs=["s3://media/run-1/video.mp4"]),
)

await ctx.create_stream_checkpoint(
    "camera-stream-checkpoint",
    stream_id="camera-1",
    consumer_id="vision-agent",
    offset=42,
    watermark=12.5,
)
```

Media artifact manifests use `schema_version=agentledger.media.v0` and support these kinds:

```text
image
audio
video
frame
audio_segment
video_segment
transcript
embedding
derived
```

Portable media metadata fields:

```text
kind
mime_type
codec
duration_seconds
fps
sample_rate_hz
width
height
channels
timestamp_start_seconds
timestamp_end_seconds
frame_index
segment_index
transcript_language
embedding_model
source_uri
checksum
extra
```

Lineage fields:

```text
source_artifact_ids
source_blob_refs
tool_call_ids
event_ids
metadata
```

Event stream checkpoint manifests use `schema_version=agentledger.stream.v0` and store:

```text
stream_id
consumer_id
offset
watermark
chunk
partial_result_ref
backpressure
metadata
```

Rules:

```text
runtime-core stores immutable refs and JSON metadata, not raw media bytes
media tools should archive expensive derived outputs as artifacts
stream consumers should persist offsets/watermarks before acknowledging irreversible progress
replay should reuse captured media/stream artifacts instead of re-running expensive tools
```

Runtime-core also ships dependency-free tool schema conventions for adapters that want a stable catalog before binding to a concrete media backend:

```text
audio.transcribe
video.extract_frames
frame.describe
video.summarize
stream.consume
stream.emit
```

These conventions are exported by `media_tool_specs()` / `register_media_tool_conventions(...)`, `agentledger tools manifest --example examples/media_stream`, and the language-neutral runtime contract. The default functions intentionally raise `NotImplementedError`; real processing must be injected by an adapter or user tool implementation.

When an injected media executor is registered, calls still go through the normal runtime path:

```text
ctx.call_tool("video.extract_frames", ...)
  -> ToolGateway validation
  -> policy decision
  -> Tool Ledger reservation
  -> executor call
  -> archived response
  -> media artifact manifest created through AgentContext
  -> evidence media_artifacts index
```

## Replay Contract

Deterministic replay must:

- load run spec and policy snapshot
- load state/session snapshots
- return archived model responses
- return archived tool responses
- validate archived artifact refs, including media manifests and stream checkpoints
- not execute external side effects
- re-apply state transitions
- compare event/state/artifact hashes
- report divergence across event, state, artifact, ledger, cost, and model-output dimensions


## Evidence Bundle

Evidence bundles are replay-ready and external-eval-ready snapshots of a run. They include:

```text
run metadata
initial_state
steps
events with decoded payloads
tool ledger rows
artifacts
media_artifacts
stream_checkpoints
cost records
summary
final_state
bundle_hash
```

Rules:

```text
Evidence export must not call tools or model providers.
Evidence export should preserve enough raw payload information for replay, external eval consumers, and audit.
Bundle hash excludes the bundle_hash field itself.
```

## Budget and Cost Attribution

Cost records are append-only accounting events linked to run/session/step.

Fields:

```text
cost_id
run_id
session_id
step_id
category
name
amount
unit
metadata_json
created_at
```

Current categories include `tool`, `tool_shadow`, and `model`.

`CostAttributionReporter` builds a read-only report from `cost_records` and the event log:

```text
total
by_agent
by_step
by_category
by_name
```

The report attributes tool calls, model tokens, and USD amounts without mutating runtime state:

```bash
PYTHONPATH=src python3 -m agentledger cost report <run_id>
```

## Shadow Mode

Shadow mode runs candidate agent logic against a source run's archived evidence. It may execute local pure code, but managed side-effect tools must be resolved from the source run's successful Tool Ledger rows. If no archived response exists, the runtime blocks the side effect.

```text
I13. Shadow mode must not create external side effects.
I14. Shadow side-effect responses must reference source evidence.
```


## Scheduler and Lease Recovery

The scheduler control plane owns worker-independent lifecycle operations. The local implementation exposes these through `RuntimeScheduler` and `SQLiteStore`:

```text
heartbeat(step_id, lease_token, lease_seconds)
recover_expired_leases()
cancel_run(run_id, reason)
status(run_id)
```

Rules:

```text
A heartbeat requires a valid running lease.
Expired leases move running steps back to retry_scheduled and fence the old lease token.
A cancelled run clears active owners and lease tokens, and stale workers cannot commit.
Recovering an expired lease emits lease_expired and step_retry_scheduled events.
Cancelling a run emits run_cancel_requested, step_cancelled, and run_cancelled events.
```

## Retry Policy and Failure Taxonomy

Each step stores a JSON retry policy. The stable local policy supports:

```json
{ "max_attempts": 3 }
```

Retry behavior:

```text
attempt < max_attempts  -> retry_scheduled
attempt >= max_attempts -> failed
```

Failure classification emits `failure_classified` before retry or fail transitions. Current categories are intentionally small: `retryable_agent_error`, `non_retryable_agent_error`, `timeout`, and `unhandled_exception`.

Additional invariants:

```text
I15. Expired or cancelled leases must fence old worker commits.
I16. Retry exhaustion must transition the step and run to failed.
I17. Cancellation must be represented in the event log, not just as a status write.
```


## Worker Loop

`LocalWorker` is the local development shape for future worker pools. It repeatedly:

```text
recover expired leases
check terminal/idle state
claim one step through Runtime.run_once
record attempts/successes
stop on terminal status, idle, or max_iterations
```

The worker loop does not own scheduling invariants. It calls `RuntimeScheduler` and `Runtime.run_once`; the store remains the source of truth for leases, cancellation, retry, and status.

`WorkerService` is the process-shaped reference loop for deployment adapters. It repeatedly runs one `LocalWorker` iteration, tracks attempts and recovered leases, backs off on idle polls, and can stop on:

```text
terminal_status
idle
max_loops
request_stop(reason)
SIGINT/SIGTERM when signal handlers are installed
```

The service is intentionally single-process and dependency-free. Horizontal scaling should start multiple worker processes against a StateStore that passes `WorkerConformanceRunner`; runtime-core does not hide database provisioning, queues, or orchestration behind this loop.

## Store Conformance

`StateStoreConformanceRunner` defines the minimum behavioral contract every StateStore adapter must pass:

```text
create_claim_commit
stale_lease_rejected
expired_lease_recovered
cancel_fences_worker
```

`WorkerConformanceRunner` defines the minimum behavioral contract every worker-capable backend must pass:

```text
multi_worker_claims_distinct_steps
heartbeat_fences_wrong_owner
recovery_fences_previous_owner
```

Future Postgres, MySQL, or remote stores should run both suites before being considered compatible with runtime-core worker pools.

`MediaRuntimeConformanceRunner` defines the executable smoke contract for media/stream runtime semantics:

```text
media_evidence_replay_chain
media_tool_ledger_chain
```

The root `agentledger conformance` command includes this suite alongside state, blob, and worker checks.

## Framework Adapter Conformance

`FrameworkAdapterConformanceRunner` defines the minimum smoke contract for dependency-free framework wrappers:

```text
run_spec_maps_adapter
runtime_run_once_completes
evidence_export_works
```

The CLI includes local fixture kinds for `python-function`, `langgraph-node`, `langchain`, `crewai`, `autogen`, `openai-agents`, `llamaindex`, and `semantic-kernel`:

```bash
PYTHONPATH=src python3 -m agentledger adapter conformance --kind langchain
```

Exact optional adapter packages should add framework-native tests on top of this baseline.

## Failure Injection

`FailureInjectionSuite` runs executable reliability probes against a local runtime root:

```text
side_effect_crash      -> worker crash after external side effect must not duplicate external writes
retry_exhaustion       -> retry policy exhaustion must fail the step/run with failure events
lease_fencing          -> expired old lease must be fenced after recovery
cancellation_fencing   -> cancelled run must fence old workers and block new claims
```

CLI:

```bash
PYTHONPATH=src python3 -m agentledger failure inject --scenario all
PYTHONPATH=src python3 -m agentledger failure inject --scenario lease_fencing
```

The suite is a local reliability harness, not a destructive chaos tool. It creates its own runtime runs under `<root>/failure-injection` and does not drop or clean user databases.

## Failure Attribution

`FailureAttributionReporter` builds a read-only summary from steps, Tool Ledger rows, approval requests, and failure-related events. It does not replay a run or call tools.

The report includes:

```text
run_status
summary counts
root_causes
failed_steps
pending_verification
pending_approvals
failure_events
```

CLI:

```bash
PYTHONPATH=src python3 -m agentledger failure report <run_id>
```

## Evidence Directory Export

Evidence bundles can be exported as a single JSON file or as a directory layout:

```text
manifest.json
bundle.json
events.jsonl
summary.json
steps.json
tool_ledger.json
cost_records.json
artifacts.json
media_artifacts.json
stream_checkpoints.json
final_state.json
```

The directory layout is intended for CI artifacts, external eval harnesses, shadow regression, and human review.

Evidence can also be exported as a single static HTML report for local incident review:

```bash
PYTHONPATH=src python3 -m agentledger evidence <run_id> --html ./evidence.html
```

The HTML report summarizes run metadata, final state, steps, Tool Ledger, approvals, artifacts, media artifacts, stream checkpoints, costs, and events. It is a static file and does not start a long-running process.


## Time Travel Debugging

`TimeTravelDebugger` reconstructs committed state from the event log without calling models or tools. It treats these events as state mutations:

```text
run_created -> initial_state
state_committed -> JSON merge patch
system_state_patch_applied -> JSON merge patch
```

Other events remain visible in the timeline but do not mutate reconstructed state. The CLI can inspect the whole timeline or select a specific event sequence:

```bash
PYTHONPATH=src python3 -m agentledger timetravel <run_id>
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --at-seq 5
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --include-diffs
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --include-states
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --include-diffs --include-states --html ./time-travel.html
PYTHONPATH=src python3 -m agentledger debug <run_id> --json --include-diffs
PYTHONPATH=src python3 -m agentledger debug <run_id> --include-diffs --html ./debug.html
```

This is a debugger, not a replay executor. It is side-effect safe because it reads only durable events and blob refs. The HTML mode writes a single static file for incident review and does not start a long-running process.


## Evidence Diff

`EvidenceDiffer` compares two evidence bundles or exported bundle paths. It reports changes across:

```text
bundle_hash
summary
final_state
event_types
tool_ledger statuses
media_artifacts
stream_checkpoints
cost_summary
```

This is the first building block for replay diff, shadow regression, and prompt/workflow change safety.

## Evidence Regression Checks

`EvidenceRegressionRunner.evaluate_regression` is a side-effect-free evidence consumer that turns evidence diffs into release gates. A golden evidence bundle represents the expected behavior for a known run, and a current evidence bundle represents a new prompt, workflow, model, policy, or runtime version.

The regression gate can enforce:

```text
final_state_regression
event_type_regression
tool_ledger_status_regression
media_artifact_regression
stream_checkpoint_regression
max_total_usd_delta
```

The CLI accepts either single-file evidence bundles or evidence directory exports:

```bash
PYTHONPATH=src python3 -m agentledger evidence-regression ./golden.json ./current-evidence-dir
PYTHONPATH=src python3 -m agentledger evidence-regression ./golden.json ./current.json --max-total-usd-delta 0.05
PYTHONPATH=src python3 -m agentledger evidence-regression ./golden.json ./current.json --allow-final-state-changes
PYTHONPATH=src python3 -m agentledger evidence-regression ./golden.json ./current.json --allow-media-artifact-changes --allow-stream-checkpoint-changes
```

Evidence regression checks must remain side-effect free and outside the production execution path. They read evidence only, produce a structured report, and exit non-zero when a required invariant fails. Full offline evaluation across many agents and cases should live outside runtime-core and consume evidence/replay contracts.

## Adversarial Review Checklist

`AdversarialReviewRunner` is a read-only pre-release checklist over an evidence bundle. It looks for common production blockers and review warnings before a prompt, workflow, policy, adapter, or runtime change is accepted.

Current checks:

```text
no_failed_steps
no_pending_verification
no_pending_approvals
completed_steps_have_completion_events
ledger_statuses_known
event_sequence_contiguous
artifacts_have_blob_refs
media_artifacts_have_refs
stream_checkpoints_have_offsets
high_risk_approvals_decided
no_blocking_failure_events
max_total_usd
```

CLI:

```bash
PYTHONPATH=src python3 -m agentledger review checklist <run_id>
PYTHONPATH=src python3 -m agentledger review checklist <run_id> --max-total-usd 0.10 --fail-on-risk
```

The checklist does not mutate runtime data. With `--fail-on-risk`, blocker failures exit non-zero and can be used as a release gate.

## Divergence Report

`DivergenceReporter` compares two evidence bundles without replaying or calling tools. It is meant for replay/rerun and prompt/workflow-change investigations where users need to see which runtime dimensions changed.

Dimensions:

```text
events
state
artifacts
media_artifacts
stream_checkpoints
ledger
cost
model_outputs
```

CLI:

```bash
PYTHONPATH=src python3 -m agentledger divergence <left_run_id> <right_run_id>
PYTHONPATH=src python3 -m agentledger divergence ./golden.json ./current-dir --evidence-paths
PYTHONPATH=src python3 -m agentledger divergence ./golden.json ./current.json --evidence-paths --fail-on-divergence
```

Divergence reports are read-only and can be used as a release gate with `--fail-on-divergence`.

## Golden Evidence Corpus

`GoldenCorpus` is a file-based evidence fixture harness for storing named replay/regression inputs:

```bash
PYTHONPATH=src python3 -m agentledger corpus seed minimal-success
PYTHONPATH=src python3 -m agentledger corpus seed --list-builtins
PYTHONPATH=src python3 -m agentledger corpus add side-effect ./golden.json
PYTHONPATH=src python3 -m agentledger corpus list
PYTHONPATH=src python3 -m agentledger corpus check side-effect ./current-evidence-dir
```

The corpus stores a copy of `bundle.json` and a small manifest with bundle hash and metadata. `corpus seed` installs curated built-in fixtures such as `minimal-success`, `tool-ledger-success`, and `media-stream-checkpoint`; `corpus add` stores user-provided evidence. `corpus check` reuses the same regression checks as `evidence-regression`, so it remains side-effect free and never calls tools or model providers.

## Structured Trace Export

`TraceExporter` turns evidence events into JSONL spans. The exporter is dependency-free and intentionally not a full OpenTelemetry SDK. Each event becomes one span with:

```text
trace_id = run_id
span_id = evt-<seq>
name = event type
attributes.agentledger.* = run/session/step/seq/state/payload metadata
```

Evidence media artifacts and stream checkpoints also become spans:

```text
name = media_artifact
attributes.agentledger.media_kind / media_uri / media_content_ref

name = stream_checkpoint
attributes.agentledger.stream_id / consumer_id / stream_offset / stream_watermark
```

`OTLPTraceExporter` translates the same evidence spans into OTLP/JSON shape without importing OpenTelemetry SDKs. It is meant for file-based export, CI artifacts, and optional dependency-free OTLP/JSON collector POST experiments:

```bash
PYTHONPATH=src python3 -m agentledger trace <run_id> --format otlp --out trace.otlp.json
```

OTLP file export is side-effect free. Collector POST is explicit opt-in through `trace --format otlp --otlp-endpoint ...` or `OTLPTraceExporter.post_json(...)` and must not affect runtime state commits.

## Postgres Store Skeleton

`PostgresStore` currently provides schema DDL from the storage migration catalog, an explicit optional-dependency boundary, and a psycopg-backed adapter path that can be conformance-tested through connection injection. A hardened production adapter should add real-service integration tests, operational migration rollout, and backup/restore guidance. Runtime-core must not require a Postgres driver for local use.

## MySQL Store Skeleton

`MySQLStore` provides schema DDL from the storage migration catalog, an explicit optional-dependency boundary, and a pymysql-backed adapter path. Go, TypeScript, and Rust expose the same MySQL migration contract through injected SQL clients. A hardened production adapter should add real-service integration tests, operational migration rollout, and backup/restore guidance. Runtime-core must not require a MySQL driver for local use.

---

generated by codex cli
