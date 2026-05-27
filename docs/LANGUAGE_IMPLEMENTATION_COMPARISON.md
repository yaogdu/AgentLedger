# Language Implementation Comparison

[English](LANGUAGE_IMPLEMENTATION_COMPARISON.md) | [中文](zh/LANGUAGE_IMPLEMENTATION_COMPARISON.md)

This document makes the cross-language boundary explicit. AgentLedger's complete parity claim means **portable runtime-core parity**, not identical provider or ecosystem adapter implementations in every language.

## How To Read This Table

| Mark | Meaning |
|---|---|
| Yes | Implemented in that language. |
| Contract | Portable contract, facade, manifest, or injected-client adapter exists; provider-specific hardening may be external. |
| Python-only | Implemented only for Python because the upstream framework, SDK, or current native adapter path is Python-first. |
| N/A | Not applicable to that language or intentionally outside runtime core. |
| Roadmap | Planned or possible later, not part of the current parity claim. |

## Runtime-Core Parity

These capabilities are the parity target. All four languages must implement the same runtime semantics and pass shared conformance checks.

| Capability | Python | Go | TypeScript | Rust | Evidence / note |
|---|---:|---:|---:|---:|---|
| AgentContext / execution boundary | Yes | Yes | Yes | Yes | Runtime-owned context boundary. |
| Run / session / step model | Yes | Yes | Yes | Yes | Shared run state machine. |
| Durable state commits | Yes | Yes | Yes | Yes | Local durable/snapshot store per language. |
| Event log / WAL semantics | Yes | Yes | Yes | Yes | Evidence/replay fixtures. |
| Lease, fencing, recovery | Yes | Yes | Yes | Yes | Stale worker fencing and expired lease recovery. |
| Cancellation semantics | Yes | Yes | Yes | Yes | Cancelled runs fence late commits. |
| ToolGateway | Yes | Yes | Yes | Yes | Runtime-managed tool execution boundary. |
| Tool schema validation | Yes | Yes | Yes | Yes | Input/output schema checks. |
| Tool Ledger / idempotency | Yes | Yes | Yes | Yes | Idempotent side-effect retry semantics. |
| Policy denial | Yes | Yes | Yes | Yes | Deny before execution. |
| Approval pause/resume | Yes | Yes | Yes | Yes | HITL approval semantics. |
| Sandbox fail-closed boundary | Yes | Yes | Yes | Yes | Boundary semantics, not identical provider set. |
| Budget enforcement | Yes | Yes | Yes | Yes | Runtime-level budget exceeded behavior. |
| Cost attribution | Yes | Yes | Yes | Yes | Run/step/tool/model attribution shape. |
| Failure attribution | Yes | Yes | Yes | Yes | Agent/tool/model/runtime classification. |
| Evidence export | Yes | Yes | Yes | Yes | Evidence bundle consumers. |
| Replay without side effects | Yes | Yes | Yes | Yes | Replay skips external side effects. |
| Diff / divergence / debug summary | Yes | Yes | Yes | Yes | Evidence consumers. |
| Static debug HTML export | Yes | Yes | Yes | Yes | Debug artifact generation. |
| Time travel timeline | Yes | Yes | Yes | Yes | Timeline/state-at-seq semantics. |
| Failure injection suite | Yes | Yes | Yes | Yes | Reliability harness contract. |
| Evidence regression | Yes | Yes | Yes | Yes | Golden/evidence comparison. |
| Shadow report | Yes | Yes | Yes | Yes | Replay/rerun comparison shape. |
| Scheduler facade | Yes | Yes | Yes | Yes | Local scheduler/status/recover/cancel facade. |
| Local worker/service | Yes | Yes | Yes | Yes | Worker loop and idle polling semantics. |
| CLI baseline | Yes | Yes | Yes | Yes | `help`, `doctor`, `quickstart`, `conformance`, `contract`. |
| Runnable quickstart example | Yes | Yes | Yes | Yes | `examples/`, `go/examples/`, `typescript/examples/`, `rust/examples/`. |
| Contract export/validation | Yes | Yes | Yes | Yes | Shared contract and conformance manifest. |

## Portable Adapter Contracts

These are portable enough to expose across languages. They do not mean every language bundles the same production driver or cloud SDK.

| Capability | Python | Go | TypeScript | Rust | Evidence / note |
|---|---:|---:|---:|---:|---|
| Local StateStore | Yes | Yes | Yes | Yes | Default local implementation for quickstart and tests. |
| Local BlobStore | Yes | Yes | Yes | Yes | Content-addressed local blob semantics. |
| Postgres adapter contract | Yes | Contract | Contract | Contract | Python has `PostgresStore`; Go/TS/Rust use injected SQL adapter/facade. |
| S3/MinIO blob adapter contract | Yes | Contract | Contract | Contract | Python has `S3BlobStore`; Go/TS/Rust use injected object-client adapter/facade. |
| OTLP trace export / transport | Yes | Contract | Contract | Contract | JSON/export or injected transport boundary. |
| Docker sandbox manifest | Yes | Yes | Yes | Yes | Portable manifest/fail-closed behavior; daemon hardening is external. |
| MCP-style tool/context mapping | Yes | Yes | Yes | Yes | Dependency-free in-memory contracts. |
| Function/method framework facade | Yes | Yes | Yes | Yes | Generic dependency-free framework adapter shape. |
| Media artifact refs | Yes | Yes | Yes | Yes | Evidence refs only; not full media processing. |
| Event stream checkpoint refs | Yes | Yes | Yes | Yes | Checkpoint/ref semantics only. |

## Concrete Provider Implementations

These are intentionally not required to be identical across languages. They are provider-specific infrastructure or production-pilot paths.

| Capability | Python | Go | TypeScript | Rust | Explanation |
|---|---:|---:|---:|---:|---|
| Sandbox executor count | 7 | 3 | 3 | 2 | Python includes Bubblewrap/Docker/E2B/Firecracker/Kubernetes/Local/Remote. Go/TypeScript/Rust include local/fail-closed semantics and Docker command-style execution. |
| Bubblewrap executor | Yes | N/A | N/A | N/A | Linux/Python command executor path; not required for core parity. |
| Docker executor | Yes | Yes | Yes | Yes | Command-style tools can execute through Docker CLI when command execution is explicitly enabled; tests use injected binaries and do not require a daemon. |
| E2B executor | Yes | Roadmap | Roadmap | Roadmap | Hosted sandbox provider; adapter-level, not runtime-core. |
| Firecracker executor | Yes | Roadmap | Roadmap | Roadmap | Infrastructure-specific sandbox adapter. |
| Kubernetes executor | Yes | Roadmap | Roadmap | Roadmap | Deployment/sandbox infrastructure adapter. |
| Native Postgres StateStore driver | Yes | Roadmap | Roadmap | Roadmap | Python has psycopg-backed store; other languages currently expose injected SQL contract. |
| Native S3 SDK-backed BlobStore | Yes | Roadmap | Roadmap | Roadmap | Python has optional boto3 path; other languages use injected object client boundary. |
| Real-service Postgres hardening | Optional | Optional | Optional | Optional | Release/pilot validation, not current core parity. |
| Real-service S3/MinIO hardening | Optional | Optional | Optional | Optional | Release/pilot validation, not current core parity. |

## Ecosystem-Specific Framework Adapters

These adapters follow the ecosystem where the upstream framework actually exists. They should not be copied into every language just to make a table look symmetrical.

| Adapter | Python | Go | TypeScript | Rust | Why |
|---|---:|---:|---:|---:|---|
| LangGraphCheckpointerAdapter | Yes | N/A | Yes | N/A | Python and TypeScript/Node have LangGraph package paths; Go/Rust use the generic framework boundary. |
| LangGraphNodeAdapter | Yes | N/A | Yes | N/A | Python and TypeScript/Node expose facade/package boundaries; Go/Rust use generic function/method adapters. |
| LangChainRunnableAdapter | Yes | N/A | N/A | N/A | Current built-in target is Python LangChain. |
| CrewAIAdapter | Yes | N/A | N/A | N/A | CrewAI is Python ecosystem. |
| AutoGenAdapter | Yes | N/A | N/A | N/A | Current built-in target is Python AutoGen. |
| OpenAIAgentsSDKAdapter | Yes | N/A | N/A | N/A | Current built-in target is Python Agents SDK. |
| LlamaIndexAdapter | Yes | N/A | N/A | N/A | Current built-in target is Python LlamaIndex. |
| SemanticKernelAdapter | Yes | N/A | N/A | N/A | Current built-in target is Python Semantic Kernel path. |

## What Counts As Complete Parity

Complete parity means:

```text
portable runtime-core behavior + contract + conformance + CLI/DX + examples + package metadata
```

Complete parity does not mean:

```text
identical provider implementations, identical cloud SDKs, or ecosystem-specific framework adapters in every language
```

## Directory Layout Decision

The current directories should stay as they are:

| Directory | Keep? | Reason |
|---|---:|---|
| `go/` | Yes | Matches Go module conventions and keeps Go package isolated. |
| `typescript/` | Yes | Clear source-language name; package name is `agentledger-runtime`. The runtime targets Node.js but the implementation/documentation surface is TypeScript-compatible. |
| `rust/` | Yes | Matches Rust crate conventions and keeps Cargo files isolated. |
| `src/agentledger/` | Yes | Python reference package layout. |

Renaming `typescript/` to `node/` is not recommended right now: it would create churn without improving runtime semantics. If a future repo split happens, package/repo naming can be revisited then.
