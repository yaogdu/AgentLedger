# Implementation Plan

This is a historical implementation plan. Use `IMPLEMENTATION_STATUS.md`, `ROADMAP.md`, and `RELEASE_CHECKLIST.md` for the current v1.0 runtime-core status and release gates. Phase labels such as MVP or v0.x describe how the project was built, not the current maturity claim.

This project should not be implemented as a giant application from day one. It should be built in phases, where each phase proves a specific reliability claim.

## North Star

```text
Make AI agent execution durable, auditable, replayable, and safe by default.
```

## Product Milestones

### v0.1 - Local Durable Runtime

Goal: prove the smallest reliability loop locally.

Scope:

- Python SDK
- local runner
- SQLite WAL state store
- local blob store
- AgentContext
- Tool Registry
- Tool Gateway
- Tool Ledger
- Event Log
- deterministic replay
- CLI debug timeline MVP
- side-effect crash recovery demo

Non-goals:

- Postgres
- Kubernetes
- distributed workers
- long-running debug web app
- full sandbox
- all framework adapters
- application-specific identity and business workflows

Success criteria:

- quickstart runs without external services
- worker crash after tool success does not duplicate the side effect
- `agentledger replay <run_id>` does not call real model/tool providers
- `agentledger debug <run_id>` shows event timeline, state version, tool ledger
- all `external_write` tools require ledger reservation

Deliverables:

```text
agentledger init
agentledger run examples/side_effect_idempotency
agentledger debug <run_id>
agentledger replay <run_id>
agentledger ledger <run_id>
```

### v0.2 - Runtime Semantics Hardening

Goal: make local runtime semantics precise and testable.

Current scaffold now includes the first v0.2 slice:

- store-backed cost records and budget enforcement
- evidence bundle export
- side-effect-free evidence check reports
- replay event hash and replay-safety summary
- shadow mode that reuses archived Tool Ledger responses and blocks real side effects
- framework adapter base plus plain Python function adapter/decorator
- policy YAML/JSON loader and CLI policy check
- protocol boundary for storage/blob/model/tool adapters
- dependency-free LangGraph checkpointer/node facade and MCP tool/context adapter skeletons
- dependency-free LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, and Semantic Kernel method facades
- heartbeat, expired lease recovery, cancellation, retry policy, and failure taxonomy
- local worker loop with retry-until-idle semantics
- StateStore conformance runner
- evidence bundle directory export for CI/external eval artifacts
- static HTML evidence report export for local incident review
- evidence diff for replay/shadow regression
- evidence regression CLI for golden-vs-current evidence gates
- golden evidence corpus with built-in seed fixtures and repro harness CLI
- structured trace JSONL exporter
- runtime boundary lint for common direct shell/HTTP/SDK/model calls bypassing `ctx.call_tool`
- dependency-free OTLP JSON trace export
- failure injection suite for crash/retry/lease/cancellation semantics
- runnable examples for LangGraph-style nodes, MCP-style tools/context, and command-style sandbox tools
- Experimental Postgres store path with DDL and connection-injection conformance
- Experimental S3/MinIO BlobStore adapter with injected-client conformance
- SQLite migration catalog with `schema_migrations` and DDL export for SQLite/Postgres


Scope:

- state patch validation
- JSON Merge Patch / JSON Patch support
- state version checks
- lease token and fencing token validation
- cancellation state machine
- retry policy and failure taxonomy
- `PENDING_VERIFICATION` side-effect state
- basic policy YAML
- cost records
- conformance tests for state store and tool ledger

Success criteria:

- stale worker commit is rejected
- state version conflict is detected
- side-effect unknown never auto-retries
- replay detects divergence by event/state hash
- high-risk tool is denied by default policy

### v0.3 - Framework Adapter and DX

Goal: prove low-friction adoption.

Scope:

- LangGraph-compatible checkpointer adapter
- generic function decorator API
- tool wrapper API
- framework-agnostic runtime protocol draft
- CLI time-travel, debug state-diff, and static report export improvements
- docs and examples
- lint for bypassing runtime boundary

Success criteria:

- a LangGraph app can adopt runtime state and tool ledger with minimal code changes through the dependency-free facade or optional wrapper package
- common framework objects can be wrapped without importing their packages in runtime-core
- a plain Python function agent can use decorators only
- developer can inspect state diff before/after model/tool events
- runtime-managed tools can be registered through `Runtime.tool(...)`
- bypassing `ctx.call_tool` can be detected by lint in example projects
- dependency-free framework adapter fixtures can generate conformance reports for certification evidence

### v0.5 - Production Pilot Runtime

Goal: support serious pilot deployments.

Scope:

- hardened Postgres state store
- hardened S3/MinIO blob store
- schema migrations
- worker heartbeat
- multi-worker lease claim
- OpenTelemetry/OTLP JSON exporter and optional collector transport
- Docker sandbox plugin MVP
- approval gate
- retention and compaction jobs
- backup/restore guide
- failure injection suite
- generic artifact retention and lineage baseline; media/stream schemas have preview contracts and processing adapters remain v0.9 roadmap

Success criteria:

- multiple workers can claim distinct steps safely
- lease expiry and old-owner recovery are tested
- high-risk action has full audit chain
- run evidence bundle can be exported
- compaction preserves replay for high-risk events

### v0.8 - Reliability Harness

Goal: make runtime useful for regression and change safety.

Scope:

- Repro Harness
- Evidence Consumer Harness
- Shadow Mode
- replay diff
- failure attribution summaries
- cost attribution summaries
- policy lint
- adversarial review checklist
- benchmark corpus for historical runs
- media pipeline replay and evidence-linked frame/audio segment artifacts

Success criteria:

- prompt/workflow changes can be shadow-run against historical evidence
- replay vs rerun divergence is reported at event level
- media replay can reuse captured frame/segment artifacts instead of reprocessing raw audio/video
- cost regressions can be attributed to agent/step/tool/model
- external eval and regression results link back to evidence bundle

### v0.9 - Multimodal and Stream Runtime

Goal: make audio, video, frame, and event stream workflows first-class without turning runtime-core into a codec or streaming engine.

Scope:

- MediaArtifact contract (preview implemented)
- image/audio/video/frame/segment/transcript/embedding artifact kinds (preview implemented)
- media manifest schema (preview implemented)
- frame index and segment timeline metadata
- derived artifact lineage (preview implemented)
- EventStream checkpoint contract (preview implemented)
- chunk refs, offsets, watermarks, partial results, checkpoint/resume (preview implemented)
- stream backpressure and cancellation semantics
- multimodal tool schema conventions (preview implemented)
- media/stream reliability hooks for evidence, replay, evidence regression, review, divergence, backup, retention, trace, and conformance (preview implemented)

Success criteria:

- an audio/video workflow can persist durable media refs, frame/segment metadata, and derived outputs
- a stream consumer can resume from a durable offset/watermark after worker restart
- replay can reuse captured media artifacts and stream chunks instead of re-calling expensive tools
- evidence bundles can trace final outputs back to source frames, audio segments, transcripts, or chunks
- reliability gates can detect media artifact or stream checkpoint regressions before release

### v1.0 - Stable Runtime Core

Goal: stable enough for production pilots with clear boundaries.

Scope:

- stable AgentContext API
- stable event schema
- stable Tool Registry schema
- stable Tool Ledger schema
- stable StateStore interface
- security policy
- versioning and migration policy
- adapter conformance tests
- semver release process

Success criteria:

- runtime invariants are documented and tested
- all critical state backends pass conformance tests
- all high-risk tool flows have audit, approval, ledger, replay safety
- project has README, quickstart, architecture docs, security docs, CI, tests, examples, changelog

## Parallel Workstreams

### Runtime Core

- AgentContext
- Run / Session / Step models
- State Store
- Event Store
- Tool Ledger
- Replay Engine

### Developer Experience

- decorators
- CLI
- examples
- docs
- lint
- local-first defaults

### Adapters

- LangGraph checkpointer
- OpenAI Agents SDK adapter
- generic Python adapter
- TypeScript worker client
- Rust worker/runtime primitives
- Go infra worker/client
- MCP tool adapter

### Enterprise Readiness

- Postgres
- S3/MinIO
- OpenTelemetry
- Docker sandbox
- approvals
- retention / compaction
- threat model

## First Three Demos

1. Side-effect idempotency after worker crash.
2. Time-travel debug of a model/tool/state sequence.
3. LangGraph app with AgentLedgerCheckpointer and ToolGatewayNode.


## Current Implementation Slice Added

- Simple API: `agent`, `run`, `arun`, `RunResult`, and `Runtime.run()/Runtime.arun()` for hello-world adoption.
- Approval gate: durable `approval_requests`, `waiting_human` transition, CLI list/approve/deny commands.
- Sandbox boundary: `SandboxExecutor`, `SandboxPolicy`, `SandboxResult`, and `sandbox_required` tool execution events.
- Retention planning: non-destructive `RetentionPlanner`, media/stream protected ref counts, and compaction marker before future snapshot/AOF cleanup.
- Storage migration baseline: `schema_migrations`, SQLite auto-migration, Postgres migration status/apply, DDL catalog, and `agentledger migrate` CLI.
- Multi-language contract baseline: Python reference runtime plus contract export and golden JSON for Rust/TypeScript/Go.
- Evidence regression: `agentledger evidence-regression` for side-effect-free golden/current evidence checks and CI release gates.
- Adversarial review: `agentledger review checklist <run_id> --fail-on-risk` provides a read-only pre-release evidence gate.
- Divergence report: `agentledger divergence` compares event, state, artifact, ledger, cost, and model-output dimensions for rerun investigations.
- Cost attribution: `agentledger cost report <run_id>` groups recorded usage by run, agent, step, category, and tool/model name.
- Runtime boundary lint: `agentledger lint boundary` for best-effort detection of direct shell, HTTP, cloud SDK, GitHub SDK, and common model SDK calls that should be routed through runtime-managed tools or the runtime model boundary.
- Tool schema/catalog DX: dependency-free schema subset validation plus `agentledger tools manifest --format agentledger|openai`.
- Debug DX: `agentledger debug --json --include-diffs`, `agentledger timetravel --include-diffs`, and `--html` static reports expose state changes without a long-running process.
- Evidence DX: `agentledger evidence <run_id> --html ...` writes a static report for review without a long-running process.
- Tool wrapper DX: `Runtime.tool(...)` registers runtime-managed tools with the same metadata as `ToolSpec`.
- Adapter certification DX: `agentledger adapter conformance --kind ...` verifies dependency-free framework wrappers against local runtime/evidence checks.
- OTLP pilot path: `OTLPTraceExporter.post_json(...)` and `agentledger trace --format otlp --otlp-endpoint ...` can send dependency-free OTLP/JSON explicitly.
- Backup readiness: `agentledger backup check <run_id>` verifies metadata, schema version, blob refs, media/stream nested refs, and evidence exportability without mutating runtime data.
- Failure injection: `agentledger failure inject` for local side-effect crash, retry exhaustion, lease fencing, and cancellation fencing probes.
- Failure attribution: `agentledger failure report <run_id>` summarizes failed steps, pending verification, pending approvals, and failure events without mutating runtime state.
- Examples: `examples/langchain/basic_runnable.py`, `examples/langgraph/basic_graph.py`, `examples/crewai/basic_crew.py`, `examples/autogen/basic_agent.py`, `examples/openai_agents/basic_agent.py`, `examples/llamaindex/basic_query.py`, `examples/semantic_kernel/basic_kernel.py`, `examples/mcp_tool/basic_tool.py`, `examples/mcp_context/basic_context_server.py`, `examples/tool_catalog/basic_catalog.py`, and `examples/sandbox/command_tool.py` run without external services or framework dependencies.
- Repro harness: `agentledger corpus add/list/check` stores named golden evidence fixtures and runs side-effect-free evidence checks against them.
- Built-in fixtures: `agentledger corpus seed` installs reusable baseline, Tool Ledger, and media/stream evidence fixtures for compatibility checks.


## Sandbox Adapter Roadmap

- Core: `SandboxConfig`, `SandboxRouter`, fail-closed `none`, and in-process `local` executor.
- Linux local: bubblewrap adapter package that executes command-style tools with namespaces/seccomp policy.
- Container: Docker adapter package for common local/team deployments.
- Cluster: Kubernetes adapter with Job manifest dry-run, optional `kubectl` create/wait/log/delete execution, and `runtime_class` support for gVisor/Kata-style runtimes.
- High isolation: Firecracker/E2B/custom remote executor packages for untrusted code scenarios.
