# Extensibility and Adapter Model

The runtime must be extensible at every layer. Core should define stable contracts and invariants; adapters provide concrete integrations.

## Design Principle

```text
Core owns protocol and invariants.
Adapters own integration details.
No adapter should pollute runtime core.
Python is the reference implementation, not the protocol boundary.
If core is not the only layer that can enforce the guarantee, prefer an adapter.
```

AgentLedger should stay a thin but indispensable core. It should not rebuild mature planning, workflow, observability, eval, RAG, sandbox, or deployment systems. Instead, it should define the runtime boundary those systems can plug into and the conformance checks that prove they preserve runtime invariants.

## Adapter Maturity Model

Each extension point should be described with three explicit levels:

```text
Core contract
  Interface, event shape, state transition, failure semantics, and invariants.

Built-in minimal implementation
  Dependency-free reference behavior that is good enough for local development,
  examples, tests, and simple deployments.

Optional production adapter
  Integration with mature external systems, stronger isolation, stronger scale,
  or framework-native behavior.
```

Examples:

| Area | Core contract | Built-in minimal implementation | Optional production adapter |
|---|---|---|---|
| Storage | `StateStoreProtocol`, migrations, lease/fencing invariants | SQLite WAL + local blob store | Postgres, S3/MinIO, custom store |
| Sandbox | `SandboxPolicy`, `SandboxExecutor`, fail-closed routing, audit/evidence | fail-closed `none`, local executor, dry-run manifests | Docker, E2B, bubblewrap, Kubernetes/gVisor, Firecracker |
| Observability | structured events, evidence links, trace span shape | JSONL and OTLP/JSON export | OpenTelemetry SDK, collector recipes, trace stores |
| Policy | capability checks, approvals, pre/postcondition hooks | YAML/JSON role-capability policy | OPA, Cedar, internal policy service |
| Frameworks | `FrameworkAdapter`, `AgentContext`, `ToolGateway` boundary | plain Python and dependency-free facades | framework-native packages and smoke fixtures |
| Media/Stream | durable refs, metadata, lineage, stream cursors | artifact contracts and tool schema conventions | codecs, transcription, frame extraction, stream transport |

## Extension Points

| Layer | Interface | Common Implementations |
|---|---|---|
| State | `StateStore` | SQLite WAL, Postgres |
| Events | `EventStore` | DB table, Kafka/Redpanda optional |
| Blob | `BlobStore` | local fs, S3, MinIO |
| Tools | `ToolExecutor` | local function, HTTP, MCP, sandbox executor |
| Policy | `PolicyEngine` | YAML, custom RBAC, OPA/Cedar adapter later |
| Sandbox | `SandboxExecutor` / `SandboxConfig` | none, local, bubblewrap, Docker, E2B, Kubernetes/gVisor, Firecracker, custom |
| Model | `ModelProvider` | OpenAI, Anthropic, local model, replay provider |
| Framework | `FrameworkAdapter` | LangChain, LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, custom |
| Worker | `WorkerProtocol` | Python SDK, TypeScript client, JSON-RPC, gRPC, HTTP |
| Observability | `TraceExporter` | local logs, OpenTelemetry, LangSmith-style backend |
| Evidence Regression | `EvidenceRegressionRunner` as side-effect-free evidence checker | local invariant checks, external eval consumer adapters, CI gates |
| Media and Streams | `MediaArtifact` / `EventStreamCheckpoint` | image/audio/video/frame refs, transcript refs, stream chunk refs, external stream adapters |

## Framework-agnostic Runtime Contract

Core objects:

```text
RunSpec
SessionState
StepClaim
AgentContext
ToolRequest
ToolResult
StatePatch
MemoryProposal
ArtifactRef
RuntimeEvent
EvidenceBundle
```

Any agent framework can integrate if it can map its own concepts to these objects.

## Package Layout Target

```text
runtime-core
  protocol, state, event, ledger, replay, invariants

runtime-sdk-python
  AgentContext, decorators, local runner, CLI

runtime-sdk-typescript
  worker client, tool registration, protocol client

runtime-adapters-langgraph
runtime-adapters-openai-agents
runtime-adapters-crewai
runtime-adapters-autogen
runtime-adapters-llamaindex
runtime-adapters-semantic-kernel
runtime-adapters-mcp

runtime-storage-postgres
runtime-blob-s3
runtime-sandbox-docker
runtime-otel
```

## Adapter Contract

A framework adapter should implement some or all of:

```python
class FrameworkAdapter:
    def map_run_spec(self, framework_run): ...
    def map_step(self, framework_step): ...
    def persist_checkpoint(self, checkpoint): ...
    def capture_model_call(self, request, response): ...
    def capture_tool_call(self, request, response): ...
    def emit_runtime_event(self, event): ...
    def wrap_tool(self, tool): ...
```

Rules:

- adapters are optional packages
- core must not import adapter dependencies
- adapter tests run separately from core tests
- adapter should pass the relevant conformance runner before certification

## Storage Adapters

Storage must be pluggable because local dev and production have different needs.

AgentLedger is storage-opinionated by default, but storage-extensible by design. The default SQLite backend manages AgentLedger metadata tables and `schema_migrations` automatically; enterprise users can bring their own backend by implementing the StateStore contract and preserving runtime invariants.

Recommended defaults:

```text
v0.1:
  SQLite WAL + local blob store

production pilot:
  Postgres + S3/MinIO

high-throughput optional:
  Postgres for state + Kafka/Redpanda for event stream + S3/MinIO for payloads
```

Important: Redis/cache/queue systems may assist scheduling, but should not be the source of truth for durable state.

## MCP Adapter

MCP should sit behind Tool Gateway:

```text
Agent
  -> Runtime Tool Gateway
  -> Policy / Ledger / Audit / Sandbox
  -> MCP Client
  -> MCP Server
  -> External Resource
```

MCP standardizes tools and context; the runtime adds policy, audit, idempotency, side-effect handling, and replay safety.

## Communication Adapters

WhatsApp, Telegram, Matrix, Slack, email, and webhooks are channel adapters, not core runtime.

Flow:

```text
External Message
  -> Channel Adapter
  -> idempotency check by external_message_id
  -> append session event
  -> create or continue run
  -> Agent response
  -> outbound message ledger
```

Adapter responsibilities:

- duplicate delivery handling
- external message id mapping
- rate limit and backpressure
- channel secret management
- session mapping
- replay-safe outbound messages

## Multi-language Support

Python is the current reference runtime, but the project should not stop at Python or SDK-only packages. Go, TypeScript, and Rust should share the same runtime contract, golden fixtures, and runtime-ready gate.

Each language can start with a smaller role, but parity requires native runtime-core conformance:

```text
Go: native worker/runtime baseline, infra workers, Kubernetes/controller adapters
TypeScript: protocol client first, then Node runtime-core and TS framework adapters
Rust: high-performance runtime primitives, replay/sandbox/worker components
```

The current contract artifact is exported with:

```bash
PYTHONPATH=src python3 -m agentledger contract export
```

and checked in at `contracts/agentledger.runtime.v1.json`.


## Current Adapter Scaffold

The repository currently includes a minimal adapter contract in `src/agentledger/adapters.py`:

```text
FrameworkAdapter
PythonFunctionAdapter
python_agent decorator
LangGraphCheckpointerAdapter
LangGraphNodeAdapter
LangChainRunnableAdapter
CrewAIAdapter
AutoGenAdapter
OpenAIAgentsSDKAdapter
LlamaIndexAdapter
SemanticKernelAdapter
MCPToolAdapter
FrameworkAdapterConformanceRunner
StateStoreProtocol / BlobStoreProtocol / ToolExecutorProtocol / ModelProviderProtocol
```

This is intentionally small. The built-in framework facades call conventional methods such as `invoke`, `kickoff`, `generate_reply`, or `run` without importing those frameworks. Heavier integrations such as exact LangGraph, CrewAI, AutoGen, LlamaIndex, Semantic Kernel, OpenAI Agents SDK, and MCP packages should live behind optional adapters and must not become runtime-core dependencies.

Framework adapters can use `FrameworkAdapterConformanceRunner` or the CLI fixture:

```bash
PYTHONPATH=src python3 -m agentledger adapter conformance --kind langchain
```

The fixture checks that the adapter maps a run spec, returns a `Runtime.run_once`-compatible callable, completes a local run, and produces exportable evidence.


## Protocol Boundary

`src/agentledger/protocol.py` defines runtime-checkable protocols for the core extension seams:

```text
StateStoreProtocol
BlobStoreProtocol
ToolExecutorProtocol
ModelProviderProtocol
```

These protocols are intentionally small and dependency-free. Storage, model, sandbox, MCP, and framework integrations should implement these contracts before they are wired into runtime-core.

## LangGraph Skeleton

`src/agentledger/adapters_langgraph.py` provides a dependency-free checkpointer/node facade. It supports the common checkpointer operations `put`, `get`, `get_tuple`, `list`, and `put_writes` using plain dictionaries, plus async counterparts. Runtime core still does not import LangGraph; a future optional package can wrap these records with LangGraph's exact classes.

## MCP Skeleton

`src/agentledger/adapters_mcp.py` maps MCP-style tool descriptors into `ToolSpec`. MCP invocation still goes through `ToolGateway`, so policy, ledger, audit, budget, replay, and shadow mode semantics remain runtime-owned.

The dependency-free MCP fixtures include:

```text
InMemoryMCPToolServer
InMemoryMCPContextServer
MCPToolAdapter
MCPContextAdapter
```

`MCPContextAdapter` exposes resource reads as a runtime-managed tool such as `mcp.context.read`, so context access is still policy/audit/evidence visible. See `examples/mcp_context/basic_context_server.py`.

`ToolRegistry.manifest()` and `ToolRegistry.openai_tools()` expose registered tools without importing model SDKs. Adapter packages should use these catalog exports rather than bypassing `ToolGateway`.

## Media and Event-stream Adapter Boundary

Media and stream support is a reliability contract, not a codec stack. Runtime core should store durable references, metadata, lineage, and resumable cursors; adapters should own capture, decoding, transcription, frame extraction, stream transport, and provider-specific APIs.

Core contracts:

```text
MediaArtifact
  kind, uri/content_ref, media metadata, lineage, derived output refs

EventStreamCheckpoint
  stream_id, consumer_id, offset, watermark, chunk ref, partial result ref

StreamChunkRef
  immutable chunk id, offset, content_ref/content_hash, sequence/event time
```

Runtime-owned invariants:

```text
raw media payloads stay behind BlobStore or external durable refs
media artifacts have stable refs and lineage when derived from tools
stream consumers persist offsets before retry/resume boundaries
replay validates refs and checkpoints without re-consuming external streams
evidence, trace, diff, evidence regression, backup, and retention treat media refs as first-class evidence
```

Adapter-owned responsibilities:

```text
transcription, frame extraction, embedding, summarization, and stream IO
external storage lifecycle for large media objects
provider-specific retry/backpressure behavior
redaction or access-control for sensitive media refs
conversion of provider outputs into MediaArtifact or EventStreamCheckpoint records
```

The dependency-free tool conventions in `src/agentledger/media_tools.py` define portable schemas for:

```text
audio.transcribe
video.extract_frames
frame.describe
video.summarize
stream.consume
stream.emit
```

These are conventions, not mandatory built-ins. A media adapter may register any subset with executor implementations, but calls should still flow through `ToolGateway` so policy, ledger idempotency, audit, replay, and evidence semantics remain runtime-owned.

## Runtime Boundary Lint

`RuntimeBoundaryLinter` is a dependency-free AST checker for direct calls that bypass runtime-managed seams. It flags common shell, HTTP, email, cloud SDK, GitHub SDK, and model SDK calls such as OpenAI, Anthropic, LiteLLM, Google GenAI, Mistral, Cohere, Groq, Ollama, and Vertex AI so framework adapters and examples can keep side effects behind `ctx.call_tool` or the runtime model boundary.

```bash
PYTHONPATH=src python3 -m agentledger lint boundary ./examples ./my_agents
PYTHONPATH=src python3 -m agentledger lint boundary ./my_agents --exclude .venv --no-fail
PYTHONPATH=src python3 -m agentledger lint boundary ./my_agents --rules examples/lint/boundary_rules.json
PYTHONPATH=src python3 -m agentledger lint boundary ./my_agents --rules examples/lint/boundary_rules.json --replace-defaults
```

Project-specific rule packs are dependency-free JSON files. Each rule has `rule_id`, `pattern`, `category`, `message`, `suggestion`, and optional `prefix`. By default, custom rules are appended to the built-in rules; `--replace-defaults` makes the scan use only the supplied rule pack.

The linter is intentionally best-effort. It is not a security sandbox and cannot prove that arbitrary dynamic Python code is safe. It exists to catch common bypasses during development and CI before they become invisible production side effects.

Inline suppressions are explicit:

```python
# agentledger: ignore-next-line
os.system("allowed by local project policy")

os.system("allowed")  # agentledger: ignore-boundary
```

## Store Conformance for Adapters

Storage adapters should pass `StateStoreConformanceRunner` before they are considered runtime-compatible. The current checks cover create/claim/commit, stale lease fencing, expired lease recovery, and cancellation fencing. Backends used by worker pools should also pass `WorkerConformanceRunner`, which checks distinct multi-worker claims, heartbeat fencing, and recovery fencing against a shared backing store. Adapter packages can reuse these runners against Postgres, remote stores, or embedded stores.

## BlobStore Conformance for Adapters

Blob adapters should implement `BlobStoreProtocol` and pass `BlobStoreConformanceRunner`. The current checks cover JSON roundtrip, stable content-addressed refs, and rejection of unsupported refs. `LocalBlobStore` is the default local implementation; `S3BlobStore` is an experimental S3/MinIO-compatible adapter with optional boto3 loading and injected-client support.

## Worker Adapter Boundary

`LocalWorker` is intentionally small and dependency-free. `WorkerService` wraps it into a process-shaped loop with idle backoff, graceful stop, optional signal handlers, and structured run summaries. Distributed worker implementations should preserve the same control flow: recover expired leases, claim via the StateStore, execute through Runtime/AgentContext, and let store transitions define correctness.


## Observability Adapter Boundary

`TraceExporter` emits dependency-free JSONL spans from evidence events. `OTLPTraceExporter` translates the same spans into OTLP/JSON without importing OpenTelemetry SDKs and can optionally POST that JSON to a configured collector. Observability adapters should preserve this format for OpenTelemetry collectors, LangSmith-style backends, or custom trace stores without changing runtime-core event semantics.

`TimeTravelDebugger` is also event-log based. It reconstructs committed state by applying initial state and committed JSON merge patches in event sequence order. Debugging adapters or UIs should preserve this read-only, side-effect-free model.

## Postgres Adapter Boundary

`PostgresStore` is an experimental psycopg-backed adapter path with DDL, migrations, native `FOR UPDATE SKIP LOCKED` worker claiming, and connection-injection conformance coverage. A production adapter should still keep driver details optional, add real-service integration tests, and pass `StateStoreConformanceRunner` plus `WorkerConformanceRunner` against an actual Postgres instance.

## Diff and Regression Boundary

`EvidenceDiffer` is intentionally evidence-based rather than framework-based. Shadow mode, replay regression, prompt comparison, and workflow migration tests should compare evidence bundles instead of re-calling tools or model providers.


## Sandbox Adapter Packages

Runtime core owns the contract and audit trail; adapter packages own backend-specific execution. A backend adapter should implement `SandboxExecutor.run_tool(...)`, respect `SandboxPolicy`, and return `SandboxResult` without leaking secrets into metadata. Kubernetes-based adapters should use `runtime_class` for gVisor rather than making gVisor a separate core dependency. The built-in Kubernetes adapter provides a dependency-free Job manifest dry-run and a `kubectl`-gated execution path; stronger integrations can replace it with an in-cluster controller or enterprise scheduler.

Sandbox adapter packages can remain optional so users who do not want Docker/E2B/Kubernetes can use `none`, `local`, bubblewrap, or their own enterprise executor.
