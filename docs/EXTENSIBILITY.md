# Extensibility and Adapter Model

The runtime must be extensible at every layer. Core should define stable contracts and invariants; adapters provide concrete integrations.

## Design Principle

```text
Core owns protocol and invariants.
Adapters own integration details.
No adapter should pollute runtime core.
```

## Extension Points

| Layer | Interface | Common Implementations |
|---|---|---|
| State | `StateStore` | SQLite WAL, Postgres |
| Events | `EventStore` | DB table, Kafka/Redpanda optional |
| Blob | `BlobStore` | local fs, S3, MinIO |
| Tools | `ToolExecutor` | local function, HTTP, MCP, sandbox executor |
| Policy | `PolicyEngine` | YAML, custom RBAC, OPA/Cedar adapter later |
| Sandbox | `SandboxExecutor` | local process, Docker, E2B, microVM later |
| Model | `ModelProvider` | OpenAI, Anthropic, local model, replay provider |
| Framework | `FrameworkAdapter` | LangChain, LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, custom |
| Worker | `WorkerProtocol` | Python SDK, TypeScript client, JSON-RPC, gRPC, HTTP |
| Observability | `TraceExporter` | local logs, OpenTelemetry, LangSmith-style backend |
| Eval | `EvalRunner` | rule checks, LLM judge, human review, regression suite |

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
timeout-adapters-autogen
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
- adapter must pass runtime event and replay conformance tests

## Storage Adapters

Storage must be pluggable because local dev and production have different needs.

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

## TypeScript Support

Python is the MVP runtime language, but SDK design must not be Python-only.

TypeScript can start as a worker/protocol client:

```text
create_run
claim_step
call_tool
append_event
write_state_patch
read_checkpoint
```

Later, TypeScript can include tool decorators and framework adapters.
