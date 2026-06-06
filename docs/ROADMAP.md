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
| Inspector / Debug Viewer | stable read models, evidence export, static HTML debug export, redaction hooks, schema/version metadata | separate read-only local or internal inspector package | deployment management service, write/control plane in runtime-core |
| Model Gateway / Router | model-call boundary, request/response archival, replay skipping, token/cost attribution, budget/fallback semantics | provider adapters, LiteLLM-style router adapters, policy packs, price catalogs | bundling every model SDK, becoming a full model gateway product, replacing provider SDKs |

Execution backend positioning is documented in `EXECUTION_BACKENDS.md`: Temporal, Ray, and Kubernetes are backend adapters for generic distributed execution, while AgentLedger keeps agent-specific runtime invariants.

Adapter prioritization is documented in `ADAPTER_ROADMAP.md`: official adapters are added when the ecosystem is mature and the boundary can preserve AgentLedger invariants; otherwise the integration remains experimental or community-owned.

This scope map is part of the release gate: a new feature should either fit runtime-core as a production execution reliability contract, land as an optional adapter, become a separate evidence consumer, or be documented as out of scope. The default choice is adapter or external consumer unless runtime-core is the only layer that can enforce the invariant.

## Agent Harness Positioning

AgentLedger should not try to become a complete Agent Harness product. A full harness would need to rebuild or deeply own workflow orchestration, trace UI, eval systems, model gateways, context engines, sandbox infrastructure, tool hosting, and enterprise governance. Those layers already have mature or fast-moving ecosystems such as LangGraph, Temporal, Langfuse, LangSmith, OpenTelemetry, LiteLLM, MCP, vector databases, Kubernetes, and sandbox providers.

AgentLedger's role is narrower and more defensible:

```text
AgentLedger is the reliability substrate for Agent Harness stacks.

It provides durable execution, tool/model governance, evidence, replay,
policy, sandbox boundaries, cost/failure attribution, and adapter contracts.

It integrates with LangGraph, Temporal, Langfuse, MCP, model providers,
storage backends, and sandbox systems instead of replacing them.
```

Recommended stack positioning:

| Layer | Example systems | AgentLedger responsibility |
|---|---|---|
| Workflow / planning | LangGraph, CrewAI, AutoGen, LangChain, custom code | adapter boundary, checkpoint/evidence hooks, side-effect-safe node/tool execution |
| Durable workflow backend | Temporal, Ray, Kubernetes workers | agent-specific leases, fencing, cancellation, checkpoints, Tool Ledger, evidence, replay |
| Observability / eval UI | Langfuse, LangSmith, OpenTelemetry, custom dashboards | structured events, evidence bundles, trace/cost/failure export, correlation IDs |
| Tool and context protocols | MCP, internal tool servers, provider SDK tools | ToolGateway, Tool Ledger, schema validation, approvals, sandbox, audit records |
| Model providers / routers | OpenAI, Anthropic, Gemini, Bedrock, Ollama, LiteLLM | ModelGateway contract, archived model responses, budget/fallback/replay semantics |
| Storage / artifacts | SQLite, Postgres, MySQL, S3/MinIO, internal stores | StateStore/BlobStore contracts, migrations, conformance, evidence refs |

### Must Stay In Runtime-Core

These capabilities are core because only the runtime execution path can enforce them reliably:

```text
ToolGateway / Tool Ledger / idempotency
StateStore / checkpoint / lease / fencing / cancellation
event log / evidence bundle / replay
policy / approval / sandbox contract
cost and failure attribution
conformance and adapter certification
ModelGateway contract after the model boundary is designed
```

Runtime-core may include dependency-free local defaults and protocol contracts, but it should not force provider SDKs, web frameworks, cloud SDKs, or orchestration engines into the base package.

### Should Be Official Optional Packages

These are valuable and should be supported when the package boundary is clear:

```text
agentledger-inspector: read-only local/internal debug viewer for run timeline, state diff, Tool Ledger, cost/failure, evidence
agentledger-langgraph: LangGraph checkpointer/node integration
agentledger-mcp: MCP tool/context integration
agentledger-otel and Langfuse/LangSmith-style exporters: observability/evidence export
agentledger-temporal: Temporal execution-backend bridge
agentledger-model-* packages: OpenAI, Anthropic, Gemini, Bedrock, Ollama, LiteLLM-style provider/router adapters
agentledger-sandbox-* packages: Docker, Kubernetes, E2B, Firecracker/gVisor/bubblewrap where appropriate
agentledger-postgres, agentledger-mysql, agentledger-s3: storage and artifact adapters
```

Official optional packages must preserve AgentLedger invariants, stay fail-closed when dependencies or permissions are missing, and publish conformance or injected-client tests.

### Should Be Adapter / Export / Contract Only

These systems should be integrated with, not rebuilt:

```text
LangChain / CrewAI / AutoGen / OpenAI Agents SDK / LlamaIndex / Semantic Kernel
Langfuse / LangSmith / OpenTelemetry backends
Temporal / Ray / Kubernetes
LiteLLM and enterprise model gateways
vector databases, RAG systems, long-term memory systems
eval platforms and benchmark runners
MCP tool servers and enterprise tool catalogs
```

AgentLedger should provide adapters, export formats, evidence bundles, trace correlation, and conformance checks for these layers.

### Should Stay Out Of Scope

These would make the project too broad or turn it into a different product:

```text
complete agent workflow engine
complete eval platform
complete Langfuse/LangSmith replacement
complete RAG or memory platform
complete sandbox infrastructure platform
deployment management service, billing, organization admin
debug viewer write/control plane in the first inspector release
tool marketplace or app store
```

### Recommended Implementation Order

1. Ship `agentledger-inspector` as a read-only evidence/runtime metadata consumer over SQLite/Postgres/MySQL and exported evidence bundles.
2. Harden observability export: OTLP now, then Langfuse/LangSmith-style evidence/trace exporters without replacing those tools.
3. Design and implement the `ModelGateway`/`ModelRouter` contract in runtime-core with injected provider clients and replay-safe archived responses.
4. Add optional model provider/router adapters for OpenAI, Anthropic, Gemini, Bedrock, Ollama, and LiteLLM-style routing.
5. Add a Temporal bridge that makes the boundary explicit: Temporal owns workflow lifecycle; AgentLedger owns node-internal tool/model/runtime safety.
6. Continue hardening storage, sandbox, MCP, tool, and framework adapters with real-service conformance, permission boundaries, backup/restore, and failure semantics.

## Open Source Adoption And Maintainer Workflow

This track is not a separate runtime feature line and does not change the stable v1.x runtime-core contract. It exists to make the project easier to evaluate, adopt, maintain, and integrate with the wider agent ecosystem.

Positioning:

```text
AgentLedger is an early-stage reliability and governance runtime layer
for production AI agents.

It should demonstrate infrastructure value through clear examples,
adapter contracts, conformance checks, and maintenance evidence rather
than overclaiming broad production adoption.
```

Recommended work:

1. Add a focused OpenAI Agents SDK example that shows a runtime-managed tool call, approval gate, Tool Ledger record, evidence export, and replay-safe debugging flow.
2. Add an MCP governance example that shows schema validation, permission checks, approval-required tools, sandbox-required tools, and audit evidence for MCP-style tools.
3. Add a Temporal bridge example that demonstrates the intended boundary: Temporal owns workflow lifecycle and retries; AgentLedger owns node-internal tool/model/state reliability.
4. Add a Codex-assisted maintainer workflow document or script that helps with issue triage, release checklist preparation, adapter conformance checks, documentation consistency, and changelog drafting.
5. Keep `OPEN_SOURCE_IMPACT.md` and `MAINTAINER_NOTES.md` current as the public explanation of ecosystem value and maintenance responsibility.
6. Collect real usage evidence without inflating claims: examples, discussions, issues, integration notes, package downloads, external demos, and real-service hardening reports.

Adoption evidence work:

1. Build a 3-minute demo named "Prevent duplicate tool side effects in AI agents": roughly 30 lines of code plus a short README, showing a failed retry that does not duplicate an external action because Tool Ledger owns the idempotency record. The expected output should show the run id, one external side effect, one Tool Ledger entry, and replay/evidence commands.
2. Record a short GIF or terminal screencast showing the runtime path: `run -> tool call -> approval -> crash -> resume -> replay evidence`.
3. Write one technical article with a clear thesis, for example "Agents Need a Runtime, Not More Retries" or "Making AI Agents Durable, Auditable, and Replayable".
4. Keep the README opening focused on the user pain: "Your agent called a tool. Did it happen? Can you retry safely? Can you prove it later?"
5. Create public issues or discussions for the next adoption tasks: OpenAI Agents SDK approval/replay example, MCP tool governance example, Inspector prototype, Temporal bridge example, and tool-injection risk scanner.
6. Publish one or two real integration notes or case studies, such as using AgentLedger to audit tool calls in a legal agent, without including private data.

Companion product directions:

| Direction | Why it matters | Packaging boundary |
|---|---|---|
| AgentLedger Inspector | makes runs visible through timeline, Tool Ledger, approvals, replay diff, artifacts, cost, and failure attribution | separate read-only local/internal tool, not runtime-core UI |
| Tool Governance / MCP Gateway | enforces schema, permission, approval, sandbox, audit, and idempotency before tool side effects | optional gateway package or reference service |
| Replay / Regression Lab | lets teams test prompt, model, tool-schema, or agent-logic changes against historical evidence without repeating side effects | CLI and CI companion over evidence bundles |
| Production Harness Blueprint | shows how AgentLedger composes with LangGraph/OpenAI Agents SDK, Temporal, Langfuse/OTel, MCP, Postgres/S3, and Docker sandbox | examples, templates, and deployment recipes |
| Agent Security Scanner | detects tool boundary bypass, risky tool schemas, missing approval/sandbox, secret exposure, and sensitive evidence artifacts | optional scanner command or separate package |

The adoption goal is not to chase stars directly. It is to make the project understandable and verifiable within a few minutes: without AgentLedger, users often cannot tell what happened after an agent failure; with AgentLedger, they can inspect, resume, replay, and govern tool side effects.

Mentioning OpenAI Agents SDK here means a planned ecosystem example and adapter target. It does not imply official OpenAI partnership, endorsement, certification, or completed production integration unless a later release explicitly documents that evidence.

Explicit non-goals for this track:

```text
do not describe AgentLedger as a mature large-adoption project until evidence exists
do not add marketing-only claims that are not backed by examples or conformance
do not turn the repo into a full harness product, or eval platform
do not put secrets, private customer details, or private company implementation notes into public docs
```

## v1.3.0 - Language-neutral Inspector Release

Status: implemented as a read-only evidence/runtime metadata consumer without changing runtime-core execution semantics.

Implemented:

- added `agentledger inspector run` for SQLite, Postgres, and MySQL runtime metadata reads
- added `agentledger inspector evidence` for exported evidence bundle files or directories
- added `agentledger.inspector.v1` as a stable read model for run timeline, Tool Ledger, approvals, policy decisions, cost/failure records, artifacts, and risk flags
- added static HTML Inspector export for local or internal debugging
- added read-only SQLite store and read-only local blob store helpers; Postgres/MySQL usage is documented to require read-only DB credentials
- added optional `agentledger-inspector` companion package and extension API for custom data sources/renderers
- documented DB connection, evidence input, static HTML output, and extension boundaries in English and Chinese

Explicitly not in this version:

- write/control-plane actions such as approval, denial, cancellation, ledger editing, or database mutation
- permission/user/organization management
- long-running web application
- replacing Langfuse, LangSmith, OpenTelemetry, or eval platforms
- remote blob service integration inside the Inspector package

Follow-up work:

- richer report navigation and artifact cross-links
- configurable redaction policies
- evidence-driven replay/regression lab over Inspector read models
- optional local/internal web viewer if it remains read-only and dependency-isolated

## v1.2.4 - Adoption And Short Demo Release

Status: implemented as an adoption/example release without changing runtime-core semantics.

Implemented:

- added cross-language 3-minute side-effect safety demos that show crash/retry without duplicate external writes
- added cross-language MCP governance examples that map descriptor annotations into policy, approval, sandbox metadata, idempotency, and audit evidence
- strengthened the README first screen around the tool side-effect safety problem
- added adoption planning docs, public issue/discussion candidates, and legal-agent case-study templates
- updated package metadata and current install examples to the 1.2.4 release train

Explicitly not in this version:

- changing the stable runtime-core contract
- claiming official OpenAI Agents SDK or MCP endorsement
- building the Inspector, Replay Lab, or Security Scanner companion products
- making production-hardening claims for optional adapters without real-service evidence

## v1.2.3 - Query Documentation And Langfuse Adapter Boundary

Status: implemented as a small adapter/documentation release without changing runtime-core semantics.

Implemented:

- added SQL query examples for single-table runtime inspection, multi-table timelines, approvals, costs, artifacts, and large business-schema integration patterns
- added `agentledger-langfuse` as an official optional observability adapter boundary
- added TypeScript subpath/package, Go adapter boundary, and Rust crate/feature boundary for Langfuse-style evidence/trace payload export
- updated adapter packaging, certification, optional-adapter conformance, and documentation entrypoints
- removed tracked local runtime state from the repository

Explicitly not in this version:

- replacing Langfuse or implementing a full observability backend
- binding runtime-core to the Langfuse SDK
- production validation of a specific Langfuse server ingestion endpoint

## v1.2.2 - MySQL Adapter Boundary Release

Status: implemented as a storage adapter boundary release. It extends the `1.2.x` adapter packaging model without changing runtime-core semantics.

Implemented:

- added MySQL DDL/migration metadata to Python, Go, TypeScript, and Rust storage schema helpers
- added Python `MySQLStore` / `MySQLStoreConfig` with optional `pymysql` dependency and CLI migration/status support
- added `agentledger-mysql` Python package, TypeScript npm package boundary, Go `go/adapters/mysql`, and Rust `agentledger-mysql` crate boundary
- added cross-language optional adapter and official adapter conformance tokens for MySQL
- documented MySQL as an official optional adapter boundary, not a production-hardening claim

Explicitly not in this version:

- production-ready claims for MySQL without real-service evidence
- live MySQL concurrency/load/backup/restore gates
- native non-Python MySQL drivers in core; Go/TypeScript/Rust expose injected SQL adapter contracts

## v1.2.1 - Adapter Packaging Release

Status: implemented on the `v1.2.1` branch as an adapter packaging and boundary release. It packages the existing adapter seams without changing the runtime-core semantics.

Why this comes before reliability/media/sub-agent expansion:

```text
freeze the core-vs-adapter boundary before adding more surface area
keep runtime-core dependency-light
let heavy ecosystem dependencies move at their own release cadence
make future reliability hardening live next to the adapter it validates
avoid turning runtime-core into a bundle of optional integrations
```

Implemented:

- created a `packages/` workspace for official Python adapter packages
- added the first Python adapter packages: `agentledger-postgres`, `agentledger-s3`, `agentledger-langgraph`, `agentledger-mcp`, `agentledger-otel`, and `agentledger-sandbox-docker`
- added TypeScript subpath exports and npm adapter packages under `typescript/packages/`
- added Go adapter import subpackages under `go/adapters/`
- added Rust adapter features and crate packages under `rust/crates/`
- added core extras so users can install capabilities without memorizing package names:
  - `agentledger-runtime[postgres]`
  - `agentledger-runtime[s3]`
  - `agentledger-runtime[langgraph]`
  - `agentledger-runtime[mcp]`
  - `agentledger-runtime[otel]`
  - `agentledger-runtime[docker]`
  - `agentledger-runtime[all]`
- kept backwards-compatible import shims in core for the current Python adapter modules
- gave every adapter package a README, example/readme or package entry point, and local smoke coverage
- added adapter-package docs in English and Chinese
- kept adapter packages dependency-light by using optional dependencies, facade exports, and injected clients where possible

Explicitly not in this version:

- production-ready claims for Postgres/S3/sandbox/worker/OTLP without real service evidence
- full framework-native version matrix for every agent framework
- complete MCP SDK server/client coverage
- Temporal/Ray/Kubernetes scheduler backend adapters
- media processing adapters for audio/video/frame/transcription/embedding
- sub-agent or multi-agent runtime semantics
- long-running UI, or full eval platform

Verified release gates:

- `scripts/check_adapter_packages.py`
- Python unittest suite
- Go tests including adapter subpackages
- TypeScript tests and syntax checks including adapter subpath exports
- Rust tests with `adapters-all`
- cross-language parity script with markdown link and diff checks
- complete core parity/package dry-run script

Follow-up versions:

```text
1.2.x  adapter packaging fixes, framework-native smoke, and package docs polish
1.3.0  language-neutral Inspector: read-only DB/evidence consumer and static HTML debug report
1.3.x  richer Inspector/report UX, redaction, and evidence-driven replay/regression lab
1.4.0  sub-agent/multi-agent runtime semantics: parent-child runs, spawn/join, cancellation/failure/cost attribution
1.5.0  media adapter release: frame/audio/video refs, transcription/embedding adapters, stream transports
1.6.0  ModelGateway/ModelRouter contract: ctx.call_model, model events, provider injection, fallback/budget/replay semantics
1.6.x  optional model provider/router adapters, kept outside runtime-core
```

## v1.1.0 - Adapter Certification And Reliability Gate Upgrade

Status: implemented in the Python reference runtime-core as a backwards-compatible policy, adapter certification, and evidence regression upgrade.

Goals:

```text
replace bare allow/deny policy checks with a normalized decision contract
keep ToolGateway as the current enforcement point
preserve simple YAML/JSON role-capability policies
prepare future model, memory, output, media, sub-agent, and multi-agent gates
turn official adapter expectations into machine-readable certification bundles
make evidence regression output easier for CI and release gates to consume
avoid turning runtime-core into OPA, Cedar, DLP, eval, or governance UI
```

Implemented:

- `PolicyRequest` with `subject`, `action`, `resource`, `context`, `signals`, and `runtime_state`
- `PolicyDecision` with `effect`, `action_tier`, `risk_level`, `controls`, `reasons`, `findings`, `policy_version`, and delegation fields
- `PolicyFinding` and `PolicyControl` evidence/control objects
- built-in dependency-free evaluators for role capability, action boundary, and runtime state
- `ToolGateway` integration that records the full decision contract in `tool_permission_decided`
- compatibility for `PolicyEngine.check_tool(...)`
- contract fields for child-agent/delegation context without implementing sub-agent execution
- media/stream resource compatibility without implementing media processing adapters
- policy engine documentation and SVG diagrams
- `agentledger adapter certify` for official adapter certification bundles
- built-in certification profiles for Postgres, S3, MCP, Docker, OTEL, LangGraph, and Temporal
- explicit `production_validation.status=external-required` for adapter paths that require real infrastructure
- `evidence-regression` metadata summary with failed checks, changed dimensions, changed counts, bundle-hash status, and cost deltas

Explicitly not in this version:

- real OPA/Cedar adapters
- prompt injection, PII, DLP, or LLM safety providers
- policy management UI or governance backend
- sub-agent/multi-agent spawn/join runtime semantics
- full media processing adapters
- P2-style production claims for Postgres/S3/sandbox/worker/OTLP without real service credentials, concurrency/load checks, and restore or rollback drills

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
- adapter certification bundles for official adapter profiles
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

Implemented in the current v1.1.0 local reliability path:

- `evidence-regression` machine-readable summary for failed checks, changed dimensions, changed counts, bundle-hash status, and cost deltas

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

## Post-v1 - Inspector Evolution

Status: partially implemented in `1.3.0`. The current Inspector is a read-only evidence/runtime metadata consumer with static HTML export. Future work should stay in an optional package and remain outside runtime-core execution semantics.

Package names:

```text
agentledger-inspector
future package names may be added only if they remain read-only consumers
```

Preferred positioning:

```text
read-only local/internal web inspector
debug and audit UI for AgentLedger-owned runtime metadata
consumer of StateStore, BlobStore, evidence bundles, and static debug exports
```

Goals:

```text
make AgentLedger run history inspectable without reading raw database rows
visualize the same evidence that replay/debug/cost/failure commands already expose
keep runtime-core free of web framework dependencies
avoid write/control-plane features until permissions and safety are mature
```

Implemented in `1.3.0`:

- read-only SQLite runtime database input
- Postgres/MySQL runtime database input through documented adapter boundaries
- evidence-bundle input for cross-language runs
- static HTML export for shareable offline debugging
- Tool Ledger, approval, policy decision, cost/failure, artifact, and timeline read model

Follow-up work:

- run/session list with status, timestamps, cost summary, and failure summary
- run timeline for steps, events, model calls, tool calls, approvals, artifacts, and checkpoints
- state diff and state-version view
- Tool Ledger view with idempotency key, causal token, side-effect status, request/response refs, and unknown-state handling
- artifact/evidence browser with payload refs, blob hashes, media refs, and stream checkpoint refs
- cost and failure attribution panels
- configurable redaction for secrets, credentials, prompts, payload fields, and large blobs
- schema/version compatibility checks before reading a database

Explicit non-goals:

- mutating runtime state, approving/denying requests, canceling runs, or editing ledger rows in the first version
- replacing LangSmith, Langfuse, OpenTelemetry backends, or eval platforms
- bypassing the evidence/replay/export contracts by reading undocumented internals only

Exit criteria:

- a developer can point the inspector at a local `.agentledger/state.db` and inspect run timeline, state diff, Tool Ledger, cost, failures, and artifacts
- the same package can read Postgres/MySQL through documented schema/version checks
- the UI is useful as a local/internal debug tool without requiring a separate application backend
- all sensitive fields are redacted by default or explicitly configurable

## Post-v1 - Model Gateway And Router

Status: roadmap. This is a runtime boundary capability, but concrete model providers and routing engines should remain optional adapters.

Why it belongs at the runtime boundary:

```text
model calls affect cost, latency, replay, evidence, determinism, and policy
runtime is the layer that can record the selected provider/model and skip real calls during replay
budget enforcement and fallback semantics need to be visible before and after the model call
```

Core contract goals:

- `ctx.call_model(...)` or equivalent language-native API for runtime-managed model invocation
- `ModelGateway` contract for request validation, provider selection, execution, archival, and replay
- `ModelRouterPolicy` contract for rule-based routing by task, model family, cost, latency, context size, data policy, and allowed providers
- model-call events such as `model_call_requested`, `model_route_selected`, `model_call_completed`, `model_call_failed`, and `model_call_replayed`
- request/response refs in evidence bundles, with redaction and payload hashing
- token/cost attribution by run, step, agent role, provider, and model
- in-flight budget enforcement before expensive model calls
- fallback semantics and failure taxonomy for timeout, rate limit, policy denial, budget exceeded, provider failure, and malformed output
- replay semantics that reuse archived model responses instead of calling providers again
- shadow model comparison hooks that can compare provider/model output without producing tool side effects

Planned adapter layer:

- provider adapters for OpenAI, Anthropic, Gemini, Bedrock, Azure OpenAI, Ollama, and local/inference-server APIs where ecosystem demand exists
- optional LiteLLM-style adapter for users who already centralize provider routing elsewhere
- provider price catalog adapters, kept outside runtime-core
- policy adapters for org-specific model allowlists, region/data rules, and high-risk model approvals

Minimal first implementation:

```text
dependency-free ModelGateway interface
injected provider client for tests and application wiring
rule-based YAML/JSON router policy
model-call event/evidence/cost records
replay that returns archived model output
no mandatory provider SDK dependency in runtime-core
```

Explicit non-goals:

- bundling every model provider SDK into runtime-core
- replacing OpenAI, Anthropic, Gemini, Bedrock, Ollama, LiteLLM, or enterprise model gateways
- building a full model marketplace, billing system, prompt management platform, or managed router
- claiming deterministic model behavior beyond archived-response replay

Exit criteria:

- agent code can call a model through the runtime boundary and produce replayable model evidence
- budget/cost attribution records the provider/model selected for each call
- replay can skip real model calls and return archived responses
- provider routing is configurable without making runtime-core depend on provider SDKs

## Post-v1 - Sub-agent And Multi-agent Runtime Semantics

Status: roadmap. AgentLedger should not become a full multi-agent planner or collaboration framework, but it should provide reliable runtime primitives for sub-agent and multi-agent execution relationships.

Goals:

```text
make parent/child agent runs durable and replayable
make multi-agent execution evidence attributable across runs
keep orchestration/planning in frameworks such as LangGraph, AutoGen, CrewAI, Temporal, or user code
```

Planned runtime-core primitives:

- parent-child run links: `parent_run_id`, `parent_step_id`, `child_run_id`, `child_role`
- sub-agent lifecycle events: `agent_spawn_requested`, `agent_spawned`, `agent_joined`, `agent_spawn_failed`
- replay-safe join semantics that read prior child evidence instead of spawning duplicate child work
- cost/failure attribution from child runs back to the parent run and step
- cancellation propagation from parent run to child runs, with fencing for stale child workers
- policy, approval, sandbox, and budget inheritance rules for child runs
- evidence bundle links so parent and child runs can be reviewed together
- conformance fixtures for child run creation, cancellation, failure propagation, and replay-safe joins

Explicit non-goals:

- building a competing planner, debate system, voting system, or autonomous multi-agent collaboration engine
- replacing LangGraph, AutoGen, CrewAI, Temporal, Ray, or Kubernetes
- hiding sub-agent side effects from the normal Tool Ledger, approval, sandbox, and evidence pipeline

Exit criteria:

- a parent run can spawn and join a child run with durable evidence links
- child run failures and costs are visible in parent attribution reports
- parent cancellation fences child workers and records propagation evidence
- replay of a parent run does not create duplicate child runs or duplicate child side effects

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

The language plan should not block Python progress, but it must prevent semantic drift. The final target is native runtime-core parity across Python, Go, TypeScript, and Rust, not SDK-only packages.

| Language | First milestone | Runtime-ready milestone |
|---|---|---|
| Python | reference runtime | stable v1.0 runtime-core |
| Go | preview runtime-core parity baseline under `go/`, covering lease/cancel, Tool Ledger, policy/approval/sandbox, and cost/failure; infra adapters next | production adapters, worker/deployment hardening, and packaged per-language conformance |
| TypeScript | preview runtime-core parity baseline under `typescript/` with `.d.ts`; TS framework adapters next | production adapters, framework integration, and packaged per-language conformance for Node.js services |
| Rust | preview in-memory runtime-core parity baseline under `rust/`; persistence/async/worker components next | full runtime-core conformance or certified high-performance core subset |

Process:

1. keep Python as the reference implementation;
2. freeze shared contract and evidence/conformance fixtures;
3. maintain native runtime-core parity baselines in Go, TypeScript, and Rust without semantic drift;
4. keep optional framework, storage, sandbox, and observability integrations behind adapters;
5. move to a unified release train only after all stable language runtimes pass shared conformance.

Before parity, non-Python implementations may publish 0.x preview packages. After parity, runtime contract changes require synchronized language updates and conformance results.

See `MULTI_LANGUAGE.md` and `LANGUAGE_PARITY_MATRIX.md`.
