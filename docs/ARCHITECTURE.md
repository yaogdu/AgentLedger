# Architecture

AgentLedger is a runtime reliability layer for Agent Harness stacks. It is not an agent framework, model SDK, workflow engine, eval system, observability suite, RAG system, or sandbox infrastructure provider.

The architecture keeps runtime core thin but hard to replace: it only owns guarantees that must be enforced at the boundary between agent logic and external effects. Mature systems integrate through adapters and conformance tests instead of being rebuilt inside core.

In a complete harness stack, AgentLedger is the reliability substrate under or beside systems such as LangGraph, Temporal, Langfuse, MCP, model providers, storage backends, and sandbox providers.

The practical split is:

```text
core contract -> dependency-free local default -> optional production adapter
```

This lets a hello-world user run without extra services while advanced users can swap in mature infrastructure through the same runtime contract.

![AgentLedger runtime architecture](assets/agentledger-runtime-architecture.svg)

## Layered View

```text
Agent / Framework Layer
  plain Python functions, LangGraph, CrewAI, AutoGen, custom agents, future TS/Rust/Go workers

Runtime Boundary
  AgentContext, Runtime, ToolGateway, PolicyEngine, PolicyDecision, BudgetController

Execution Control
  Scheduler, leases, fencing tokens, retry policy, cancellation, worker loop

Durable Metadata
  runs, steps, events, tool_ledger, artifacts, costs, approvals, schema_migrations

Evidence and Reliability
  replay, evidence bundle, diff, evidence checks, trace JSONL, shadow mode

Adapter Layer
  storage, blob store, framework adapters, MCP, sandbox, observability, policy, model providers
```

## Core Flow

```text
create_run
  -> append run_created / step_created
claim_step
  -> acquire lease token and attempt number
execute agent function through AgentContext
  -> call tools through ToolGateway
  -> write state patches
  -> create artifacts
commit_state_patch
  -> validate lease token
  -> validate base state version
  -> apply patch atomically
  -> append completion events
replay/evidence
  -> read events and archived payloads
  -> never call external tools
```

## Runtime Core Modules

| Module | Responsibility |
|---|---|
| `src/agentledger/runtime.py` | Runtime orchestration and local execution loop. |
| `src/agentledger/context.py` | Agent-facing context for state, tools, artifacts, heartbeat. |
| `src/agentledger/store.py` | SQLite StateStore reference implementation. |
| `src/agentledger/storage_schema.py` | Storage DDL catalog and SQLite migration runner. |
| `src/agentledger/tools.py` | Tool registry, gateway, policy checks, approval, ledger, sandbox boundary. |
| `src/agentledger/policy.py` | PolicyRequest, PolicyDecision, evaluator registry, role/risk policy, decision composition. |
| `src/agentledger/replay.py` | Replay summary without external side effects. |
| `src/agentledger/evidence.py` | Evidence bundle export. |
| `src/agentledger/media.py` | Media artifact, lineage, stream chunk, and checkpoint contracts. |
| `src/agentledger/media_tools.py` | Dependency-free media and stream ToolSpec conventions. |
| `src/agentledger/scheduler.py` | Lease recovery, cancellation, status. |
| `src/agentledger/worker.py` | Local worker loop. |
| `src/agentledger/sandbox.py` | Sandbox executor contract and built-in adapter slots. |
| `src/agentledger/contract.py` | Language-neutral runtime contract export. |
| `src/agentledger/protocol.py` | Python protocol definitions for extension seams. |

## Runtime Invariants

The implementation should preserve these invariants across languages and adapters:

```text
events are append-only and ordered per run
state commits require a valid lease token
state commits require the expected base state version
stale, expired, or cancelled workers cannot commit
managed side effects reserve a unique idempotency key
PENDING_VERIFICATION side effects are not auto-retried
replay and shadow mode do not create external side effects
sandbox-required tools fail closed when isolation is unavailable
approval-required tools do not execute before approval
secrets should not be written into event payloads or evidence
```

## Adapter Boundary

Core owns semantics and invariants. Adapters own infrastructure details.

Examples:

```text
StateStore: SQLite, Postgres, MySQL, DynamoDB, internal store
BlobStore: local fs, S3, MinIO, GCS, OSS
SandboxExecutor: none, local, bubblewrap, Docker, Kubernetes/gVisor, Firecracker, E2B
FrameworkAdapter: LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents SDK, LlamaIndex, Semantic Kernel, custom
Observability: JSONL, OpenTelemetry, LangSmith-style backends, internal tracing
Policy: YAML, OPA, Cedar, RBAC/ABAC, enterprise policy service
```

An adapter is compatible only if it preserves runtime invariants and passes the relevant conformance tests.

## Storage Boundary

AgentLedger stores runtime metadata, not application data.

Runtime tables:

```text
runs
steps
events
tool_ledger
artifacts
cost_records
approval_requests
schema_migrations
```

Application tables such as users, orders, documents, or tasks remain owned by the user's application.

## Multi-language Boundary

Python is the reference implementation. It is not the protocol boundary.

AgentLedger targets native runtime-core parity across Python, Go, TypeScript, and Rust. SDK/client-only packages can help adoption, but they are not the protocol boundary and do not count as runtime-ready by themselves.

Go, TypeScript, and Rust implementations should target:

```text
contracts/agentledger.runtime.v1.json
docs/RUNTIME_SPEC.md
docs/MULTI_LANGUAGE.md
docs/LANGUAGE_PARITY_MATRIX.md
StateStore conformance semantics
evidence/replay golden fixtures
```

This prevents each language from inventing different event names, lease semantics, idempotency behavior, or evidence bundle shapes.

---

generated by codex cli
