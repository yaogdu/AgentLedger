# Changelog

All notable changes to AgentLedger will be documented in this file.

This project follows semantic versioning for the stable runtime-core contract. Optional adapters can still carry preview or experimental status.

## Unreleased

### Changed

- Removed public `eval` CLI aliases in favor of `evidence-check`, `evidence-regression`, and `corpus check`, keeping full eval systems outside runtime-core.
- Clarified the v1.0 roadmap section as implemented for Python runtime-core, with media/stream contracts still marked preview.
- Changed the PyPI distribution name to `agentledger-runtime` while keeping the import package and CLI as `agentledger`.

## 1.0.0

### Added

- Maturity model and release-readiness documentation.
- Roadmap scope map for stable runtime-core, optional adapters, and external evidence consumers.
- Architecture overview for runtime layers, core modules, invariants, and adapter boundaries.
- Experimental psycopg-backed Postgres StateStore path with env/CLI configuration, schema isolation, JSONB handling, connection-injection conformance, and opt-in real-service smoke test.
- Experimental S3/MinIO BlobStore adapter with optional boto3 loading, env/CLI configuration, injected-client support, BlobStore conformance coverage, and opt-in real-service smoke test.
- Store-level artifact creation to remove SQLite connection leakage from `AgentContext`.
- Language-neutral runtime contract fixture for future Rust, TypeScript, and Go implementations.
- Storage migration baseline with SQLite `schema_migrations`, Postgres migration status/apply, and DDL export.
- Kubernetes/gVisor sandbox dry-run and `kubectl`-gated execution path.
- Evidence regression CLI for golden-vs-current evidence gates across final state, event types, Tool Ledger statuses, and cost deltas.
- Runtime boundary lint CLI for common direct shell, HTTP, SDK, cloud, and model calls that bypass `ctx.call_tool`.
- Dependency-free OTLP JSON trace exporter, CLI `trace --format otlp`, and optional OTLP/JSON collector POST.
- Failure injection suite and CLI for local crash, retry, lease fencing, and cancellation probes.
- Runnable dependency-free LangChain, LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, MCP-style tool/context, tool catalog, and sandbox command examples.
- Roadmap entries for media artifact and event stream runtime support.
- LangGraph-compatible dependency-free checkpointer facade with `put`, `get`, `get_tuple`, `list`, and `put_writes`.
- Versioning/compatibility policy and adapter certification checklist.
- Golden evidence corpus and `agentledger corpus add/list/check` repro harness.
- Dependency-free LangChain, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, and Semantic Kernel method facades.
- Read-only backup readiness checker and CLI `agentledger backup check <run_id>`.
- Tool schema/catalog DX with dependency-free schema subset validation and `agentledger tools manifest`.
- Static time-travel HTML debug export via `agentledger timetravel --html` and `agentledger debug --html`.
- Framework adapter conformance runner and CLI fixtures for dependency-free adapter certification smoke.
- Tool catalog example showing `Runtime.tool(...)`, schema validation, AgentLedger manifest export, and OpenAI-compatible tool descriptors.
- Read-only cost attribution report and CLI `agentledger cost report <run_id>`.
- Read-only failure attribution report and CLI `agentledger failure report <run_id>`.
- Replay/rerun divergence report and CLI `agentledger divergence`.
- Adversarial review checklist and release gate CLI `agentledger review checklist`.
- Static evidence HTML report via `agentledger evidence --html`.
- Dependency-free MCP tool/context server fixtures and `MCPContextAdapter`.
- CI real-service conformance jobs for Postgres and MinIO optional adapters.
- Built-in golden corpus seed fixture via `agentledger corpus seed minimal-success`.
- Preview media and event-stream artifact contracts with `MediaArtifact`, `MediaMetadata`, `ArtifactLineage`, `StreamChunkRef`, `EventStreamCheckpoint`, context helpers, evidence counts, language-neutral contract entries, and a dependency-free example.
- Media/stream tool schema conventions for `audio.transcribe`, `video.extract_frames`, `frame.describe`, `video.summarize`, `stream.consume`, and `stream.emit`, including CLI manifest export.
- Evidence bundle media/stream indexes and replay artifact validation/counts for archived media manifests and stream checkpoints.
- Runtime-managed media tool example showing `video.extract_frames` through ToolGateway, Tool Ledger, media artifact creation, and evidence export.
- Adversarial review checks for media artifact refs and stream checkpoint offsets.
- Evidence diff and divergence dimensions for media artifacts and stream checkpoints.
- Evidence regression gates for media artifact refs and stream checkpoint changes, with CLI allow flags.
- Backup readiness checks for media/stream evidence shape and nested `blob://` refs inside artifact metadata.
- Retention planning now reports media artifact counts, stream checkpoint counts, and protected nested blob refs before any future compaction.
- Trace export now includes media artifact and stream checkpoint spans in addition to event spans.
- Media runtime conformance runner covering media evidence, replay, evidence regression, review, trace, and Tool Ledger chains.
- Transient retry worker demo documentation for `worker-run` and `worker serve`.
- Docs tool catalog fixture documentation for `agentledger tools manifest --example examples/docs`.
- Release checklist documentation covering local gates, example smoke, optional service-backed checks, evidence gates, and release-note requirements.
- Formal documentation index, detailed usage guide, detailed design/implementation guide, Chinese documentation entrypoints, and SVG runtime architecture diagram.
- CLI parser smoke coverage for documented commands, including nested commands and global `--policy` usage.
- Packaging metadata coverage for the `agentledger` console script, supported Python versions, README metadata, and optional dependency groups.
- Media/stream adapter boundary and certification guidance for durable refs, lineage, checkpoints, replay, and evidence export.

### Changed

- CI now compiles examples, runs ResourceWarning-sensitive tests, executes root conformance, checks media tool manifests, and smokes media/worker examples.
- README and CONTRIBUTING release checks now point to the shared release checklist and include ResourceWarning, conformance, lint, and contract gates.
- Python package classifiers now include Python 3.12, Python 3 only, OS independence, and Python library metadata.

### Fixed

- Postgres injected connection ownership is now explicit, preventing shared test connections from being closed too early while still closing runtime-owned connections.
- Migration CLI paths now close SQLite/Postgres stores deterministically after status/apply operations.
- Warning-sensitive test runs no longer emit unclosed sqlite database ResourceWarnings.

## 0.2.0-alpha

### Added

- Python reference runtime.
- Local SQLite WAL StateStore.
- Local file BlobStore.
- AgentContext, Runtime, ToolRegistry, and ToolGateway.
- Tool Ledger for managed side effects and idempotency.
- Event-level replay summary.
- Evidence bundle export.
- Evidence diff, evidence check report, and trace JSONL exporter.
- Cost and budget records.
- Approval request/approve/deny flow.
- Policy YAML/JSON loader.
- Local scheduler with heartbeat, lease recovery, cancellation, and retry policy.
- Local worker loop.
- Sandbox executor contract with local, disabled, bubblewrap, Docker, Kubernetes, E2B, Firecracker, and custom adapter slots.
- Simple API: `agent`, `run`, `arun`.
- LangGraph and MCP dependency-free adapter skeletons.
- Postgres DDL skeleton and optional dependency boundary.
- StateStore conformance runner.

### Known Limitations

- Postgres and S3/MinIO adapters are experimental and not production-hardened.
- Distributed worker deployment is not complete.
- OTLP collector transport is dependency-free and experimental.
- Exact optional framework packages are not implemented.
- Rust, TypeScript, and Go implementations are not started.
- Production sandbox hardening requires external deployment policy.
