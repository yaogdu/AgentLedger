# Roadmap

AgentLedger should evolve in phases. Each phase proves a reliability claim before adding more surface area.

## Capability Scope Map

To avoid a bloated runtime, every large capability is split into three lanes: core contract, optional adapter, and explicit non-goal. Runtime-core should own production execution control points, state transitions, evidence, replay hooks, CLI checks, conformance, and safe defaults. Integrations that need heavy dependencies, offline batch runners, or deployment-specific choices should remain optional adapters or separate tools.

The route is a thin but indispensable runtime core: only build what cannot be guaranteed outside the runtime boundary. If a mature system already owns a layer well, AgentLedger should expose an adapter contract and conformance suite rather than rebuilding that layer.

Most capabilities should be evaluated in three layers: core contract, built-in minimal implementation, and optional production adapter. A minimal built-in keeps the project usable out of the box; production adapters let users connect mature systems without forcing those dependencies into core.

| Capability | Runtime-core owns | Optional adapters may own | Explicit non-goals for core |
|---|---|---|---|
| Planning / Workflow | adapter contract, runtime-managed checkpoints, evidence hooks, tool boundary integration | LangGraph, CrewAI, AutoGen, LangChain, Temporal, Prefect, Airflow, custom workflow adapters | building a competing planner, graph engine, or workflow engine |
| Eval / Evidence Consumers | evidence export, replay, deterministic rerun hooks, minimal side-effect-free regression checks, conformance fixtures | external eval runners, LLM judges, benchmark datasets, CI report sinks | full offline evaluator that runs N agents x M cases, metrics service, test-case management, or long-running web app |
| Tracing / Observability | structured events, trace JSONL, OTLP/JSON export, evidence links | OpenTelemetry SDK packages, collector recipes, external trace stores | full observability suite |
| Guardrails | ToolSpec schema validation, policy checks, approvals, pre/postcondition hooks, adversarial review gates | richer policy engines, org-specific rule packs, external review workflows | business-specific governance backend |
| Tool Gateway + Sandbox | ToolGateway, Tool Ledger, idempotency, audit, sandbox executor contract, fail-closed behavior | Docker, bubblewrap, Kubernetes/gVisor, E2B, Firecracker, custom executors | owning external sandbox infrastructure |
| Memory | session memory, short-term durable state, versioned memory refs, shared findings, replayable memory events | vector stores, semantic retrieval, RAG, long-term knowledge stores | full knowledge base or semantic retrieval system |
| Session / HITL | run/session/step state machine, approval request lifecycle, audit events | external human review queues, chat/app integrations | business review backend or workflow back office |
| FinOps / Cost Control | token/call/cost records, budget enforcement hooks, cost attribution reports | provider price catalogs, finance exports, alerts | invoice or payment system |

This scope map is part of the release gate: a new feature should either fit runtime-core as a production execution reliability contract, land as an optional adapter, become a separate evidence consumer, or be documented as out of scope. The default choice is adapter or external consumer unless runtime-core is the only layer that can enforce the invariant.

## v1.0 Stable Runtime-Core Baseline

Status: implemented and release-gated in the current Python reference runtime-core.

Goals:

```text
prove durable local execution
prove Tool Ledger idempotency
prove event-level replay/evidence
prove policy/approval/sandbox boundaries
prove storage and runtime contracts are extensible
```

Current focus:

- local SQLite runtime
- Tool Ledger and replay
- evidence/export/diff and side-effect-free regression checks
- lease/fencing/cancellation
- approval and sandbox boundaries
- storage migration baseline
- language-neutral contract fixture
- documentation and release readiness

Exit criteria:

- full local test suite passes
- README quickstart works without external services
- maturity and roadmap documents are explicit
- contract and schema drift are covered by tests

## Post-v1 - Developer Experience and Framework Adoption

Goals:

```text
make adoption low-friction
prove framework-agnostic integration
make runtime bypass visible
```

Implemented in the current v1.0 core/adapters path:

- LangGraph-compatible dependency-free checkpointer facade
- dependency-free LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, and Semantic Kernel facades
- adapter conformance fixtures for dependency-free framework wrappers
- improved CLI debug timeline, state diff view, and optional static HTML debug export
- examples for plain Python, LangGraph, MCP tool/context, and command-style sandbox tools
- lint/check command for common direct tool calls and model SDK bypasses that bypass `ctx.call_tool` or the runtime model boundary, with JSON rule-pack extension
- tool schema/catalog export for framework adapters and OpenAI-compatible tool descriptors
- contract fixture docs for Rust/TypeScript/Go

Remaining planned:

- exact optional framework packages and framework-native smoke fixtures
- deeper LangGraph package compatibility around native checkpoint records
- additional runtime-boundary lint examples for common SDK bypasses

Exit criteria:

- a LangGraph example can use AgentLedger with minimal code changes
- a plain Python example remains hello-world simple
- runtime-managed tools can be registered through decorator-style APIs
- adapter wrappers can emit a certification-style conformance report
- debug CLI can emit state diffs and static HTML reports without starting a long-running process
- contract export is stable enough for external SDK prototyping

## Post-v1 - Production Adapter Hardening

Goals:

```text
support serious single-team pilots
separate core from production adapters
make recovery/audit/backup stories concrete
```

Implemented in the current v1.0 core/adapters path:

- Postgres StateStore adapter path with migration status/apply commands, schema isolation, injected conformance, native claim path, docs, and CI service conformance
- S3/MinIO BlobStore adapter path with injected conformance, docs, and CI service conformance
- schema migration commands and DDL catalog for SQLite/Postgres
- backup/restore guide and read-only backup readiness checker
- dependency-free OTLP JSON export and optional collector POST
- distributed worker guide, local `WorkerService`, and worker conformance suite
- failure injection suite
- policy and approval examples
- sandbox contracts plus Docker/bubblewrap command paths and Kubernetes/gVisor dry-run/gated path
- generic artifact retention and lineage baseline; media/stream preview contracts exist, processing adapters remain post-v1 roadmap

Remaining planned:

- production rollout exercises, operational tuning, and restore drills against real Postgres/S3-compatible services
- hardened OpenTelemetry adapter package and deployment recipe
- hardened worker supervision and real-service load/concurrency validation
- stronger policy packs and approval examples
- sandbox deployment recipes with secret, network, and resource-limit guidance
- actual compaction/snapshot job that preserves replay guarantees

Exit criteria:

- Postgres adapter passes StateStore conformance tests
- multiple workers can claim distinct steps safely
- high-risk tool flow has full audit chain
- evidence bundle can be exported for every run

## Post-v1 - Reliability Harness and Evidence Consumers

Goals:

```text
make prompt/workflow/runtime changes testable
turn evidence into regression inputs for external and local checks
```

Planned:

- richer replay/rerun divergence report with more drill-down and fixture UX
- richer repro harness UX for named golden evidence fixtures
- larger real-world benchmark corpus for historical runs beyond the current built-in seed fixtures
- cost attribution regression report
- failure attribution summaries
- richer adversarial review policy packs and release gates
- shadow mode comparison workflows
- additional real-world golden evidence fixtures
- replayable media pipeline support for frame/audio segment indexes, timeline metadata, and evidence-linked derived artifacts

Exit criteria:

- prompt/workflow changes can be shadow-run against historical evidence
- replay divergence is reported at event/state/artifact level
- media pipeline replay can reuse captured frame/segment artifacts instead of reprocessing raw media
- regression and external eval results link back to evidence bundles

## Post-v1 - Multimodal and Stream Adapters

Status: preview contracts are implemented in the Python reference runtime; processing adapters remain future work.

Goals:

```text
make long-running multimodal workflows first-class
support resumable stream processing without turning runtime-core into a media engine
```

Implemented preview:

- `MediaArtifact`, `MediaMetadata`, and `ArtifactLineage` contracts for durable media refs and derived artifact lineage
- `StreamChunkRef` and `EventStreamCheckpoint` contracts for resumable stream cursors
- `AgentContext.create_media_artifact(...)` and `AgentContext.create_stream_checkpoint(...)`
- evidence summary counts for media artifacts and stream checkpoints
- evidence bundle indexes for media artifacts and stream checkpoints
- replay validation/counts for archived media and stream artifacts
- adversarial review checks for media artifact refs and stream checkpoint offsets
- evidence diff and divergence dimensions for media artifacts and stream checkpoints
- eval/regression gates for media artifacts and stream checkpoints
- backup readiness and retention protected-ref accounting for nested media/stream blob refs
- trace spans for media artifacts and stream checkpoints
- tool schema conventions for `audio.transcribe`, `video.extract_frames`, `frame.describe`, `video.summarize`, `stream.consume`, and `stream.emit`
- ToolGateway/Tool Ledger example for an injected `video.extract_frames` executor
- media runtime conformance runner for evidence, replay, eval, review, trace, and Tool Ledger chains
- language-neutral contract entries for media and stream artifact schemas

Remaining planned:

- optional adapters for image, audio, video, frame extraction, transcription, embedding generation, and stream transport
- production backpressure/cancellation integration for stream consumers
- richer evidence cross-links for frame indexes, segment timelines, transcripts, stream offsets, and derived artifact lineage
- adapter-level replay semantics that distinguish reusing captured media artifacts from re-running expensive media tools
- compatibility hardening for media/stream contracts before any v1.0 stability promise

Exit criteria:

- agents can process audio/video through runtime-managed tools while preserving durable refs, metadata, and lineage
- stream consumers can resume from a durable offset/watermark after worker restart
- evidence bundles can explain which frame/segment/transcript artifacts produced a final result
- media and stream support remain adapter-driven; runtime-core stores refs, metadata, lineage, and checkpoints, not heavy codecs

## v1.0 - Stable Runtime Contract

Status: implemented for the Python runtime-core contract.

Stable in v1.0:

```text
AgentContext API boundary
runtime contract JSON
event/evidence schema
Tool Ledger semantics
StateStore and BlobStore conformance suites
versioning and migration policy
security policy and threat model
adapter certification checklist
```

The media/stream schema is intentionally still preview inside the v1 contract. It is covered by evidence and conformance checks, but it should not be treated as a fully frozen media processing API until the adapter work matures.

Release gates:

- critical runtime invariants are documented and tested
- stable storage and blob adapters pass conformance tests
- high-risk tool flows have audit, approval, ledger, replay, and sandbox boundaries
- docs clearly distinguish stable, preview, experimental, skeleton, and roadmap features

## Multi-language Track

The language plan should not block Python progress, but it must prevent semantic drift.

| Language | First milestone | Later milestone |
|---|---|---|
| Python | reference runtime | production runtime for Python users |
| TypeScript | protocol client and worker SDK | TS framework adapters |
| Rust | runtime primitives or sandbox worker | high-performance runtime engine |
| Go | worker/infra adapter | Kubernetes/controller-friendly deployment services |

All language implementations should target `contracts/agentledger.runtime.v1.json` and equivalent conformance fixtures.
