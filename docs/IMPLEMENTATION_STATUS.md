# Implementation Status

Updated: 2026-06-05

This document tracks what is implemented in runtime-core, what remains planned for optional adapters, and what should stay outside runtime-core.

## Current Baseline

AgentLedger 1.3.x is a stable runtime-core line with Python as the reference implementation and Go/TypeScript/Rust covered by shared runtime-core parity gates. The 1.3 line keeps the stable runtime-core contract and adds a language-neutral, read-only Inspector companion path for evidence and runtime metadata inspection. It is suitable for:

- local use
- runtime design review
- framework adapter integration
- adapter experimentation
- reliability semantics validation
- production pilot preparation with explicit adapter boundaries

Release-scope note: 1.3.0 added Inspector as a read-only evidence/runtime metadata consumer. It can read exported evidence bundles or connect to SQLite/Postgres/MySQL AgentLedger metadata with read-only credentials and can export a static HTML debug report. 1.3.2 adds configurable redaction for Inspector JSON/HTML output. 1.3.3 adds static report navigation and read-model cross-links for timeline, tool, approval, policy, and artifact records. 1.3.4 fixes Inspector package release metadata alignment. 1.3.5 improves the packaged Inspector/static HTML layout, adds a chronological event stream, adds a read-only run index, paginates the run list, and moves table JSON/details payloads into full-width rows without changing runtime-core semantics. 1.3.6 adds `agentledger.failure.envelope.v1`, exposes normalized failure envelopes through `agentledger failure report`, and adds an Inspector Failure Envelopes panel for terminal failures, retries, waiting approvals, blocked tools, and unknown side-effect states. MySQL remains the 1.2.2 storage adapter boundary and Langfuse remains the 1.2.3 observability adapter boundary; real-service production claims still require external validation.

The runtime-core contract is stable. Optional production adapters, external infrastructure hardening, and full eval systems remain outside the stable core boundary; non-Python runtime-core baselines are verified by the shared parity gates.

Scope rule: runtime-core should stay thin but indispensable. It should own only guarantees that cannot be enforced outside the runtime boundary; mature planning, workflow, eval, observability, RAG, sandbox infrastructure, and deployment systems should integrate through adapters or consume evidence/replay outputs.

## Current Completion Boundary

For the current 1.3.x goal, "stable runtime-core plus read-only evidence consumers" means the Python reference runtime is usable, documented, tested, release-gated, and contract-frozen, with Go/TypeScript/Rust covered by runtime-core parity gates. It also means first-party adapter boundaries are packaged or importable in each ecosystem where they fit, and the Inspector can consume exported evidence across languages. It does not mean every optional production adapter or external eval integration is production-hardened in every language.

Included in this boundary:

- dependency-free local runtime and SDK
- durable state, event log, Tool Ledger, replay, evidence, normalized policy decision contract, approval, sandbox boundary, cost/failure attribution, worker loop, and conformance
- built-in minimal implementations for local storage, local blobs, simple policy, local/fail-closed sandbox modes, JSONL/OTLP JSON traces, and static debug exports
- adapter contracts and dependency-free facades for framework, storage, blob, MCP, sandbox, observability, media/stream, and worker seams
- bilingual primary documentation, architecture SVG, usage guide, release checklist, and runtime contract export

Excluded from this boundary:

- production-hardened non-Python infrastructure adapters beyond the shared runtime-core parity boundary
- exact framework-native optional packages beyond the first `agentledger-langgraph` package boundary
- full external eval system
- production-hardened infrastructure adapters and rollout playbooks
- production hardening for optional adapters beyond the v1.0 core contract

## Implemented

| Area | Current status |
|---|---|
| Local durable runtime | SQLite WAL store, local blob store, event log, Tool Ledger, AgentContext, Runtime, ToolGateway |
| Simple adoption API | `agent`, `run`, `arun`, `RunResult`, hello-world example |
| Replay and evidence | event-level replay, evidence export, evidence directory layout, static HTML evidence report, evidence diff |
| Evidence regression primitives | side-effect-free evidence checks, `evidence-regression` media/stream gates, machine-readable regression summaries, adversarial review, evidence regression checklist with media/stream evidence checks, divergence report with media/stream dimensions, golden corpus seed/add/list/check with baseline, Tool Ledger, and media/stream built-ins |
| Shadow mode | side-effect-safe candidate runs using archived Tool Ledger responses |
| Cost and budget | store-backed cost records, budget enforcement hooks, and read-only cost attribution report by run/agent/step/category/tool/model |
| Approval and policy | approval request/approve/deny flow, YAML/JSON policy checks, `PolicyRequest`, `PolicyDecision`, `PolicyFinding`, `PolicyControl`, built-in evaluator registry, decision evidence in `tool_permission_decided` |
| Scheduling semantics | leases, fencing, heartbeat, cancellation, retry policy, failure taxonomy |
| Worker loop | local worker loop, process-shaped `WorkerService`, worker conformance runner |
| Storage contracts | `StateStoreProtocol`, `BlobStoreProtocol`, SQLite migrations, DDL export |
| Adapter contracts | framework adapter base, LangGraph facade, MCP tool/context mapping, dependency-free method facades, first-party adapter package boundaries |
| Sandbox boundary | fail-closed `none`, local executor, router, external executor contracts, Docker/bubblewrap command paths, Kubernetes dry-run/gated path |
| Observability | trace JSONL export with media/stream spans, dependency-free OTLP JSON export, optional OTLP/JSON collector POST, evidence-linked audit records |
| Inspector | `agentledger.inspector.v1` single-run read model, `agentledger.inspector.runs.v1` run-index read model, `agentledger inspector run/runs/evidence`, static HTML reports, section navigation, row anchors, cross-links between related records, evidence-bundle input, read-only SQLite input, Postgres/MySQL read paths through existing adapter boundaries, configurable redaction policy, optional `agentledger-inspector` companion package |
| Reliability checks | failure injection suite, failure attribution report, conformance runners including media runtime conformance, runtime-boundary lint, scheduler facade, adversarial review, evidence regression for shell, HTTP, cloud, GitHub, and common model SDK bypasses with JSON rule-pack extension |
| Media and stream contracts | `MediaArtifact`, `MediaMetadata`, `ArtifactLineage`, `StreamChunkRef`, `EventStreamCheckpoint`, `AgentContext.create_media_artifact(...)`, `AgentContext.create_stream_checkpoint(...)`, media/stream tool schema conventions, ToolGateway/Tool Ledger media tool example, evidence indexes, replay artifact validation/counts |
| Release scaffolding | CI workflow, changelog, security policy, versioning policy, release checklist, contributor checks, bilingual documentation entrypoints, SVG architecture diagram, ResourceWarning-sensitive test gate, adapter certification checklist, adapter packaging docs/checks |

## Partially Implemented

| Area | Implemented now | Still missing |
|---|---|---|
| Postgres StateStore | DDL, optional psycopg adapter, env/CLI config, migration status/apply, schema isolation, JSONB handling, injected conformance, opt-in real-service test, CI Postgres service conformance job, `agentledger-postgres` package boundary | production rollout exercises, operational tuning, backup/restore exercise against real service |
| MySQL StateStore | DDL, optional pymysql adapter, env/CLI config, migration status/apply, JSON handling, package/import boundary, cross-language injected SQL adapter facades, `agentledger-mysql` package boundary | real-service conformance job, production rollout exercises, operational tuning, backup/restore exercise against real service |
| S3/MinIO BlobStore | optional boto3 adapter, env/CLI config, injected conformance, CLI smoke, opt-in real-service test, CI MinIO service conformance job, `agentledger-s3` package boundary | IAM/KMS/lifecycle review, large object guidance, operational hardening |
| OpenTelemetry | dependency-free OTLP JSON file export and optional OTLP/JSON collector POST, `agentledger-otel` package boundary | deployment recipe and hardened SDK adapter |
| Distributed workers | local worker loop, `WorkerService`, worker conformance, Postgres `FOR UPDATE SKIP LOCKED` path, deployment guide | hardened deployment recipe, supervision examples, real-service load/concurrency validation |
| Framework support | LangGraph facade and package boundary, method facades for LangChain/CrewAI/AutoGen/OpenAI Agents SDK/LlamaIndex/Semantic Kernel, generic adapter base, dependency-free examples, adapter conformance fixtures, adapter certification bundles | exact optional packages for every framework and framework-native smoke fixtures |
| Tool schema/catalog DX | dependency-free schema subset validation with portable composition/constraint keywords, output validation, AgentLedger manifest export, OpenAI function-tool export | framework-specific tool package adapters and optional full JSON Schema integrations |
| MCP support | descriptor-to-ToolSpec mapping, dependency-free tool/context server fixtures, context read tool adapter, examples, `agentledger-mcp` package boundary | exact MCP SDK client/server integration |
| Sandbox | contract, local/fail-closed modes, command-style Docker/bubblewrap, Kubernetes dry-run/gated execution, E2B/Firecracker slots, Docker sandbox package boundary | hardened isolation packages, secret injection policy, network policy recipes, resource limit validation |
| Retention and backup checks | non-destructive retention plan with media/stream protected refs, compaction marker, and backup readiness check including media/stream nested refs | actual compaction/snapshot job that preserves replay guarantees |
| Time travel and debug | JSON CLI timeline, state reconstruction, state diff view, `debug --json`, `--include-diffs`, `--include-states`, optional static HTML report export, Inspector static report with local navigation and cross-links | richer report layout and remote artifact browser; no long-running web app in core |

## Remaining Gaps And Preview Areas

These are either outside the stable Python runtime-core, implemented only as preview parity baselines, or still planned as optional production hardening:

- Non-Python implementations: Go, Node/TypeScript, and Rust have native runtime-core baselines under `go/`, `typescript/`, and `rust/`, with shared conformance gates and adapter boundaries. `scripts/check_language_parity.py` emits a JSON parity report, loads `contracts/conformance/runtime_semantics.v1.json` as the semantic-check authority, and runs per-language conformance CLIs for Go, TypeScript, and Rust. Remaining work is production-grade external adapter hardening and ecosystem-specific native SDK coverage, not core runtime parity.
- Production-hardened Postgres, MySQL, and S3/MinIO rollout playbooks beyond the current CI-backed real-service conformance jobs.
- Hardened OpenTelemetry SDK adapter and deployment recipe.
- Full optional framework packages for LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, and framework-native smoke matrices.
- Exact MCP SDK client/server integration beyond dependency-free fixtures.
- Larger real-world benchmark corpus beyond the current baseline, Tool Ledger, and media/stream built-in fixtures.
- Full media processing adapters for image, audio, video, frame extraction, transcription, embedding generation, and stream transport.
- Production stream backpressure/cancellation adapters beyond the current durable checkpoint artifact contract.
- Optional adapter production hardening beyond the stable v1.0 core contract. Production-ready claims for Postgres/S3/sandbox/worker/OTLP still require real services, load/concurrency checks, and restore or rollback drills; local certification manifests intentionally mark those paths as external-required.

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
3. Harden production-pilot adapter paths: Postgres, S3/MinIO, worker deployment, OTLP transport, and non-destructive retention/backup checks. These P2 claims require real services, load/concurrency checks, and restore or rollback drills; local certification manifests intentionally mark them as external-required.
4. Build richer external evidence consumers and eval adapters outside runtime-core.
5. Extend media/stream preview contracts into optional adapters only after the core reliability harness remains stable.
