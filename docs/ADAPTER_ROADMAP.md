# Adapter Roadmap

[English](ADAPTER_ROADMAP.md) | [中文](zh/ADAPTER_ROADMAP.md)

AgentLedger keeps runtime-core thin: core owns invariants, contracts, events, evidence, replay, policy, and fail-closed behavior. Concrete integrations should be shipped as optional adapters when the target ecosystem is mature enough and the integration boundary is stable.

Packaging mechanics for the `1.2.0` adapter packaging release are defined in `ADAPTER_PACKAGING.md`. This roadmap defines priority and ownership; the packaging document defines package layout, extras, compatibility shims, and release gates.

## Decision Rules

An adapter should be official when it satisfies most of these conditions:

- The ecosystem is widely used by Agent/LLM production teams.
- The integration boundary is stable enough to maintain without chasing internals every release.
- The adapter can preserve AgentLedger invariants: durable state, Tool Ledger, policy, audit, evidence, replay, and failure semantics.
- The dependency is too heavy or too deployment-specific for runtime-core.
- The adapter can have conformance tests or injected-client tests without requiring a real cloud account in core CI.

An adapter should stay community/experimental when:

- The upstream SDK is unstable or mostly private/internal.
- The integration requires opinionated infrastructure that users should own.
- The runtime can only expose a safe boundary, not guarantee real behavior.
- The adapter would force core to become a workflow engine, eval platform, SaaS platform, or deployment product.

## Priority 1: Official Adapters

These should be first-class optional packages because they match common production needs and have clear runtime boundaries.

| Area | Adapter | Why it matters | Core contract already present | Expected package shape |
| --- | --- | --- | --- | --- |
| Storage | Postgres StateStore | Most enterprise pilots need server-side durable state, locking, migrations, and backup workflows. | `storage_schema.v1.json`, local persistence semantics, `optional_adapters.v1.json` | `agentledger-postgres` / language-native package |
| Blob store | S3 / MinIO BlobStore | Evidence bundles, media refs, stream checkpoints, and artifacts need cheap durable object storage. | `local_blob_store.v1.json`, content-addressed refs, `optional_adapters.v1.json` | `agentledger-s3` / language-native package |
| Framework | LangGraph | High overlap with stateful agent workflows; AgentLedger adds Tool Ledger, evidence, replay, policy, and adapter certification. | `framework_adapters.v1.json`, checkpoint boundary, optional capability descriptor | `agentledger-langgraph` |
| Tool/context protocol | MCP transport | MCP is a natural tool/context boundary for agents. Runtime should govern MCP tools without owning every tool server. | `mcp_adapters.v1.json`, `optional_adapters.v1.json` | `agentledger-mcp` / `agentledger-mcp-adapter` on npm |
| Observability | OpenTelemetry exporter/transport | Enterprises need traces in existing observability stacks. | `otlp_trace_export.v1.json` | `agentledger-otel` |
| Sandbox | Docker sandbox | Common local/team isolation backend; useful before Kubernetes/gVisor/Firecracker. | `policy_approval_sandbox.v1.json`, sandbox policy/result boundary | `agentledger-sandbox-docker` |
| Scheduler/backend | Temporal bridge | Temporal can own durable workflow orchestration while AgentLedger owns agent-specific evidence/tool/state semantics. | `scheduler.v1.json`, execution backend boundary | `agentledger-temporal` |

Docker is official first because it is the reference sandbox adapter, not because it is the only supported isolation model. AgentLedger core should remain container-runtime neutral: sandbox-required tools flow through the same policy, fail-closed, audit, evidence, timeout, and cleanup contract regardless of whether the executor is Docker, Kubernetes, E2B, gVisor/Kata, Firecracker, bubblewrap, nsjail, or a custom remote backend.

## Priority 2: Recommended Adapters

These are valuable but should follow the Priority 1 adapters or remain thinner facades until demand is clear.

| Area | Adapter | Reason | Notes |
| --- | --- | --- | --- |
| Framework | LangChain Runnable | Broad usage, relatively generic callable boundary. | Keep thin; avoid depending on LangChain internals. |
| Framework | CrewAI | Common for role-based teams, but AgentLedger should not inherit its orchestration model. | Wrap run/kickoff surfaces only. |
| Framework | AutoGen | Useful for multi-agent conversations; APIs vary by generation. | Use adapter certification before claiming stability. |
| Framework | OpenAI Agents SDK | Useful for OpenAI-native teams. | Keep aligned with official SDK surface; avoid duplicating SDK semantics. |
| Framework | LlamaIndex | Useful for RAG/knowledge-agent workloads. | Runtime should govern tools/evidence, not own retrieval. |
| Framework | Semantic Kernel | Relevant in .NET/enterprise environments. | More important when a .NET runtime/package exists. |
| Sandbox | Kubernetes Job sandbox | Good production boundary for cluster users. | Should support dry-run manifests, namespace/service account policy, and optional runtimeClass. |
| Sandbox | E2B | Good managed remote sandbox for code/tool execution. | Keep as optional remote executor adapter. |
| Distributed execution | Ray bridge | Useful for Python distributed worker pools. | Ray should own cluster scheduling; AgentLedger owns run semantics. |
| Deployment | Kubernetes worker recipe | Useful for pilots. | Recipe/Helm/examples first; full platform later only if needed. |

## Priority 3: Experimental Or Community Adapters

These should not block core parity or official release claims.

| Area | Adapter | Why not first-class yet |
| --- | --- | --- |
| Sandbox | gVisor | Usually consumed through Kubernetes/container runtime config rather than direct app SDK. |
| Sandbox | Firecracker | Powerful but infra-heavy; often managed through a platform layer. |
| Sandbox | bubblewrap | Useful on Linux local machines but less universal across macOS/Windows teams. |
| Workflow | Airflow / Prefect / Argo | They are batch/workflow systems; useful bridges, but AgentLedger should not become a general workflow engine. |
| Eval | LangSmith / Braintrust / custom eval platforms | Eval remains a consumer of evidence/replay contracts, not runtime-core. |
| Vector DB / RAG | Pinecone, Weaviate, Milvus, pgvector, etc. | Long-term memory/retrieval infra should be external; runtime stores refs/evidence, not knowledge retrieval logic. |
| SaaS/multi-tenant platform | Any hosted platform adapter | Out of current project scope. AgentLedger is a framework/library/runtime, not SaaS. |

## Cross-Language Policy

Python remains the reference implementation, but official adapters should converge across Go, TypeScript, and Rust when the ecosystem exists in that language.

| Adapter type | Python | Go | TypeScript | Rust | Policy |
| --- | --- | --- | --- | --- | --- |
| Runtime-core local defaults | Required | Required | Required | Required | Must stay aligned. |
| Postgres | Required official | Required official | Required official | Required official | Each language has mature clients. |
| S3 / MinIO | Required official | Required official | Required official | Required official | Each language has mature clients. |
| LangGraph | Required official | Not applicable unless ecosystem emerges | Not applicable unless ecosystem emerges | Not applicable unless ecosystem emerges | Official where the upstream ecosystem exists. |
| LangChain | Recommended | Community/optional | Recommended | Community/optional | Official only where API is stable and used. |
| MCP transport | Required official | Required official | Required official | Required official | Protocol-level adapter fits all languages. |
| Docker sandbox | Required official | Required official | Required official | Required official | CLI/runtime boundary is language-neutral. |
| Kubernetes sandbox/backend | Recommended | Recommended | Recommended | Recommended | Prefer manifest/dry-run contract plus optional execution. |
| Temporal bridge | Recommended | Required when Go runtime matures | Recommended | Community/optional | Match Temporal ecosystem strength per language. |
| OpenTelemetry | Required official | Required official | Required official | Required official | Standard enterprise observability path. |

## Non-Negotiable Adapter Requirements

Every official adapter must provide:

- A clear package boundary and no mandatory dependency from runtime-core.
- Config redaction and safe defaults.
- Fail-closed behavior when credentials, clients, binaries, or permissions are missing.
- Conformance tests using injected clients or local fixtures.
- Evidence records for adapter calls, failures, retries, and external refs.
- Version compatibility notes for upstream SDKs.
- Documentation in English and Chinese.

## Recommended Implementation Order

1. Postgres and S3/MinIO adapters across Python, Go, TypeScript, and Rust.
2. MCP transport adapter across Python, Go, TypeScript, and Rust.
3. Docker sandbox adapter across Python, Go, TypeScript, and Rust.
4. OpenTelemetry transport adapter across Python, Go, TypeScript, and Rust.
5. LangGraph official Python adapter package and certification examples.
6. LangChain / CrewAI / AutoGen / OpenAI Agents SDK / LlamaIndex / Semantic Kernel facades where ecosystems are stable.
7. Kubernetes sandbox/backend recipe, then optional execution adapter.
8. Temporal/Ray/Kubernetes scheduler/backend bridges based on real user demand.
