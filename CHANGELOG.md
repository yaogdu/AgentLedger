# Changelog

All notable changes to AgentLedger will be documented in this file.

This project follows semantic versioning for the stable runtime-core contract. Optional adapters can still carry preview or experimental status.

## Unreleased

### Clarified

- Clarified that Inspector is language-neutral, while the current official Inspector distribution is packaged through the Python/PyPI CLI.
- Clarified that patch releases do not need to move every language package in lockstep when runtime-core semantics and shared conformance are unchanged.
- Added standalone Inspector distribution to the roadmap for non-Python users who want the official viewer without installing a Python package into their application runtime.

## 1.3.5 - 2026-06-07

### Added

- Added an Inspector chronological Event Stream view sorted by event timestamp, showing runtime run id, extracted agent run id, step id, event type, summary, and links back to detailed timeline records.
- Added `agentledger inspector runs` and the `agentledger.inspector.runs.v1` read model for a read-only run index over SQLite/Postgres/MySQL runtime metadata.

### Fixed

- Improved packaged Inspector/static HTML layout so large JSON/details payloads and long ids do not expand tables or break the page width.
- Reworked detailed Inspector, evidence, and time-travel tables so JSON opens in a full-width row below the record instead of a narrow right-side column.
- Reworked the Inspector run-index HTML from a wide multi-column table into a compact paginated run list with status, timestamps, counters, Inspector links, and folded JSON details.

### Clarified

- This is an Inspector companion patch release. Inspector is language-neutral, but the current packaged implementation is distributed through the Python/PyPI CLI. The release does not change the stable runtime-core contract or require Go, TypeScript, or Rust runtime-core package changes.

## 1.3.4

### Fixed

- Corrected the `agentledger-inspector` package module `__version__` so it matches published package metadata.
- Added a release metadata regression check so the runtime package, Inspector companion package, and optional Inspector extra stay aligned in future patch releases.

### Clarified

- This is an Inspector/package metadata patch release. It does not change the stable runtime-core contract or require Go, TypeScript, or Rust runtime-core changes.

## 1.3.3

### Added

- Added stable Inspector read-model anchors and related links for timeline events, steps, Tool Ledger rows, approval requests, policy decisions, and artifacts.
- Added static HTML report navigation and internal cross-links so local reports can jump between events, tools, approvals, and artifacts without running a server.

### Clarified

- This is an Inspector-only patch release. It does not change the stable runtime-core contract or require Go, TypeScript, or Rust runtime-core changes.

## 1.3.2

### Added

- Added configurable Inspector redaction policies for JSON and static HTML reports.
- Added `agentledger inspector run/evidence --redact-key ...` and `--redaction-policy policy.json` for local or internal debugging with sensitive fields masked.
- Exported `InspectorRedactionPolicy` from both `agentledger-runtime` and the optional `agentledger-inspector` companion package for custom viewers.

### Clarified

- This is an Inspector-only patch release. It does not change the stable runtime-core contract or require Go, TypeScript, or Rust runtime-core changes.

## 1.3.1

### Fixed

- Added the Python `agentledger version` CLI command so the Python reference CLI matches the documented four-language CLI baseline.
- Aligned the Python, Go, TypeScript, and Rust package train to `1.3.1` after the post-release install smoke caught the missing Python command.

## 1.3.0

### Added

- `agentledger inspector` CLI with read-only `run` and `evidence` subcommands.
- Language-neutral Inspector read model `agentledger.inspector.v1` for run timeline, Tool Ledger, approvals, policy decisions, cost/failure records, artifacts, and risk flags.
- Static HTML Inspector export for local or internal debugging without starting a server.
- Read-only SQLite runtime data source and Postgres/MySQL read data sources through existing StateStore adapter boundaries.
- Optional `agentledger-inspector` companion package for users who want to depend on the read model and extension API directly.

### Clarified

- Inspector is an evidence/runtime metadata consumer, not a permissions system or write/control plane.
- Use read-only database credentials for Postgres/MySQL inspection; evidence-bundle input remains the most portable path across Python, Go, TypeScript, and Rust.

## 1.2.4

### Added

- Open-source impact documentation for AgentLedger's early-stage agent reliability and governance infrastructure positioning.
- Maintainer notes documenting project ownership, review principles, release responsibilities, coding-agent usage, and maintenance signals.
- Cross-language 3-minute side-effect safety demos showing crash/retry without duplicate external writes.
- Cross-language MCP governance examples showing descriptor annotations for side effects, approval, sandbox metadata, idempotency, and audit evidence.
- Adoption plan, public issue/discussion candidates, and a legal-agent case study template.

### Changed

- README first screen now leads with the tool side-effect safety problem before describing architecture.
- MCP tool adapter now maps governance annotations such as `approval_required`, `sandbox_required`, `sandbox_executor`, and `sandbox_policy`.

### Clarified

- Roadmap guidance for open-source adoption, OpenAI Agents SDK/MCP examples, Codex-assisted maintainer workflows, and public usage evidence without changing runtime-core semantics.
- 1.2.4 does not change runtime-core semantics; it is an adoption and example-focused release.

## 1.2.3

### Added

- SQL query examples for runtime inspection, multi-table timelines, approvals, costs, artifacts, and large business-schema integration patterns.
- `agentledger-langfuse` as an official optional observability adapter boundary.
- TypeScript subpath/package, Go adapter boundary, and Rust crate/feature boundary for Langfuse-style evidence/trace payload export.

### Changed

- Updated adapter packaging, certification, optional-adapter conformance, and documentation entrypoints for the Langfuse adapter boundary.
- Removed tracked local runtime state from the repository.

### Clarified

- Langfuse support is an adapter/export boundary, not a replacement for Langfuse or a binding to the Langfuse SDK.

## 1.2.2

### Added

- Official MySQL storage adapter boundary across Python, Go, TypeScript, and Rust.
- Python `agentledger-mysql`, TypeScript `agentledger-mysql`, Go `go/adapters/mysql`, and Rust `agentledger-mysql` package/crate boundaries.
- MySQL DDL/migration metadata in shared storage schema helpers and conformance fixtures.
- Injected-client MySQL adapter smoke coverage for Go, TypeScript, and Rust, plus Python CLI/package/export support.

### Clarified

- MySQL support in this release is an optional adapter boundary and migration/schema contract; production hardening still requires real-service concurrency, load, permission, backup, and restore validation.

## 1.2.1

### Added

- Cross-language Docker sandbox execution parity for Go, TypeScript, and Rust.
- `DockerSandboxExecutor` now supports command-style tools with explicit execution enablement, argv-only defaults, read-only Docker runs, network-deny defaults, stdout/stderr/returncode capture, and fail-closed behavior when execution is disabled.
- Official adapter conformance now checks Docker manifest generation, fail-closed execution defaults, and injected-binary command execution without requiring a live Docker daemon.

### Clarified

- Docker remains an optional sandbox adapter, not a runtime-core dependency or complete high-risk isolation answer.
- Postgres, S3/MinIO, OTLP, exact MCP SDK transport, and framework-native adapters still require separate production hardening or ecosystem-specific adapter work.

## 1.1.0

### Added

- Adapter certification bundles through `agentledger adapter certify`, covering package metadata, conformance commands, smoke commands, external service requirements, security assumptions, known limitations, and explicit production validation status.
- Evidence regression summaries with failed checks, changed dimensions, changed counts, bundle-hash status, and cost deltas for CI/release-gate consumers.

### Clarified

- P2-style production hardening still requires real Postgres/S3/sandbox/worker/OTLP environments, load/concurrency checks, and restore or rollback drills; local certification bundles mark those checks as `external-required` instead of pretending they are complete.
- This release completes the local, dependency-free P1/P3 gate slice. Exact optional adapter packages, framework-native smoke fixtures, production adapter hardening, and richer reliability harness workflows remain tracked in the roadmap.

## 1.0.5

### Added

- Normalized Policy Engine contract with `PolicyRequest`, `PolicyDecision`, `PolicyFinding`, and `PolicyControl`.
- Dependency-free evaluator registry for role capability, action boundary, and runtime-state findings.
- ToolGateway integration that records the full policy decision contract inside `tool_permission_decided` evidence while keeping `PolicyEngine.check_tool(...)` compatible.
- Policy contract fields for future sub-agent/multi-agent delegation and existing media/stream refs without implementing sub-agent execution or media processing adapters.
- Policy Engine documentation and SVG diagrams for the PEP/PDP control loop and evaluate layer.

### Clarified

- `1.0.5` focuses on runtime policy contracts and gate enforcement, not OPA/Cedar adapters, DLP, prompt-injection products, governance UIs, multi-agent orchestration, or media processing infrastructure.

## 1.0.2

### Added

- Official optional adapter conformance fixture `official_adapters.v1.json` for Postgres migration clients, S3/MinIO object clients, OTLP transport clients, and Docker sandbox manifests.
- Go, TypeScript, and Rust injected-client adapter APIs for Postgres, S3/MinIO, OTLP transport, and Docker sandbox manifest generation.
- `official_adapters_smoke` in the shared runtime semantic manifest and every preview language conformance CLI.

### Clarified

- Adapter layer development starts with SDK-neutral injected clients and dry-run manifests so runtime-core remains dependency-light while official adapters get real conformance coverage.

## 1.0.1

### Added

- `agentledger --help` now prints the GitHub project URL, documentation URL, and recommended `pipx install agentledger-runtime` command.
- README and usage docs now make the PyPI distribution name explicit and point users from installation to the GitHub documentation.
- Go, Node/TypeScript, and Rust preview runtime-core parity baselines covering run/session/step state, lease recovery, cancellation fencing, ToolGateway, Tool Ledger idempotency, evidence export, replay summary, policy denial, approval pause/resume, sandbox fail-closed behavior, cost/budget accounting, failure attribution, and Rust local snapshot persistence.
- Shared language-neutral conformance fixtures for runtime baseline, local persistence, local blob store, tool schema validation, worker service, policy/approval/sandbox, cost/failure attribution, media/stream artifact references, evidence consumers, static debug HTML, ops readiness, storage schema, MCP adapters, framework adapters, OTLP trace export, simple API, boundary lint, scheduler, adversarial review, evidence regression, failure injection, shadow reports, repro golden corpus, time travel timeline, and optional adapter boundaries.
- Preview per-language conformance CLIs for Go, Node/TypeScript, and Rust with `conformance`, `contract validate`, and `contract export` commands; `conformance` now executes every semantic smoke listed in `contracts/conformance/runtime_semantics.v1.json`.
- Cross-language parity runner `scripts/check_language_parity.py` with optional JSON report output that parses per-language conformance reports and enforces shared semantic checks, plus CI docs-hygiene checks for Markdown local links and diff whitespace.
- Conservative Python module parity audit `scripts/audit_python_parity.py`, currently reporting `gap_count: 0` for the declared runtime-core scope.
- Adapter roadmap docs defining official, recommended, experimental, and out-of-core adapter priorities across Python, Go, TypeScript, and Rust.
- Multi-language strategy, parity matrix, execution-backend positioning docs, comparison docs, and relationship architecture SVGs for LangGraph/Temporal/Ray/Kubernetes positioning.

### Clarified

- Python reference runtime-core parity is now declared for Go, TypeScript, and Rust within the AgentLedger core scope.
- Concrete production adapters such as Postgres, S3/MinIO, Docker, Kubernetes, MCP transport, LangGraph, Temporal, and OpenTelemetry remain optional packages unless explicitly shipped for a language.
- AgentLedger remains a framework/library/runtime layer, not a managed service and not a general workflow, eval, RAG, or deployment product.

## 1.0.0

### Changed

- Removed public `eval` CLI aliases in favor of `evidence-check`, `evidence-regression`, and `corpus check`, keeping full eval systems outside runtime-core.
- Clarified the v1.0 roadmap section as implemented for Python runtime-core, with media/stream contracts still marked preview.
- Changed the PyPI distribution name to `agentledger-runtime` while keeping the import package and CLI as `agentledger`.

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
