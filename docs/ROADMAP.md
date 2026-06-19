# Roadmap

AgentLedger should evolve in phases. Each phase proves a reliability claim before adding more surface area.

## Capability Scope Map

To avoid a bloated runtime, every large capability is split into three lanes: core contract, optional adapter, and explicit non-goal. Runtime-core should own production execution control points, state transitions, evidence, replay hooks, CLI checks, conformance, and safe defaults. Integrations that need heavy dependencies, offline batch runners, or deployment-specific choices should remain optional adapters or separate tools.

The route is a thin but indispensable runtime core: only build what cannot be guaranteed outside the runtime boundary. If a mature system already owns a layer well, AgentLedger should expose an adapter contract and conformance suite rather than rebuilding that layer.

Most capabilities should be evaluated in three layers: core contract, built-in minimal implementation, and optional production adapter. A minimal built-in keeps the project usable out of the box; production adapters let users connect mature systems without forcing those dependencies into core.

| Capability | Runtime-core owns | Optional adapters may own | Explicit non-goals for core |
|---|---|---|---|
| Planning / Workflow | adapter contract, runtime-managed checkpoints, evidence hooks, tool boundary integration | LangGraph, CrewAI, AutoGen, LangChain, Temporal, Prefect, Airflow, custom workflow adapters | building a competing planner, graph engine, or workflow engine |
| Eval / Evidence Consumers | evidence export, replay, deterministic rerun hooks, minimal side-effect-free regression checks, conformance fixtures, eval-adapter output formats | Langfuse, Phoenix, promptfoo, DeepEval, Ragas, OpenAI Evals, LangSmith/Braintrust-style consumers, CI report sinks | standalone Eval Platform, full offline evaluator that runs N agents x M cases, metrics service, test-case management, scorer management UI, or long-running eval web app |
| Tracing / Observability | structured events, trace JSONL, OTLP/JSON export, evidence links | OpenTelemetry SDK packages, collector recipes, external trace stores | full observability suite |
| Guardrails | ToolSpec schema validation, policy checks, approvals, pre/postcondition hooks, adversarial review gates | richer policy engines, org-specific rule packs, external review workflows | business-specific governance backend |
| Tool Gateway + Sandbox | ToolGateway, Tool Ledger, idempotency, audit, sandbox executor contract, fail-closed behavior | Docker, bubblewrap, Kubernetes/gVisor, E2B, Firecracker, custom executors | owning external sandbox infrastructure |
| Memory | session memory, short-term durable state, versioned memory refs, memory lifecycle events, projections, diffs, audit lineage, replayable memory reads/writes | vector stores, semantic retrieval, RAG, long-term knowledge stores, Mem0/Zep/Letta-style memory services | full knowledge base, semantic retrieval system, user-profile memory product, chat summarizer, or memory compression SDK |
| Session / HITL | run/session/step state machine, approval request lifecycle, audit events | external human review queues, chat/app integrations | business review backend or workflow back office |
| FinOps / Cost Control | token/call/cost records, budget enforcement hooks, cost attribution reports | provider price catalogs, finance exports, alerts | invoice or payment system |
| Inspector / Debug Viewer | stable read models, evidence export, static HTML debug export, redaction hooks, schema/version metadata | separate read-only local or internal inspector package | deployment management service, write/control plane in runtime-core |
| Runtime Model Evidence Boundary | model-call evidence, request/response archival, tool-call proposals, replay skipping, token/cost attribution, model failure evidence | provider SDKs, LiteLLM/new-api/one-api/enterprise gateways, policy packs, price catalogs | becoming a model router/gateway, bundling every model SDK, replacing provider SDKs or external gateways |
| Routing Advisor / Capability Router | candidate boundary only; no committed core feature. If future evaluation proves the boundary useful, runtime may record externally supplied route decisions as evidence and keep replay deterministic | possible WisePick-style capability router adapters or feedback clients, only if real usage justifies them | becoming a capability router, optimizing provider selection in core, or treating external routing decisions as authorization or idempotency keys |

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
| Model providers / gateways | OpenAI, Anthropic, Gemini, Bedrock, Ollama, LiteLLM, new-api, one-api, enterprise gateways | external execution/routing; AgentLedger records runtime model evidence, archived model responses, proposed tool calls, budget/failure/replay semantics |
| Routing advisors / capability routers | WisePick-style decision services, custom capability routers | candidate integration boundary only; no planned implementation until real usage proves the need |
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
Runtime Model Evidence Boundary after the model evidence contract is designed
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
external model providers and gateways: OpenAI, Anthropic, Gemini, Bedrock, Ollama, LiteLLM/new-api/one-api, or enterprise gateways through user code or optional endpoint adapters
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
LiteLLM, new-api, one-api, and enterprise model gateways
vector databases, RAG systems, long-term memory systems
eval platforms and benchmark runners such as Langfuse, Phoenix, promptfoo, DeepEval, Ragas, OpenAI Evals, LangSmith, or Braintrust
MCP tool servers and enterprise tool catalogs
routing advisors and capability routers such as WisePick-style services; candidate only, if future evaluation proves the boundary useful
```

AgentLedger should provide adapters, export formats, evidence bundles, trace correlation, and conformance checks for these layers.

### Should Stay Out Of Scope

These would make the project too broad or turn it into a different product:

```text
complete agent workflow engine
standalone eval platform
complete Langfuse/LangSmith replacement
complete RAG or memory platform
complete sandbox infrastructure platform
deployment management service, billing, organization admin
debug viewer write/control plane in the first inspector release
tool marketplace or app store
```

### Current Implementation Order After 1.4.2

1. Add framework-native examples and smoke fixtures for the most common adoption paths: OpenAI Agents SDK, LangGraph package compatibility, LangChain/CrewAI/AutoGen facades, and richer runtime-boundary examples.
2. Add a Temporal bridge example and optional adapter boundary that makes the ownership split explicit: Temporal owns workflow lifecycle and retries; AgentLedger owns node-internal tool/model/state reliability.
3. Improve Inspector as a language-neutral companion: better run-index filtering/search and a standalone viewer path for Go/TypeScript/Rust users who do not want Python in the application runtime.
4. Harden observability and eval exports beyond local JSON mapping: OTLP deployment recipes first, then Langfuse/Phoenix/promptfoo/DeepEval/Ragas/OpenAI-Evals/LangSmith-style evidence adapters without replacing those tools.
5. Continue production-pilot adapter hardening for Postgres, MySQL, S3/MinIO, workers, OTLP transport, and sandbox packages with real-service conformance, permission boundaries, backup/restore drills, and failure semantics.
6. Start the Runtime Memory Lifecycle baseline only after the model/tool/failure evidence path remains stable: memory refs, snapshots, reads/writes, diffs, lineage, replay semantics, and redaction hooks.
7. Add sub-agent/multi-agent runtime semantics as a focused reliability layer: parent-child run links, spawn/join events, cancellation propagation, replay-safe joins, and cost/failure attribution.
8. Extend media/stream support through optional processing adapters, keeping runtime-core limited to refs, metadata, lineage, checkpoints, and replay validation.

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

1. Add a focused OpenAI Agents SDK example that shows a runtime-managed tool call, approval gate, Tool Ledger record, model evidence, evidence export, and replay-safe debugging flow.
2. Add a Temporal bridge example that demonstrates the intended boundary: Temporal owns workflow lifecycle and retries; AgentLedger owns node-internal tool/model/state reliability.
3. Add standalone Inspector adoption paths for non-Python users: Docker image, single executable, static web viewer over exported evidence JSON, and/or Node/npm CLI/viewer package.
4. Add a Codex-assisted maintainer workflow document or script that helps with issue triage, release checklist preparation, adapter conformance checks, documentation consistency, and changelog drafting.
5. Keep `OPEN_SOURCE_IMPACT.md`, `MAINTAINER_NOTES.md`, and `USE_CASES.md` current as the public explanation of ecosystem value, maintenance responsibility, and practical adoption scenarios.
6. Collect real usage evidence without inflating claims: examples, discussions, issues, integration notes, package downloads, external demos, and real-service hardening reports.

Adoption evidence work:

1. Keep the cross-language 3-minute side-effect safety demo current and runnable after every release.
2. Keep the cross-language MCP governance example current and make it easy to compare with real MCP SDK integrations later.
3. Record a short GIF or terminal screencast showing the runtime path: `run -> tool call -> approval -> crash -> resume -> replay evidence`.
4. Write one technical article with a clear thesis, for example "Agents Need a Runtime, Not More Retries" or "Making AI Agents Durable, Auditable, and Replayable".
5. Keep the README opening focused on the user pain: "Your agent called a tool. Did it happen? Can you retry safely? Can you prove it later?"
6. Create public issues or discussions for the next adoption tasks: OpenAI Agents SDK approval/replay example, standalone Inspector viewer, Temporal bridge example, tool-injection risk scanner, and memory lifecycle design.
7. Publish one or two real integration notes or case studies, such as using AgentLedger to audit tool calls in a legal agent, without including private data.

Companion product directions:

| Direction | Why it matters | Packaging boundary |
|---|---|---|
| AgentLedger Inspector | makes runs visible through timeline, Tool Ledger, approvals, replay diff, artifacts, cost, and failure attribution | separate read-only local/internal tool, not runtime-core UI |
| Tool Governance / MCP Gateway | enforces schema, permission, approval, sandbox, audit, and idempotency before tool side effects | optional gateway package or reference service |
| Eval adapters / Replay regression | lets teams test prompt, model, tool-schema, or agent-logic changes against historical evidence without repeating side effects | evidence exporters and CLI/CI companions over evidence bundles; no standalone eval platform |
| Production Harness Blueprint | shows how AgentLedger composes with LangGraph/OpenAI Agents SDK, Temporal, Langfuse/OTel, MCP, Postgres/S3, and Docker sandbox | examples, templates, and deployment recipes |
| Agent Security Scanner | detects tool boundary bypass, risky tool schemas, missing approval/sandbox, secret exposure, and sensitive evidence artifacts | optional scanner command or separate package |

The adoption goal is not to chase stars directly. It is to make the project understandable and verifiable within a few minutes: without AgentLedger, users often cannot tell what happened after an agent failure; with AgentLedger, they can inspect, resume, replay, and govern tool side effects.

Mentioning OpenAI Agents SDK here means a planned ecosystem example and adapter target. It does not imply official OpenAI partnership, endorsement, certification, or completed production integration unless a later release explicitly documents that evidence.

Explicit non-goals for this track:

```text
do not describe AgentLedger as a mature large-adoption project until evidence exists
do not add marketing-only claims that are not backed by examples or conformance
do not turn the repo into a full harness product or standalone eval platform
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

Candidate follow-up release trains:

```text
1.5.0  framework/Temporal adoption: OpenAI Agents SDK example, Temporal bridge, framework-native smoke fixtures
1.6.0  standalone Inspector and evidence consumer UX: non-Python viewer path, model-call panel, filtering/search
1.7.0  Runtime Memory Lifecycle: memory refs, snapshots, reads/writes, diffs, lineage, replay semantics
1.8.0  sub-agent/multi-agent runtime semantics: parent-child runs, spawn/join, cancellation/failure/cost attribution
1.9.0  media adapter release: frame/audio/video refs, transcription/embedding adapters, stream transports
1.x    production-pilot adapter hardening can ship in patch/minor releases when real-service evidence is available
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

## Post-v1 - Reliability Harness and Eval Adapters

Goals:

```text
make prompt/workflow/runtime changes testable
turn evidence into regression inputs for external and local checks
connect AgentLedger evidence to mature open-source eval tools
```

Implemented in the current v1.1.0 local reliability path:

- `evidence-regression` machine-readable summary for failed checks, changed dimensions, changed counts, bundle-hash status, and cost deltas

Direction:

AgentLedger should not build a standalone Eval Platform. Eval platforms can use AgentLedger, but they should not be required to use it. The runtime should provide high-quality evidence and replay outputs that mature eval tools can consume.

Planned adapter/export work:

- evidence bundle to Langfuse dataset/score/experiment inputs
- evidence bundle to Phoenix dataset/experiment/eval-span inputs
- evidence bundle to promptfoo YAML/JSON test cases
- evidence bundle to DeepEval test cases and metrics inputs
- evidence bundle to Ragas dataset rows for RAG/agent workflow evaluation
- evidence bundle to OpenAI Evals-style sample records
- failure, policy, model, tool, and cost evidence mapped to eval sample metadata
- replay result to regression report inputs for CI gates

Planned local evidence-consumer improvements:

- richer replay/rerun divergence report with more drill-down and fixture UX
- richer repro harness UX for named golden evidence fixtures
- larger real-world benchmark corpus for historical runs beyond the current built-in seed fixtures
- cost attribution regression report
- failure attribution summaries
- richer adversarial review policy packs and release gates
- shadow mode comparison workflows
- additional real-world golden evidence fixtures
- replayable media pipeline support for frame/audio segment indexes, timeline metadata, and evidence-linked derived artifacts

Explicit non-goals:

- building dataset management, scorer management, leaderboard, or experiment dashboard inside AgentLedger
- running a long-lived eval service or web application
- replacing Langfuse, Phoenix, promptfoo, DeepEval, Ragas, OpenAI Evals, LangSmith, Braintrust, or custom CI systems
- claiming online runtime safety from offline eval scores; runtime policy enforcement remains in AgentLedger/policy engine

Exit criteria:

- prompt/workflow changes can be shadow-run against historical evidence
- replay divergence is reported at event/state/artifact level
- media pipeline replay can reuse captured frame/segment artifacts instead of reprocessing raw media
- regression and external eval results link back to evidence bundles
- at least two mature eval tools can consume AgentLedger evidence through documented adapters without reading undocumented runtime tables

## 1.4.0 - Agent Failure Lifecycle

Status: implemented as a runtime-core baseline in 1.4.0 across Python, Go, TypeScript, and Rust. AgentLedger records and reports runtime-owned failure evidence, including worker crashes, lease expiry, stale worker fencing, cancellation, retry exhaustion, policy denial, sandbox failure, tool/model/runtime failures, budget failures, unknown side-effect states, and replay divergence. The 1.4.0 baseline makes this a portable lifecycle: classify, attribute, recover, inspect, regress, and export.

Scope:

```text
agent execution failure belongs in runtime-core when the runtime boundary is required
agent answer-quality failure belongs in evidence consumers, eval tools, or adapters
```

Implemented in 1.4.0:

- failure taxonomy for runtime, agent, tool, model, policy, sandbox, budget, cancellation, and retry paths
- failure attribution report and cost/failure attribution records
- failure injection suite for crash, retry, lease fencing, cancellation fencing, and side-effect safety
- evidence bundles that include failed steps, failure events, Tool Ledger state, cost records, approval/policy decisions, artifacts, and replay refs
- Inspector and static debug views that can surface failure events, risk flags, cost/failure records, and event timelines
- cross-language conformance coverage for failure injection, cost/failure attribution, scheduler recovery, cancellation, replay, and shadow/evidence regression
- stable `AgentFailure` / `FailureEnvelope` read model with normalized category, severity, recoverability, retryability, owner, causal refs, and evidence refs
- failure lifecycle events such as `failure_detected`, `failure_classified`, `failure_recovery_scheduled`, `failure_recovered`, `failure_terminal`, and `failure_regressed`
- causal graph linking model calls, tool calls, state commits, approval decisions, sandbox runs, worker leases, and runtime evidence to one failure chain
- failure replay plan that can explain whether investigation can reuse archived evidence or must block unsafe side-effect replay
- failure regression analyzer for recurring failures, fixed failures, and newly introduced failures
- failure export format for external observability, incident review, eval, and support systems
- local alert records for terminal failures, unknown side-effect states, costly failures, and unsafe replay blocks
- Inspector panels for failure lifecycle, replay plan, alert records, causal graph, and evidence links

Follow-up adapter / evidence-consumer work:

- deeper Langfuse/LangSmith/OpenTelemetry live exporter integrations beyond local JSON mapping
- Temporal/Ray/Kubernetes failure propagation recipes that preserve AgentLedger failure evidence inside external execution backends
- eval adapter examples that consume AgentLedger evidence in tools such as Langfuse, Phoenix, promptfoo, DeepEval, Ragas, or OpenAI Evals to detect answer-quality failures, hallucination, policy misses, or task-level correctness regressions
- alerting/report sinks that send local alert records to concrete external systems

Explicit non-goals for runtime-core:

- becoming a full incident-management system
- becoming a full eval or LLM-judge platform
- claiming that runtime failure attribution proves answer correctness
- automatically retrying unsafe side effects without Tool Ledger, approval, sandbox, and replay evidence
- hiding external framework or backend failures from the evidence bundle

Exit criteria:

- every terminal run failure has a normalized failure envelope and causal evidence refs
- recoverable failures can be retried or resumed without duplicating side effects
- replay can explain whether a historical failure would call external systems again or reuse archived evidence
- Inspector can show a failure timeline that links to the relevant model/tool/state/policy/sandbox records
- external eval or observability systems can consume failure evidence without reading undocumented runtime tables

## Post-v1 - Runtime Memory Lifecycle

Status: roadmap. AgentLedger should not become a memory product, vector database, RAG framework, or memory compression SDK. The runtime should own only the memory semantics that affect execution correctness, replay, audit, recovery, and governance.

Positioning:

```text
Runtime Memory Lifecycle makes memory explainable and replay-safe.

It records what memory an agent read, what memory it wrote, which
snapshot was visible during a run, how projections changed over time,
and whether a later replay is using the same memory facts or a changed
view.
```

Why it belongs at the runtime boundary:

```text
memory reads affect model decisions, tool calls, approvals, and costs
memory writes can pollute future runs or hide why an action happened
replay must know whether it is reusing the original memory snapshot or reading mutable external state
audit must answer which memory facts led to a decision or side effect
```

Lossless vs. compressible boundary:

```text
Lossless runtime state must not be summarized away:
  current node, retry count, tool results, approvals, checkpoints,
  ledger status, failure state, and replay refs.

Compressible context can be externalized through adapters:
  chat history, observations, search results, reasoning notes,
  retrieved passages, and conversation summaries.
```

This keeps AgentLedger focused on runtime evidence. Memory compression can still be useful, but it should remain an adapter/evidence-consumer concern unless it changes replay, audit, recovery, or governance guarantees.

Runtime-core goals:

- `MemoryRef` for stable references to runtime-visible memory entries, projections, and snapshots
- `MemoryScope` for run, session, agent, shared, and external memory boundaries
- `MemorySnapshot` for the memory view visible to a run, step, model call, or tool call
- `MemoryReadEvent` and `MemoryWriteEvent` linked to run ids, step ids, model calls, tool calls, approvals, and policy decisions
- `MemoryProjection` read models derived from the append-only event log, such as current task state, active constraints, known user/project facts, or tool retry state
- `MemoryDiff` for detecting memory drift, pollution, deleted facts, changed constraints, and replay divergence
- `MemoryAudit` / lineage records that explain which memory facts influenced a decision, tool call, approval, or failure
- retention and redaction policy hooks for memory refs and snapshots
- replay semantics that can freeze a historical memory snapshot instead of re-querying mutable external memory

Minimal built-in implementation:

```text
dependency-free memory refs backed by the existing StateStore/BlobStore/EventLog
snapshot export inside evidence bundles
projection builder from runtime events to materialized read models
diff command/report for two snapshots or two projection versions
Inspector links from model/tool/failure records back to memory refs
```

Optional adapter layer:

- Mem0, Zep, Letta, vector databases, RAG systems, knowledge stores, and enterprise memory services
- adapter contracts for importing external memory reads/writes as runtime-visible refs
- retrieval-output capture so RAG results can be replayed and audited without making AgentLedger own retrieval
- redaction adapters for memory fields that contain private user, customer, or project data

Explicit non-goals for runtime-core:

```text
do not build a vector database
do not build a RAG framework
do not build a user-profile memory product
do not build a general chat summarizer or context-compression SDK
do not claim semantic memory makes agents smarter; the runtime claim is replay, audit, governance, and recovery
```

Exit criteria:

- a run can record exactly which memory snapshot was visible at each important execution boundary
- replay can either reuse the archived memory snapshot or explicitly report that mutable external memory would be read
- Inspector/evidence can answer which memory refs contributed to a model decision, tool side effect, approval, or failure
- memory diffs can identify changed facts, deleted facts, newly introduced constraints, and drift between two runs or two snapshots
- external memory systems can integrate through adapters without bypassing evidence, policy, redaction, and replay contracts

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

Implemented in `1.3.2`:

- configurable Inspector redaction policy for JSON and static HTML output
- CLI support for `--redact-key`, `--redaction-policy`, and `--redaction-replacement`
- `InspectorRedactionPolicy` API for custom read-model consumers

Implemented in `1.3.3`:

- stable read-model anchors for timeline, step, Tool Ledger, approval, policy, and artifact rows
- static HTML section navigation and internal cross-links between related runtime records

Implemented in `1.3.5`:

- chronological Event Stream in JSON and static HTML reports
- read-only run index with status, timestamps, cost summary, failure summary, and optional single-run links
- runtime run id and extracted agent run id in event/timeline rows
- paginated run-list static HTML and full-width JSON/details rows for Inspector, evidence, and time-travel tables

Implemented in `1.4.0`:

- `agentledger.failure.envelope.v1` normalized failure read model
- `agentledger.failure.lifecycle.v1`, `agentledger.failure.causal_graph.v1`, `agentledger.failure.replay_plan.v1`, `agentledger.failure.regression.v1`, `agentledger.failure.alerts.v1`, and `agentledger.failure.export.v1`
- failure lifecycle data in `agentledger failure report` and portable export data from `agentledger failure export`
- failure regression comparison through `agentledger failure regress`
- Inspector Failure Lifecycle, Failure Replay Plan, Failure Alerts, and Failure Causal Graph panels
- non-happy-path tests for missing event payloads, retry scheduling, pending approvals, pending tool verification, blocked tools, unsafe replay planning, terminal failure reports, export mappings, and Inspector HTML rendering

Follow-up work:

- richer filtering, search, pagination, and saved views for the read-only run index
- standalone Inspector distribution for non-Python users: Docker image, single executable, static web viewer over exported evidence JSON, and/or Node/npm CLI/viewer package
- run timeline for steps, events, model calls, tool calls, approvals, artifacts, and checkpoints
- state diff and state-version view
- Tool Ledger view with idempotency key, causal token, side-effect status, request/response refs, and unknown-state handling
- artifact/evidence browser with payload refs, blob hashes, media refs, and stream checkpoint refs
- cost and failure attribution panels
- richer redaction presets for prompts, large blobs, and project-specific evidence fields
- schema/version compatibility checks before reading a database

Explicit non-goals:

- mutating runtime state, approving/denying requests, canceling runs, or editing ledger rows in the first version
- replacing LangSmith, Langfuse, OpenTelemetry backends, or eval platforms
- bypassing the evidence/replay/export contracts by reading undocumented internals only

Exit criteria:

- a developer can point the inspector at a local `.agentledger/state.db` and inspect run timeline, state diff, Tool Ledger, cost, failures, and artifacts
- the same package can read Postgres/MySQL through documented schema/version checks
- the UI is useful as a local/internal debug tool without requiring a separate application backend
- Go, TypeScript, and Rust users can consume the official Inspector viewer without installing a Python package into their application runtime
- all sensitive fields are redacted by default or explicitly configurable

## 1.4.1 - Runtime Model Evidence Boundary

Status: implemented as a small runtime-core evidence upgrade. AgentLedger does not become a model router, model gateway, provider SDK wrapper, or LiteLLM/new-api/one-api replacement. The runtime records model evidence that user code, agent frameworks, SDKs, or external gateways already produced.

Why this belongs at the runtime boundary:

```text
model outputs can cause tool calls and side effects
model failures can explain agent failures
model requests/responses must be replayable without calling providers again
model token/cost records need run/step/agent attribution
model-proposed tool calls must be distinguishable from runtime-executed tool calls
```

Implemented in `1.4.1`:

- dependency-free `agentledger.model.evidence.v1` evidence schema
- external model-call recording APIs in Python, Go, TypeScript, and Rust
- `model_call_requested`, `model_call_completed`, `model_call_failed`, and `tool_call_proposed` events
- request/response/failure payload archival in the Python reference runtime
- token/USD cost attribution for externally recorded model calls
- `model_call_failed` participation in failure envelopes, lifecycle, alerts, replay plans, Inspector timeline, and adversarial review checks
- compatibility wrapper for the previous simple `recordModelCall` / `record_model_call` style in non-Python runtimes

Integration model:

```text
user code / framework / provider SDK / model gateway
  -> executes model call
  -> records model evidence in AgentLedger
  -> model may propose a tool call
  -> runtime executes tools through ToolGateway / Tool Ledger
```

AgentLedger should treat LiteLLM, new-api, one-api, provider SDKs, and enterprise model gateways as external systems. They can own routing, retry, timeout, key management, fallback, and provider-specific compatibility. AgentLedger owns the resulting runtime evidence, cost/failure attribution, replay behavior, and tool proposal link.

Explicit non-goals:

- no model routing or provider selection engine in runtime-core
- no dedicated LiteLLM/new-api/one-api adapter unless a future integration proves a narrow evidence-only boundary
- no bundled provider SDKs
- no provider timeout/retry/rate-limit execution policy
- no claim that archived model outputs make model behavior deterministic beyond replaying recorded evidence

Follow-up work:

- optional policy hook for high-risk model requests, data-classification evidence, and redaction decisions
- standalone Inspector packaging for Go/TypeScript/Rust users who do not want Python installed in the application runtime

Exit criteria:

- a model call made outside AgentLedger can still be attached to a run/step with archived request/response evidence
- model failures produce normalized failure evidence without requiring AgentLedger to own provider retry logic
- model-proposed tool calls are visible before the actual ToolGateway execution
- replay/debug/evidence consumers can inspect model evidence without contacting a model provider

## 1.4.2 - Model Evidence UX, Export, And Boundary Lint Consolidation

Status: implemented as a four-language 1.4.x release train with Python reference tooling improvements. Runtime-core event semantics remain aligned across Python, Go, TypeScript, and Rust; Inspector and boundary lint remain companion/read-model tooling distributed through the Python reference package.

Implemented in `1.4.2`:

- Inspector `Model Calls` panel for archived request/response/failure refs, usage, cost, provider/model metadata, and failure status
- Inspector `Tool Proposals` panel for `tool_call_proposed` records before ToolGateway execution
- stronger read-model links between model calls, proposed tool calls, runtime events, Tool Ledger rows, and failure records
- failure export model evidence refs and proposed-tool refs for Langfuse, OpenTelemetry, LangSmith, Temporal-style consumers, and local CI
- boundary lint hardening for direct database clients, direct filesystem mutation, model SDK bypasses, and risky ToolSpec metadata
- dependency-free model evidence example showing externally executed gateway/provider calls recorded into AgentLedger without provider routing

Explicit non-goals:

- no model gateway/router in runtime-core
- no bundled provider SDKs
- no standalone eval platform
- no native Inspector rewrite in Go/TypeScript/Rust for this patch

Exit criteria:

- a developer can open Inspector and see model-call evidence separately from tool execution evidence
- a model-proposed tool call can be traced to the eventual ToolGateway/Tool Ledger record when names or refs are available
- failure exports expose model evidence and proposed-tool refs without sending data to third-party platforms
- boundary lint catches common bypasses before runtime instrumentation is accidentally skipped

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

---

generated by codex cli
