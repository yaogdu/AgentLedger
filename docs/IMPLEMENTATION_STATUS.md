# Implementation Status

Updated: 2026-05-18

This document tracks what is implemented in the Python reference runtime, what remains planned, and what should stay outside runtime-core.

## Current Baseline

AgentLedger 1.0.1 is a stable runtime-core release with Python as the reference implementation and Go/TypeScript/Rust covered by shared runtime-core parity gates. It still has selected preview/experimental concrete adapter paths. It is suitable for:

- local use
- runtime design review
- framework adapter integration
- adapter experimentation
- reliability semantics validation
- production pilot preparation with explicit adapter boundaries

The runtime-core contract is stable. Optional production adapters, external infrastructure hardening, and full eval systems remain outside the stable core boundary; non-Python runtime-core baselines are verified by the shared parity gates.

Scope rule: runtime-core should stay thin but indispensable. It should own only guarantees that cannot be enforced outside the runtime boundary; mature planning, workflow, eval, observability, RAG, sandbox infrastructure, and deployment systems should integrate through adapters or consume evidence/replay outputs.

## Current Python Completion Boundary

For the current 1.0.1 goal, "stable runtime-core" means the Python reference runtime is usable, documented, tested, release-gated, contract-frozen, and covered by Go/TypeScript/Rust runtime-core parity gates. It does not mean every optional production adapter or external eval integration is shipped in every language.

Included in this boundary:

- dependency-free local runtime and SDK
- durable state, event log, Tool Ledger, replay, evidence, policy, approval, sandbox boundary, cost/failure attribution, worker loop, and conformance
- built-in minimal implementations for local storage, local blobs, simple policy, local/fail-closed sandbox modes, JSONL/OTLP JSON traces, and static debug exports
- adapter contracts and dependency-free facades for framework, storage, blob, MCP, sandbox, observability, media/stream, and worker seams
- bilingual primary documentation, architecture SVG, usage guide, release checklist, and runtime contract export

Excluded from this boundary:

- non-Python implementations
- exact framework-native optional packages
- full external eval system
- production-hardened infrastructure adapters and rollout playbooks
- production hardening for optional adapters beyond the v1.0 core contract

## Implemented

| Area | Current status |
|---|---|
| Local durable runtime | SQLite WAL store, local blob store, event log, Tool Ledger, AgentContext, Runtime, ToolGateway |
| Simple adoption API | `agent`, `run`, `arun`, `RunResult`, hello-world example |
| Replay and evidence | event-level replay, evidence export, evidence directory layout, static HTML evidence report, evidence diff |
| Evidence regression primitives | side-effect-free evidence checks, `evidence-regression` media/stream gates, adversarial review, evidence regression checklist with media/stream evidence checks, divergence report with media/stream dimensions, golden corpus seed/add/list/check with baseline, Tool Ledger, and media/stream built-ins |
| Shadow mode | side-effect-safe candidate runs using archived Tool Ledger responses |
| Cost and budget | store-backed cost records, budget enforcement hooks, and read-only cost attribution report by run/agent/step/category/tool/model |
| Approval and policy | approval request/approve/deny flow, YAML/JSON policy checks |
| Scheduling semantics | leases, fencing, heartbeat, cancellation, retry policy, failure taxonomy |
| Worker loop | local worker loop, process-shaped `WorkerService`, worker conformance runner |
| Storage contracts | `StateStoreProtocol`, `BlobStoreProtocol`, SQLite migrations, DDL export |
| Adapter contracts | framework adapter base, LangGraph facade, MCP tool/context mapping, dependency-free method facades |
| Sandbox boundary | fail-closed `none`, local executor, router, external executor contracts, Docker/bubblewrap command paths, Kubernetes dry-run/gated path |
| Observability | trace JSONL export with media/stream spans, dependency-free OTLP JSON export, optional OTLP/JSON collector POST, evidence-linked audit records |
| Reliability checks | failure injection suite, failure attribution report, conformance runners including media runtime conformance, runtime-boundary lint, scheduler facade, adversarial review, evidence regression for shell, HTTP, cloud, GitHub, and common model SDK bypasses with JSON rule-pack extension |
| Media and stream contracts | `MediaArtifact`, `MediaMetadata`, `ArtifactLineage`, `StreamChunkRef`, `EventStreamCheckpoint`, `AgentContext.create_media_artifact(...)`, `AgentContext.create_stream_checkpoint(...)`, media/stream tool schema conventions, ToolGateway/Tool Ledger media tool example, evidence indexes, replay artifact validation/counts |
| Release scaffolding | CI workflow, changelog, security policy, versioning policy, release checklist, contributor checks, bilingual documentation entrypoints, SVG architecture diagram, ResourceWarning-sensitive test gate, adapter certification checklist |

## Partially Implemented

| Area | Implemented now | Still missing |
|---|---|---|
| Postgres StateStore | DDL, optional psycopg adapter, env/CLI config, migration status/apply, schema isolation, JSONB handling, injected conformance, opt-in real-service test, CI Postgres service conformance job | production rollout exercises, operational tuning, backup/restore exercise against real service |
| S3/MinIO BlobStore | optional boto3 adapter, env/CLI config, injected conformance, CLI smoke, opt-in real-service test, CI MinIO service conformance job | IAM/KMS/lifecycle review, large object guidance, operational hardening |
| OpenTelemetry | dependency-free OTLP JSON file export and optional OTLP/JSON collector POST | deployment recipe and hardened adapter package |
| Distributed workers | local worker loop, `WorkerService`, worker conformance, Postgres `FOR UPDATE SKIP LOCKED` path, deployment guide | hardened deployment recipe, supervision examples, real-service load/concurrency validation |
| Framework support | LangGraph facade, method facades for LangChain/CrewAI/AutoGen/OpenAI Agents SDK/LlamaIndex/Semantic Kernel, generic adapter base, dependency-free examples, adapter conformance fixtures | exact optional packages for each framework and framework-native smoke fixtures |
| Tool schema/catalog DX | dependency-free schema subset validation with portable composition/constraint keywords, output validation, AgentLedger manifest export, OpenAI function-tool export | framework-specific tool package adapters and optional full JSON Schema integrations |
| MCP support | descriptor-to-ToolSpec mapping, dependency-free tool/context server fixtures, context read tool adapter, examples | exact MCP SDK client/server integration |
| Sandbox | contract, local/fail-closed modes, command-style Docker/bubblewrap, Kubernetes dry-run/gated execution, E2B/Firecracker slots | hardened isolation packages, secret injection policy, network policy recipes, resource limit validation |
| Retention and backup checks | non-destructive retention plan with media/stream protected refs, compaction marker, and backup readiness check including media/stream nested refs | actual compaction/snapshot job that preserves replay guarantees |
| Time travel and debug | JSON CLI timeline, state reconstruction, state diff view, `debug --json`, `--include-diffs`, `--include-states`, optional static HTML report export | richer report layout and artifact cross-links; no long-running web app in core |

## Remaining Gaps And Preview Areas

These are either outside the stable Python runtime-core, implemented only as preview parity baselines, or still planned as optional production hardening:

- Non-Python implementations: Go, Node/TypeScript, and Rust have dependency-free preview native runtime baselines under `go/`, `typescript/`, and `rust/`. All three execute shared runtime-core parity tests for `runtime_baseline.v1.json`, `local_persistence.v1.json`, `local_blob_store.v1.json`, `tool_schema_validation.v1.json`, `worker_service.v1.json`, `policy_approval_sandbox.v1.json`, `cost_failure_attribution.v1.json`, `media_stream_artifacts.v1.json`, `evidence_consumers.v1.json`, `static_debug_html.v1.json`, `ops_readiness.v1.json`, `storage_schema.v1.json`, `mcp_adapters.v1.json`, `framework_adapters.v1.json`, `otlp_trace_export.v1.json`, `simple_api.v1.json`, and `boundary_lint.v1.json`, `scheduler.v1.json`, `adversarial_review.v1.json`, `evidence_regression.v1.json`, `failure_injection.v1.json`, `shadow.v1.json`, `repro.v1.json`, `time_travel.v1.json`, `optional_adapters.v1.json`, covering leases, cancellation, Tool Ledger idempotency, policy denial, approval pause/resume, sandbox fail-closed behavior, cost/budget accounting, failure attribution, and media/stream artifact references, trace spans, evidence diff, divergence, debug summaries, static HTML debug export, ops readiness planning, storage schema helpers, MCP-style in-memory adapters, dependency-free framework adapters, OTLP JSON trace export, and the simple hello-world API, and Rust local snapshot persistence. `scripts/check_language_parity.py` can emit a JSON parity report, loads `contracts/conformance/runtime_semantics.v1.json` as the semantic-check authority, and now runs preview per-language conformance CLIs for Go, TypeScript, and Rust, including fixture-aligned semantic smokes for state/evidence/replay, local persistence/reopen, local blob store, tool schema validation, worker service, Tool Ledger retry, policy/approval/sandbox, cost/failure attribution, and media/stream artifact refs, trace spans, evidence diff, divergence, debug summaries, static HTML debug export, ops readiness planning, storage schema helpers, MCP-style in-memory adapters, dependency-free framework adapters, OTLP JSON trace export, and the simple hello-world API; SDK/client-only packages may appear first but will not count as runtime-ready.
- Production-hardened Postgres and S3/MinIO rollout playbooks beyond the current CI-backed real-service conformance jobs.
- Hardened OpenTelemetry adapter package and deployment recipe.
- Full optional framework packages for LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, and Semantic Kernel.
- Exact MCP SDK client/server integration beyond dependency-free fixtures.
- Larger real-world benchmark corpus beyond the current baseline, Tool Ledger, and media/stream built-in fixtures.
- Full media processing adapters for image, audio, video, frame extraction, transcription, embedding generation, and stream transport.
- Production stream backpressure/cancellation adapters beyond the current durable checkpoint artifact contract.
- Optional adapter production hardening beyond the stable v1.0 core contract.

## Non-goals For Runtime Core

The following should not be implemented inside runtime-core:

- business data schemas
- application-specific identity, commerce, or domain workflows
- long-running web application
- database drop/truncate/reset helpers for user data
- cloud resource provisioning
- replacing agent frameworks, workflow engines, Ray, Temporal, or Kubernetes

Runtime-core should expose durable contracts, conformance suites, adapter seams, CLI tools, and safe defaults. Backend-specific execution and deployment policy should live in optional packages or user-provided adapters.

Large capabilities such as Eval, Observability, Guardrails, Tool Gateway/Sandbox, Memory, Session/HITL, and Cost Control must follow the `docs/ROADMAP.md` capability scope map: core owns production execution reliability contracts, evidence, and replay hooks; optional adapters or separate tools own offline batch runners and heavy integrations; runtime-core must not grow into a full application suite.

## Next Implementation Order

1. Keep v1.0 runtime-core compatibility protected by release gates, contract snapshots, and conformance suites.
2. Improve adoption without bloating core: exact optional framework packages, additional framework-native smoke fixtures, and project-specific runtime-boundary lint, scheduler facade, adversarial review, evidence regression examples.
3. Harden production-pilot adapter paths: Postgres, S3/MinIO, worker deployment, OTLP transport, and non-destructive retention/backup checks.
4. Build richer external evidence consumers and eval adapters outside runtime-core.
5. Extend media/stream preview contracts into optional adapters only after the core reliability harness remains stable.
