# Maturity Model

AgentLedger is currently a v1.0 stable runtime-core project with explicit adapter boundaries.

The goal of this document is to make maturity explicit so users know which parts are stable in core, which parts are preview or experimental adapters, and which parts are external or roadmap.

## Status Levels

| Status | Meaning |
|---|---|
| `Stable core` | Implemented, tested, documented, and covered by contract/conformance gates for v1.0 runtime-core. |
| `Parity core` | Implemented in a non-Python runtime and covered by shared runtime-core parity gates; Python remains the reference for contract evolution. |
| `Experimental` | Implemented enough to validate a design, but not hardened for production. |
| `Skeleton` | Contract, DDL, adapter shape, or docs exist; full implementation is not complete. |
| `Roadmap` | Planned and designed, but not implemented yet. |
| `External` | Expected to live in optional packages, deployment recipes, or user-provided adapters. |
| `Non-goal` | Explicitly outside AgentLedger core. |

## Capability Matrix

| Capability | Status | Notes |
|---|---|---|
| Python reference runtime | `Stable core` | Current implementation in `src/agentledger`. |
| Simple API `agent/run/arun` | `Stable core` | Spring-style hello world with durable semantics underneath. |
| SQLite StateStore | `Stable core` | WAL mode, local-first, automatic migration baseline. |
| Local BlobStore | `Stable core` | File-backed JSON payload/artifact storage. |
| Event log | `Stable core` | Per-run sequence ordering and payload refs. |
| Tool Ledger | `Stable core` | Idempotency, audit, replay-safe side-effect records. |
| Replay engine | `Stable core` | Event-level replay summary; validates archived payload and artifact refs; does not call real tools. |
| Evidence bundle | `Stable core` | Exported JSON/file/static HTML layout for run review and regression, including media/stream indexes. |
| Evidence check report | `Stable core` | Side-effect-free runtime invariant checks, including media artifact refs and stream checkpoint offsets. |
| Diff report | `Stable core` | Evidence-to-evidence regression comparison. |
| Evidence regression CLI | `Stable core` | Golden-vs-current evidence gates for state, event, ledger, media/stream, and cost regressions. |
| Divergence report | `Stable core` | Evidence comparison across event, state, artifact, media/stream, ledger, cost, and model-output dimensions. |
| Adversarial review checklist | `Stable core` | Read-only pre-release evidence gate with blocker/warning checks, including media artifact refs and stream checkpoint offsets. |
| Golden evidence corpus | `Stable core` | File-based repro harness with built-in baseline, Tool Ledger, and media/stream seed fixtures, named evidence fixtures, and regression gates. |
| Trace JSONL exporter | `Stable core` | Local trace format for run/evidence review, including media artifact and stream checkpoint spans. |
| OpenTelemetry/OTLP JSON exporter | `Preview` | Dependency-free OTLP/JSON file export plus optional collector POST; hardened deployment remains external. |
| Time Travel Debugger CLI | `Stable core` | Reconstructs committed state by event sequence and can include state diffs plus static HTML export. |
| Cost/budget records | `Stable core` | Tool/model accounting, attribution reports, and budget enforcement hooks. |
| Approval gate | `Stable core` | Store-backed request/approve/deny flow. |
| Lease/fencing/cancellation | `Stable core` | Local scheduler and conformance tests cover core semantics. |
| Worker runtime loop | `Stable core` | Local worker loop, process-shaped `WorkerService`, and worker conformance checks; distributed deployment recipe is not complete. |
| Failure injection suite | `Stable core` | Local crash/retry/lease/cancellation probes for reliability regression checks. |
| Failure attribution report | `Stable core` | Read-only failure summary for steps, approvals, pending verification, and failure events. |
| Storage migrations | `Stable core` | SQLite runner, Postgres migration status/apply path, and SQLite/Postgres DDL catalog. |
| Runtime contract JSON | `Stable core` | Golden fixture for Python plus Go/TypeScript/Rust native runtime-core implementations. |
| Cross-language parity runner | `Stable core` | `scripts/check_language_parity.py` runs Python, Go, TypeScript, Rust, contract diff, Markdown links, and whitespace checks locally. |
| Release checklist and CI gates | `Stable core` | Local release checklist, contributor checks, ResourceWarning-sensitive tests, root conformance, boundary lint, contract export, and dependency-free example smoke. |
| Policy YAML | `Stable core` | Dependency-free role/tool policy loader. |
| Sandbox boundary | `Stable core` | `none`, `local`, router, events, fail-closed semantics. |
| Bubblewrap/Docker execution | `Experimental` | Command-style execution paths; production hardening remains external. |
| Kubernetes/gVisor executor | `Experimental` | Job dry-run and `kubectl`-gated execution; cluster policy is external. |
| E2B/Firecracker/custom sandbox | `Skeleton` | Adapter slots only. |
| Postgres StateStore | `Experimental` | psycopg-backed adapter with env/CLI config, schema isolation, JSONB handling, native `FOR UPDATE SKIP LOCKED` claiming, injected conformance, opt-in real-service test, and CI service conformance; operational hardening remains. |
| S3/MinIO BlobStore | `Experimental` | Content-addressed JSON adapter with injected-client conformance, CLI smoke, opt-in real-service test, and CI MinIO conformance; deployment hardening remains. |
| LangGraph adapter | `Preview` | Dependency-free checkpointer/node facade; exact LangGraph package integration remains optional. |
| MCP adapter | `Skeleton` | Tool descriptor mapping, context-read adapter, and dependency-free fixtures exist; exact MCP SDK integration is roadmap. |
| CrewAI/AutoGen/LangChain/OpenAI Agents/LlamaIndex/Semantic Kernel facades | `Preview` | Dependency-free method adapters exist; exact framework package integrations remain optional. |
| Go runtime implementation | `Parity core` | Dependency-free native runtime-core parity baseline exists under `go/`, including policy/approval/sandbox, cost/failure semantics, CLI, examples, and shared conformance. Production adapters remain separate. |
| TypeScript runtime implementation | `Parity core` | Dependency-free Node/TypeScript-compatible runtime-core parity baseline exists under `typescript/`, including policy/approval/sandbox, cost/failure semantics, CLI, examples, subpath exports, and shared conformance. Production adapters remain separate. |
| Rust runtime implementation | `Parity core` | Dependency-free runtime-core parity baseline exists under `rust/`, including local snapshot persistence, policy/approval/sandbox, cost/failure semantics, CLI, examples, features, and shared conformance. Production adapters remain separate. |
| Static time-travel report | `Preview` | Optional static HTML inspection export for local incident review; a long-running web app is a non-goal for runtime-core. |
| Lint for runtime bypass | `Stable core` | AST-based CLI check for common direct shell, HTTP, SDK, cloud, and model calls that bypass `ctx.call_tool`. |
| Media artifact contract | `Preview` | `MediaArtifact`, `MediaMetadata`, and `ArtifactLineage` store refs, metadata, and lineage; codecs and media processing remain external. |
| Event stream contract | `Preview` | `StreamChunkRef` and `EventStreamCheckpoint` store durable offsets, watermarks, chunk refs, partial-result refs, and backpressure hints. |
| Media/stream tool conventions | `Preview` | Dependency-free ToolSpec schemas and manifest export for common audio, video, frame, and stream adapter names. |
| Media runtime conformance | `Preview` | Executable checks for media evidence, replay, evidence regression, review, trace, and Tool Ledger chains. |
| Kubernetes deployment automation | `External` | Should live outside runtime core. |
| Business data schema | `Non-goal` | AgentLedger owns runtime metadata only. |

## Current Release Readiness

AgentLedger v1.0 runtime-core is ready for:

```text
local use
framework adapter integration
runtime design review
adapter experimentation
reliability semantics validation
production pilot preparation with explicit adapter boundaries
```

AgentLedger runtime-core still does not include:

```text
application-specific identity and business workflows
untrusted code execution without external hardening
large distributed worker fleet management
full external eval systems
workflow/planning engines
```

## v1.0 Compatibility

For v1.0 runtime-core, stable contracts and schemas should evolve additively where possible and remain protected by:

```text
contract JSON snapshots
schema migrations
StateStore conformance tests
evidence bundle fixtures
documented capability status
```
